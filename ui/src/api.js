const API = "http://127.0.0.1:8765";

async function request(path, options) {
  const response = await fetch(API + path, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok && data.error) {
    throw new Error(data.error);
  }
  return data;
}

export function loadSettings() {
  return request("/api/settings");
}

export function setSaveAnswers(enabled) {
  return request("/api/settings/save", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ enabled }),
  });
}

export function listAnswers() {
  return request("/api/answers");
}

export function deleteAnswers(names) {
  return request("/api/answers/delete", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ names }),
  });
}

export function deleteAllAnswers() {
  return request("/api/answers/delete-all", { method: "POST" });
}

export function openUrl(url) {
  return request("/api/open-url", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url }),
  });
}

export function beginLogin(switchAccount) {
  return request("/api/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ switch: switchAccount }),
  });
}

export function loginStatus() {
  return request("/api/login/status");
}

export async function solveBatch(urls, apiKey, onProgress) {
  const response = await fetch(API + "/api/solve", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ urls, apiKey }),
  });
  if (!response.ok || !response.body) {
    throw new Error("获取答案失败");
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let result = null;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let newline = buffer.indexOf("\n");
    while (newline >= 0) {
      const line = buffer.slice(0, newline).trim();
      buffer = buffer.slice(newline + 1);
      newline = buffer.indexOf("\n");
      if (!line) continue;
      const message = JSON.parse(line);
      if (message.type === "progress" && onProgress) onProgress(message.message || "");
      if (message.type === "result") result = message;
    }
  }
  if (!result) throw new Error("没有返回结果");
  return result;
}
