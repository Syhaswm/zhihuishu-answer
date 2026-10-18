importScripts("config.js");

const DEFAULTS = {
  apiKey: self.ZHS_CONFIG.apiKey || "",
  model: self.ZHS_CONFIG.model || "deepseek-chat",
  apiBase: self.ZHS_CONFIG.apiBase || "https://api.deepseek.com/chat/completions",
};

async function seedConfig() {
  const cur = await chrome.storage.local.get(["apiKey", "model", "apiBase"]);
  const patch = {};
  if (!cur.apiKey && DEFAULTS.apiKey) patch.apiKey = DEFAULTS.apiKey;
  if (!cur.model) patch.model = DEFAULTS.model;
  if (!cur.apiBase) patch.apiBase = DEFAULTS.apiBase;
  if (Object.keys(patch).length) await chrome.storage.local.set(patch);
}

chrome.runtime.onInstalled.addListener(() => {
  seedConfig();
});
seedConfig();

async function getConfig() {
  const stored = await chrome.storage.local.get(["apiKey", "model", "apiBase"]);
  return {
    apiKey: stored.apiKey || DEFAULTS.apiKey,
    model: stored.model || DEFAULTS.model,
    apiBase: stored.apiBase || DEFAULTS.apiBase,
  };
}

function buildPrompt(questions) {
  const blocks = questions.map((q) => {
    const lines = [`${q.n}. [${q.type}] ${q.stem}`];
    if (q.options && q.options.length) {
      q.options.forEach((opt) => lines.push(`- ${opt.content}`));
    } else {
      lines.push("（无选项，请直接作答）");
    }
    return lines.join("\n");
  });
  return [
    "根据下面的题目作答。只输出一个 JSON 对象，不要 Markdown。",
    "格式：{\"answers\":[{\"n\":1,\"answer\":[\"选项原文\"],\"reason\":\"不超过40字\"}]}",
    "规则：",
    "1. 选择题的 answer 必须逐字复制选项原文。单选只放 1 个，多选放全部正确项。",
    "2. 判断题 answer 使用选项原文；没有选项时用「对」或「错」。",
    "3. 填空、简答把答案放进 answer 数组，只放一个字符串。",
    "4. n 使用题目给出的题号。",
    "",
    blocks.join("\n\n"),
  ].join("\n");
}

function parseModelJson(text) {
  const trimmed = String(text || "").trim();
  try {
    return JSON.parse(trimmed);
  } catch (e) {}
  const fence = trimmed.match(/```(?:json)?\s*([\s\S]*?)```/);
  if (fence) return JSON.parse(fence[1]);
  const start = trimmed.indexOf("{");
  const end = trimmed.lastIndexOf("}");
  if (start >= 0 && end > start) return JSON.parse(trimmed.slice(start, end + 1));
  throw new Error("模型没有返回 JSON");
}

async function askChunk(cfg, questions) {
  const resp = await fetch(cfg.apiBase, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${cfg.apiKey}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      model: cfg.model,
      temperature: 0.1,
      max_tokens: 2500,
      response_format: { type: "json_object" },
      messages: [
        {
          role: "system",
          content: "你只根据题目和选项作答，并且只输出 JSON。",
        },
        { role: "user", content: buildPrompt(questions) },
      ],
    }),
    signal: AbortSignal.timeout(120000),
  });
  const raw = await resp.text();
  let data;
  try {
    data = JSON.parse(raw);
  } catch (e) {
    throw new Error(`DeepSeek 返回的不是 JSON（HTTP ${resp.status}）`);
  }
  if (!resp.ok) {
    const message = data.error && data.error.message ? data.error.message : raw.slice(0, 300);
    throw new Error(`DeepSeek ${resp.status}：${message}`);
  }
  const content = data.choices && data.choices[0] && data.choices[0].message
    ? data.choices[0].message.content
    : "";
  const parsed = parseModelJson(content);
  const list = Array.isArray(parsed.answers) ? parsed.answers : [];
  return list.map((item) => ({
    n: Number(item.n),
    answer: item.answer,
    reason: item.reason || "",
  }));
}

async function solve(questions) {
  const cfg = await getConfig();
  if (!cfg.apiKey) throw new Error("没有 API Key。点浏览器工具栏里的插件图标填写。");
  const answers = [];
  const size = 10;
  for (let i = 0; i < questions.length; i += size) {
    const part = await askChunk(cfg, questions.slice(i, i + size));
    answers.push(...part);
  }
  return answers;
}

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (!msg || msg.type !== "solve") return;
  solve(msg.questions || [])
    .then((answers) => sendResponse({ ok: true, answers }))
    .catch((err) => sendResponse({ ok: false, error: err.message || String(err) }));
  return true;
});
