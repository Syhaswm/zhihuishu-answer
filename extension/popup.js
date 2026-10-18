const keyEl = document.getElementById("key");
const modelEl = document.getElementById("model");
const statusEl = document.getElementById("status");

chrome.storage.local.get(["apiKey", "model"], (cfg) => {
  keyEl.value = cfg.apiKey || "";
  if (cfg.model) modelEl.value = cfg.model;
});

document.getElementById("save").addEventListener("click", () => {
  const apiKey = keyEl.value.trim();
  const model = modelEl.value.trim() || "deepseek-chat";
  chrome.storage.local.set({ apiKey, model }, () => {
    statusEl.textContent = apiKey ? "已保存" : "Key 是空的，调用会失败";
  });
});
