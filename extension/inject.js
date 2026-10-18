(() => {
  const MARK = "__zhsAnswerHooked";
  if (window[MARK]) return;
  window[MARK] = true;

  let lastText = "";

  function emit(url, text) {
    const href = String(url || "");
    if (!href.includes("/student/doHomework")) return;
    if (!text || text === lastText) return;
    lastText = text;
    window.postMessage({ source: "zhs-answer", type: "exam-json", text }, "*");
  }

  const origFetch = window.fetch;
  if (typeof origFetch === "function") {
    window.fetch = function (...args) {
      const pending = origFetch.apply(this, args);
      try {
        const input = args[0];
        const url = typeof input === "string" ? input : input && input.url;
        pending
          .then((res) => {
            try {
              res.clone().text().then((text) => emit(url, text)).catch(() => {});
            } catch (e) {}
          })
          .catch(() => {});
      } catch (e) {}
      return pending;
    };
  }

  const origOpen = XMLHttpRequest.prototype.open;
  const origSend = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function (method, url) {
    this.__zhsUrl = url;
    return origOpen.apply(this, arguments);
  };
  XMLHttpRequest.prototype.send = function () {
    this.addEventListener("load", function () {
      try {
        emit(this.__zhsUrl, this.responseText);
      } catch (e) {}
    });
    return origSend.apply(this, arguments);
  };

  window.addEventListener("message", (event) => {
    if (event.source !== window) return;
    const data = event.data;
    if (!data || data.source !== "zhs-answer" || data.type !== "ping") return;
    if (!lastText) return;
    window.postMessage({ source: "zhs-answer", type: "exam-json", text: lastText }, "*");
  });
})();
