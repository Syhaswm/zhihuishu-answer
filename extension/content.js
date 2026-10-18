(() => {
  const PANEL_ID = "zhs-answer-panel";
  let currentExam = null;
  let solving = false;

  function stripHtml(raw) {
    const el = document.createElement("div");
    el.innerHTML = String(raw || "");
    return (el.textContent || "").replace(/\u00a0/g, " ").replace(/\s+/g, " ").trim();
  }

  function normalizeQuestion(q) {
    const rawName = String(q.name || "");
    let stem = stripHtml(rawName);
    if (/<img\b/i.test(rawName)) stem += "（题目含图片，仅按文字作答）";
    return {
      type: (q.questionType && q.questionType.name) || "未知题型",
      typeId: q.questionType && q.questionType.id,
      stem,
      options: (q.questionOptions || [])
        .map((opt) => ({ id: opt.id, content: stripHtml(opt.content) }))
        .filter((opt) => opt.content),
      score: q.questionScore || "",
    };
  }

  function collectQuestions(nodes, bucket) {
    (nodes || []).forEach((q) => {
      const children = q.questionChildrens;
      if (Array.isArray(children) && children.length) {
        collectQuestions(children, bucket);
        return;
      }
      const item = normalizeQuestion(q);
      if (item.stem) bucket.push(item);
    });
  }

  function parseExam(text) {
    let data;
    try {
      data = JSON.parse(text);
    } catch (e) {
      return null;
    }
    const exam = data && data.rt && data.rt.examBase;
    const parts = exam && exam.workExamParts;
    if (!Array.isArray(parts)) return null;
    const questions = [];
    parts.forEach((part) => collectQuestions(part.questionDtos, questions));
    questions.forEach((q, i) => {
      q.n = i + 1;
    });
    if (!questions.length) return null;
    return {
      title: exam.name || "作业",
      course: exam.courseName || "",
      questions,
    };
  }

  function answerList(raw, options) {
    const opts = options || [];
    if (Array.isArray(raw)) return raw.map((s) => String(s).trim()).filter(Boolean);
    const text = String(raw || "").trim();
    if (!text) return [];
    if (opts.some((o) => o.content === text)) return [text];
    const pieces = text.split(/[、,，;；]/).map((s) => s.trim()).filter(Boolean);
    return pieces.length ? pieces : [text];
  }

  function ensurePanel() {
    let panel = document.getElementById(PANEL_ID);
    if (panel) return panel;
    panel = document.createElement("aside");
    panel.id = PANEL_ID;
    panel.innerHTML = `
      <div class="zhs-head">
        <strong>智慧树答题</strong>
        <button type="button" class="zhs-icon" data-act="collapse" title="收起">–</button>
      </div>
      <div class="zhs-body">
        <div class="zhs-meta"></div>
        <div class="zhs-status">打开作业页后刷新一次，插件会截获题目。</div>
        <div class="zhs-actions">
          <button type="button" data-act="solve">重新解答</button>
          <button type="button" data-act="copy">复制答案</button>
        </div>
        <ol class="zhs-list"></ol>
        <p class="zhs-foot">答案由 DeepSeek 生成，提交前请自行核对。插件不会替你交卷。</p>
      </div>
    `;
    panel.addEventListener("click", (event) => {
      const btn = event.target.closest("[data-act]");
      if (!btn) return;
      const act = btn.getAttribute("data-act");
      if (act === "collapse") {
        panel.classList.toggle("is-collapsed");
        btn.textContent = panel.classList.contains("is-collapsed") ? "答" : "–";
      } else if (act === "solve") {
        solveCurrent();
      } else if (act === "copy") {
        copyAnswers();
      }
    });
    document.documentElement.appendChild(panel);
    return panel;
  }

  function setStatus(text, isError) {
    const panel = ensurePanel();
    const el = panel.querySelector(".zhs-status");
    el.textContent = text;
    el.classList.toggle("is-error", !!isError);
  }

  function renderQuestions() {
    const panel = ensurePanel();
    const exam = currentExam;
    panel.querySelector(".zhs-meta").textContent = exam
      ? `${exam.course ? exam.course + " · " : ""}${exam.title} · ${exam.questions.length} 题`
      : "";
    const list = panel.querySelector(".zhs-list");
    list.innerHTML = "";
    if (!exam) return;
    exam.questions.forEach((q) => {
      const li = document.createElement("li");
      li.dataset.n = String(q.n);
      const answers = answerList(q.modelAnswer, q.options);
      const answerText = answers.length ? answers.join("、") : "等待解答";
      li.innerHTML = `
        <div class="zhs-qtype">${q.n}. ${q.type}${q.score ? " · " + q.score + "分" : ""}</div>
        <div class="zhs-stem"></div>
        <div class="zhs-answer"></div>
        <div class="zhs-reason"></div>
      `;
      li.querySelector(".zhs-stem").textContent = q.stem;
      li.querySelector(".zhs-answer").textContent = "答案：" + answerText;
      li.querySelector(".zhs-reason").textContent = q.reason || "";
      list.appendChild(li);
    });
  }

  function clearHighlights() {
    document.querySelectorAll(".zhs-hit").forEach((el) => el.classList.remove("zhs-hit"));
  }

  function ownText(el) {
    let text = "";
    el.childNodes.forEach((node) => {
      if (node.nodeType === Node.TEXT_NODE) text += node.textContent;
    });
    return text.replace(/\s+/g, " ").trim();
  }

  function highlightAnswers() {
    clearHighlights();
    if (!currentExam) return;
    const wanted = new Set();
    currentExam.questions.forEach((q) => {
      answerList(q.modelAnswer, q.options).forEach((text) => {
        if (text) wanted.add(text);
      });
    });
    if (!wanted.size) return;
    const panel = document.getElementById(PANEL_ID);
    document.querySelectorAll("div, span, p, li, label, a").forEach((el) => {
      if (panel && panel.contains(el)) return;
      const direct = ownText(el);
      const full = (el.textContent || "").replace(/\s+/g, " ").trim();
      const hit = wanted.has(direct) || (el.childElementCount <= 1 && full.length <= 40 && wanted.has(full));
      if (hit) el.classList.add("zhs-hit");
    });
    document.querySelectorAll(".zhs-hit").forEach((el) => {
      if (el.querySelector(".zhs-hit")) el.classList.remove("zhs-hit");
    });
  }

  async function solveCurrent() {
    if (!currentExam || solving) return;
    solving = true;
    setStatus(`正在请求 DeepSeek，共 ${currentExam.questions.length} 题…`);
    try {
      const resp = await chrome.runtime.sendMessage({
        type: "solve",
        questions: currentExam.questions.map((q) => ({
          n: q.n,
          type: q.type,
          stem: q.stem,
          options: q.options,
        })),
      });
      if (!resp || !resp.ok) throw new Error((resp && resp.error) || "没有收到解答");
      const byN = new Map();
      (resp.answers || []).forEach((item) => byN.set(Number(item.n), item));
      currentExam.questions.forEach((q) => {
        const item = byN.get(q.n);
        if (!item) return;
        q.modelAnswer = item.answer;
        q.reason = item.reason || "";
      });
      renderQuestions();
      highlightAnswers();
      const missing = currentExam.questions.filter((q) => !answerList(q.modelAnswer, q.options).length).length;
      setStatus(missing ? `已返回，有 ${missing} 题没有解析到答案` : "已返回答案，绿色为页面上匹配到的选项");
    } catch (err) {
      setStatus(err.message || String(err), true);
    } finally {
      solving = false;
    }
  }

  async function copyAnswers() {
    if (!currentExam) return;
    const text = currentExam.questions
      .map((q) => {
        const answers = answerList(q.modelAnswer, q.options);
        return `${q.n}. ${answers.join("、") || "（无）"}`;
      })
      .join("\n");
    try {
      await navigator.clipboard.writeText(text);
    } catch (e) {
      const area = document.createElement("textarea");
      area.value = text;
      area.setAttribute("readonly", "");
      area.style.position = "fixed";
      area.style.left = "-9999px";
      document.body.appendChild(area);
      area.select();
      const ok = document.execCommand("copy");
      area.remove();
      if (!ok) {
        setStatus("复制失败，请从面板里手动选择", true);
        return;
      }
    }
    setStatus("答案已复制");
  }

  function onExamText(text) {
    const exam = parseExam(text);
    if (!exam) return;
    currentExam = exam;
    ensurePanel();
    renderQuestions();
    clearHighlights();
    solveCurrent();
  }

  window.addEventListener("message", (event) => {
    if (event.source !== window) return;
    const data = event.data;
    if (!data || data.source !== "zhs-answer" || data.type !== "exam-json") return;
    onExamText(data.text);
  });

  window.postMessage({ source: "zhs-answer", type: "ping" }, "*");
})();
