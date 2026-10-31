<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { BackTop, Banner, Button, Card, Checkbox, Input, Modal, Pagination, Select, Switch, Tag, TextArea, Toast } from "@kousum/semi-ui-vue";
import * as api from "./api";
import { applyDockLayout, applyWindowOpacity, DOCK_WIDTH_DEFAULT } from "./dock";
import { registerCopyHotkey, unregisterCopyHotkey, writeClipboard } from "./hotkey";

const url = ref("");
const apiKey = ref("");
const providerKeys = ref({});
const provider = ref("deepseek");
const modelName = ref("deepseek-flash");
const modelOptions = ref([]);
const loadingModels = ref(false);
const testingLink = ref(false);
const loadingUsage = ref(false);
const modelHint = ref("");
const connectHint = ref("");
const connectOk = ref(false);
const usageRows = ref([]);
const usageNote = ref("");
const usageConsole = ref("");
const usageSupported = ref(false);
const sessionUsageText = ref("");
const sessionCacheText = ref("");
const thinking = ref(false);
const baseUrl = ref("https://api.deepseek.com/chat/completions");
const providers = ref([
  { id: "deepseek", name: "DeepSeek", url: "https://api.deepseek.com/chat/completions", model: "deepseek-flash", needsKey: true, hint: "在 DeepSeek 开放平台创建的 Key" },
]);
const scroller = ref(null);
const loading = ref(false);
const loggingIn = ref(false);
const accountName = ref("");
const status = ref("先点登录账号，在弹出的窗口登录。之后获取答案会一直用这个账号。");
const error = ref("");
const batchFailKind = ref("");
const batchFailTitle = ref("");
const batchFailNext = ref("");
const papers = ref([]);
const saveAnswers = ref(true);
const resumeCheckpoint = ref(true);
const pendingRetryCount = ref(0);
const pendingRetryHint = ref("");
const answerFiles = ref([]);
const showAllFiles = ref(false);
const selectedFiles = ref([]);
const confirmAll = ref(false);
const page = ref(1);
const paperAnchor = ref(null);
const helpOpen = ref(false);
const fullFetchConfirmOpen = ref(false);
const fullFetchConfirmItems = ref([]);
let fullFetchConfirmPending = null;
const updateInfo = ref(null);
const updateCheckFailed = ref("");
const checkingUpdate = ref(false);
const appVersionText = ref("");
const selectedQuestionN = ref(null);
const selectedPartIndex = ref(0);
const hotkeyHint = "Ctrl+Shift+C";
const keyPage = "https://platform.deepseek.com/api_keys";
const dockSide = ref("off");
const dockWidth = ref(DOCK_WIDTH_DEFAULT);
const dockOnTop = ref(true);
const dockOpacity = ref(100);
const dockOpacityOptions = [
  { value: 100, label: "不透明" },
  { value: 95, label: "95%" },
  { value: 90, label: "90%" },
  { value: 85, label: "85%（最透）" },
];
const showDockSettings = ref(true);
const dockShowAllQuestions = ref(false);
const answerShowReason = ref(false);
const answerFontSize = ref("medium");
const answerDisplayOptions = [
  { value: "answers", label: "仅答案" },
  { value: "reason", label: "含解析" },
];
const answerFontOptions = [
  { value: "small", label: "小" },
  { value: "medium", label: "中" },
  { value: "large", label: "大" },
];
const dockModeOptions = [
  { value: "off", label: "常规窗口" },
  { value: "left", label: "贴在屏幕左侧" },
  { value: "right", label: "贴在屏幕右侧" },
];

const currentPaper = computed(() => papers.value[page.value - 1] || null);
const currentProvider = computed(() => providers.value.find((item) => item.id === provider.value) || providers.value[0]);
function modelSupportsThinking(providerId, model) {
  const name = String(model || "").toLowerCase();
  if (providerId === "deepseek" || name.includes("deepseek")) return true;
  if (["thinking", "reason", "-r1", "qwq", "qwen3"].some((token) => name.includes(token))) return true;
  if (name.includes("glm-4.5") || name.includes("glm-4.6") || name.includes("glm-4.7") || name.includes("glm-5")) return true;
  return false;
}
const supportsThinking = computed(() => modelSupportsThinking(provider.value, modelName.value));
const providerOptions = computed(() => providers.value.map((item) => ({ value: item.id, label: item.name })));
const visibleFiles = computed(() =>
  showAllFiles.value ? answerFiles.value : answerFiles.value.slice(0, 3)
);
const isDocked = computed(() => dockSide.value === "left" || dockSide.value === "right");

const answerDisplayMode = computed(() => (answerShowReason.value ? "reason" : "answers"));

const pageDisplayClasses = computed(() => ({
  "page--dock": isDocked.value,
  "page--answer-font-small": answerFontSize.value === "small",
  "page--answer-font-large": answerFontSize.value === "large",
}));

function showQuestionStem() {
  return !isDocked.value;
}

function showQuestionOptions(question) {
  return !isDocked.value && question?.options?.length;
}

function showQuestionReason(question) {
  return answerShowReason.value && question?.reason;
}

const dockQuestions = computed(() => {
  const paper = currentPaper.value;
  if (!paper?.questions?.length) return [];
  return paper.questions;
});

const dockQuestionIndex = computed(() => {
  const qs = dockQuestions.value;
  if (!qs.length) return -1;
  const idx = qs.findIndex((item) => item.n === selectedQuestionN.value);
  return idx >= 0 ? idx : 0;
});

const dockFocusedQuestion = computed(() => {
  const qs = dockQuestions.value;
  if (!qs.length) return null;
  const idx = Math.max(0, dockQuestionIndex.value);
  return qs[idx] || null;
});

const dockQuestionOptions = computed(() =>
  dockQuestions.value.map((item) => ({ value: item.n, label: `第 ${item.n} 题` }))
);

const dockFocusedParts = computed(() => {
  const question = dockFocusedQuestion.value;
  return question ? displayParts(question) : [];
});

const visibleQuestions = computed(() => {
  const paper = currentPaper.value;
  if (!paper?.questions?.length) return [];
  if (isDocked.value && !dockShowAllQuestions.value && dockFocusedQuestion.value) {
    return [dockFocusedQuestion.value];
  }
  return paper.questions;
});

function ensureDockSelection() {
  const qs = dockQuestions.value;
  if (!qs.length) return;
  if (selectedQuestionN.value == null || !qs.some((item) => item.n === selectedQuestionN.value)) {
    selectQuestion(qs[0], 0);
  }
}

function goPrevQuestion() {
  const qs = dockQuestions.value;
  const idx = dockQuestionIndex.value;
  if (idx <= 0) {
    Toast.info("已经是第一题");
    return;
  }
  selectQuestion(qs[idx - 1], 0);
}

function goNextQuestion() {
  const qs = dockQuestions.value;
  const idx = dockQuestionIndex.value;
  if (idx < 0 || idx >= qs.length - 1) {
    Toast.info("已经是最后一题");
    return;
  }
  selectQuestion(qs[idx + 1], 0);
}

function jumpDockQuestion(value) {
  const n = Number(value);
  const question = dockQuestions.value.find((item) => item.n === n);
  if (question) selectQuestion(question, 0);
}

function goPrevPart() {
  if (selectedPartIndex.value <= 0) {
    Toast.info("已经是第一空");
    return;
  }
  selectedPartIndex.value -= 1;
}

function goNextPart() {
  const len = dockFocusedParts.value.length;
  if (len <= 1 || selectedPartIndex.value >= len - 1) {
    Toast.info("已经是最后一空");
    return;
  }
  selectedPartIndex.value += 1;
}

watch([isDocked, dockQuestions], () => {
  if (isDocked.value) ensureDockSelection();
});

function showPage(next) {
  const total = papers.value.length;
  const value = Math.min(Math.max(Number(next) || 1, 1), total || 1);
  page.value = value;
  selectedQuestionN.value = null;
  selectedPartIndex.value = 0;
  if (isDocked.value) ensureDockSelection();
  paperAnchor.value?.scrollIntoView({ block: "start" });
}

function selectQuestion(question, partIndex = 0) {
  if (!question) return;
  selectedQuestionN.value = question.n;
  selectedPartIndex.value = partIndex;
}

function isQuestionSelected(question) {
  return selectedQuestionN.value === question.n;
}

function hotkeyCopyPayload() {
  const paper = currentPaper.value;
  if (!paper?.ok || !paper.questions?.length) return null;
  let question = paper.questions.find((item) => item.n === selectedQuestionN.value);
  if (!question) question = paper.questions[0];
  if (!question) return null;
  const parts = displayParts(question);
  if (question.options?.length) {
    const text = answerParts(question).join("、") || String(question.answer || "");
    return { text, hint: `第 ${question.n} 题` };
  }
  const index = Math.min(Math.max(selectedPartIndex.value, 0), parts.length - 1);
  const part = parts[index] || parts[0];
  const label = part?.label ? String(part.label).trim() : "";
  return {
    text: part?.text || "",
    hint: label ? `第 ${question.n} 题 ${label}` : `第 ${question.n} 题`,
  };
}

async function copyHotkeyAnswer() {
  const payload = hotkeyCopyPayload();
  if (!payload) {
    Toast.warning("还没有可复制的答案，请先获取答案。");
    return;
  }
  const text = String(payload.text || "").trim();
  if (!text) {
    Toast.warning("当前选中没有答案，请点选另一题或某一空。");
    return;
  }
  const ok = await writeClipboard(text);
  if (ok) {
    Toast.success(`已复制（${payload.hint}）`);
  } else {
    error.value = "复制失败，请手动选择这段答案";
  }
}

function answerParts(question) {
  return String(question.answer || "")
    .split("、")
    .map((item) => item.trim())
    .filter(Boolean);
}

function isHit(question, option) {
  return answerParts(question).includes(option);
}

function scrollTarget() {
  return scroller.value || window;
}

async function loadSettings() {
  let data = null;
  for (let attempt = 0; attempt < 40; attempt += 1) {
    try {
      data = await api.loadSettings();
      break;
    } catch (err) {
      await new Promise((resolve) => setTimeout(resolve, 250));
    }
  }
  if (!data) {
    status.value = "答题服务还没启动，请稍等再打开一次。";
    return;
  }
  if (Array.isArray(data.providers) && data.providers.length) providers.value = data.providers;
  provider.value = data.provider || "deepseek";
  providerKeys.value = data.keys && typeof data.keys === "object" ? { ...data.keys } : {};
  if (data.apiKey && !providerKeys.value[provider.value]) {
    providerKeys.value[provider.value] = data.apiKey;
  }
  apiKey.value = providerKeys.value[provider.value] || "";
  const savedModel = data.model || "";
  modelName.value =
    !savedModel || savedModel === "deepseek-chat" ? currentProvider.value?.model || "deepseek-flash" : savedModel;
  baseUrl.value = data.baseUrl || currentProvider.value?.url || "";
  thinking.value = !!data.thinking;
  accountName.value = data.name || "";
  saveAnswers.value = data.saveAnswers !== false;
  answerFiles.value = data.files || [];
  if (data.expired) {
    status.value = "登录已过期。请点「切换账号」重新登录。";
  }
  dockSide.value = data.dockSide || "off";
  dockWidth.value = data.dockWidth || DOCK_WIDTH_DEFAULT;
  dockOnTop.value = data.dockOnTop !== false;
  dockOpacity.value = normalizeDockOpacity(data.dockOpacity);
  answerShowReason.value = data.answerShowReason === true;
  const font = String(data.answerFontSize || "medium").toLowerCase();
  answerFontSize.value = font === "small" || font === "large" ? font : "medium";
  showDockSettings.value = !isDocked.value;
  if (isDocked.value) {
    try {
      await applyDockLayout(dockSide.value, dockWidth.value, dockOnTop.value, dockOpacity.value);
    } catch (err) {
      Toast.warning(err.message || "贴边模式没能应用，请再选一次。");
    }
  }
}

function normalizeDockOpacity(value) {
  const n = Number(value) || 100;
  if (n >= 100) return 100;
  if (n >= 95) return 95;
  if (n >= 90) return 90;
  return 85;
}

async function changeDockSide(value) {
  const next = value || "off";
  dockSide.value = next;
  showDockSettings.value = next === "off";
  try {
    await api.setDockPref(next, dockWidth.value, dockOnTop.value, dockOpacity.value);
    await applyDockLayout(next, dockWidth.value, dockOnTop.value, dockOpacity.value);
    if (next === "off") {
      Toast.success("已恢复常规窗口");
    } else {
      ensureDockSelection();
      Toast.success(next === "left" ? "已贴在屏幕左侧" : "已贴在屏幕右侧");
    }
  } catch (err) {
    Toast.warning(err.message || "切换窗口模式失败");
  }
}

async function changeDockOnTop(event) {
  dockOnTop.value = isChecked(event);
  if (!isDocked.value) return;
  try {
    await api.setDockPref(dockSide.value, dockWidth.value, dockOnTop.value, dockOpacity.value);
    await applyDockLayout(dockSide.value, dockWidth.value, dockOnTop.value, dockOpacity.value);
  } catch (err) {
    Toast.warning(err.message || "置顶设置失败");
  }
}

async function changeDockOpacity(value) {
  dockOpacity.value = normalizeDockOpacity(value);
  try {
    await api.setDockPref(dockSide.value, dockWidth.value, dockOnTop.value, dockOpacity.value);
    if (isDocked.value) {
      await applyWindowOpacity(dockOpacity.value);
    }
  } catch (err) {
    Toast.warning(err.message || "透明度设置失败");
  }
}

async function changeAnswerDisplay(value) {
  answerShowReason.value = value === "reason";
  try {
    await api.setDisplayPref(answerShowReason.value, answerFontSize.value);
  } catch (err) {
    Toast.warning(err.message || "显示设置保存失败");
  }
}

async function changeAnswerFontSize(value) {
  const next = value === "small" || value === "large" ? value : "medium";
  answerFontSize.value = next;
  try {
    await api.setDisplayPref(answerShowReason.value, next);
  } catch (err) {
    Toast.warning(err.message || "字号设置保存失败");
  }
}

function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function login() {
  error.value = "";
  loggingIn.value = true;
  status.value = "请在弹出的窗口登录，成功后会自动保存。";
  try {
    await api.beginLogin(Boolean(accountName.value));
    let resp = { pending: true };
    for (let attempt = 0; attempt < 240 && resp.pending; attempt += 1) {
      await wait(500);
      resp = await api.loginStatus();
    }
    if (resp.pending) throw new Error("登录窗口等待超时。需要登录时再点一次。");
    if (!resp.ok) throw new Error(resp.error || "没有保存登录");
    accountName.value = resp.name || "已登录";
    status.value = "已保存登录：" + accountName.value + "。现在可以获取答案。";
    Toast.success("登录已保存");
  } catch (err) {
    const message = err.message || String(err);
    error.value = message;
    status.value = message;
    try {
      const data = await api.loadSettings();
      accountName.value = data.name || "";
    } catch (ignore) {
      /* 账号显示保持原样 */
    }
  } finally {
    loggingIn.value = false;
  }
}

function chooseProvider(value) {
  providerKeys.value = { ...providerKeys.value, [provider.value]: apiKey.value };
  provider.value = value;
  modelOptions.value = [];
  modelHint.value = "";
  connectHint.value = "";
  usageRows.value = [];
  usageNote.value = "";
  usageConsole.value = "";
  usageSupported.value = false;
  apiKey.value = providerKeys.value[value] || "";
  const found = providers.value.find((item) => item.id === value);
  if (!found) return;
  modelName.value = found.model || "";
  baseUrl.value = found.url || "";
}

async function fetchModels() {
  error.value = "";
  modelHint.value = "";
  const found = currentProvider.value;
  if (found && found.needsKey && !String(apiKey.value || "").trim()) {
    modelHint.value = `请先填写${found.name}的 API Key，再获取模型列表。`;
    Toast.warning(modelHint.value);
    return;
  }
  loadingModels.value = true;
  try {
    const data = await api.listModels(provider.value, baseUrl.value, apiKey.value);
    if (!data.ok) throw new Error(data.error || "没有获取到模型");
    modelOptions.value = data.models || [];
    if (!modelName.value && modelOptions.value.length) modelName.value = modelOptions.value[0];
    Toast.success(`已获取 ${modelOptions.value.length} 个模型`);
  } catch (err) {
    modelOptions.value = [];
    const message = err.message || String(err);
    modelHint.value = message;
    error.value = message;
    Toast.warning(message);
  } finally {
    loadingModels.value = false;
  }
}

async function openUsageConsole() {
  if (!usageConsole.value) return;
  try {
    await api.openUrl(usageConsole.value);
  } catch (err) {
    window.open(usageConsole.value, "_blank");
  }
}

async function fetchUsage() {
  usageRows.value = [];
  usageNote.value = "";
  usageConsole.value = "";
  usageSupported.value = false;
  const found = currentProvider.value;
  if (found && found.needsKey && !String(apiKey.value || "").trim()) {
    usageNote.value = `请先填写${found.name}的 API Key，再查询用量。`;
    Toast.warning(usageNote.value);
    return;
  }
  loadingUsage.value = true;
  try {
    const data = await api.queryUsage(provider.value, baseUrl.value, apiKey.value);
    if (!data.ok) throw new Error(data.error || "查询失败");
    usageRows.value = data.rows || [];
    usageNote.value = data.note || "";
    usageConsole.value = data.consoleUrl || "";
    usageSupported.value = !!data.supported;
    if (data.supported && usageRows.value.length) {
      Toast.success("用量已更新");
    } else if (usageNote.value) {
      Toast.info(usageNote.value);
    }
  } catch (err) {
    usageNote.value = err.message || String(err);
    Toast.warning(usageNote.value);
  } finally {
    loadingUsage.value = false;
  }
}

async function testConnection() {
  connectHint.value = "";
  const found = currentProvider.value;
  if (!String(modelName.value || "").trim()) {
    connectOk.value = false;
    connectHint.value = "请先填写模型名称，再测试连接。";
    Toast.warning(connectHint.value);
    return;
  }
  if (found && found.needsKey && !String(apiKey.value || "").trim()) {
    connectOk.value = false;
    connectHint.value = `请先填写${found.name}的 API Key，再测试连接。`;
    Toast.warning(connectHint.value);
    return;
  }
  testingLink.value = true;
  try {
    const data = await api.testModel(provider.value, baseUrl.value, apiKey.value, modelName.value);
    if (!data.ok) throw new Error(data.error || "连接失败");
    connectOk.value = true;
    connectHint.value = `${data.name || found?.name || "模型"} 已连通，可以使用 ${data.model}。`;
    Toast.success("连接成功");
  } catch (err) {
    connectOk.value = false;
    connectHint.value = err.message || String(err);
    Toast.warning(connectHint.value);
  } finally {
    testingLink.value = false;
  }
}

async function downloadUpdate() {
  const url = updateInfo.value && updateInfo.value.url;
  if (!url) return;
  try {
    await api.openUrl(url);
  } catch (err) {
    window.open(url, "_blank");
  }
}

function applyUpdateCheck(info) {
  if (!info) return;
  if (info.update) {
    updateInfo.value = info;
    updateCheckFailed.value = "";
    return;
  }
  updateInfo.value = null;
  if (info.checkOk === false && info.checkMessage) {
    updateCheckFailed.value = info.checkMessage;
  } else {
    updateCheckFailed.value = "";
  }
}

async function runUpdateCheck(options = {}) {
  const toast = options.toast === true;
  const clearFailed = options.clearFailed !== false;
  if (checkingUpdate.value) return;
  checkingUpdate.value = true;
  if (clearFailed) updateCheckFailed.value = "";
  try {
    if (!appVersionText.value) {
      appVersionText.value = await api.appVersion();
    }
    const info = await api.checkUpdate(appVersionText.value);
    applyUpdateCheck(info);
    if (toast) {
      if (info && info.update) {
        Toast.success(`发现新版本 ${info.latest}`);
      } else if (info && info.checkOk === false) {
        Toast.warning(info.checkMessage || "检查更新失败");
      } else {
        Toast.success(`当前已是最新版本（v${appVersionText.value}）`);
      }
    }
  } catch (err) {
    updateCheckFailed.value = "检查更新失败，请确认本机答题服务正常。";
    if (toast) Toast.warning(updateCheckFailed.value);
  } finally {
    checkingUpdate.value = false;
  }
}

function manualUpdateCheck() {
  runUpdateCheck({ toast: true, clearFailed: true });
}

function retryUpdateCheck() {
  runUpdateCheck({ toast: true, clearFailed: true });
}

onMounted(() => {
  loadSettings();
  api
    .appVersion()
    .then((current) => {
      appVersionText.value = current || "";
      return runUpdateCheck({ toast: false, clearFailed: true });
    })
    .catch(() => {
      updateCheckFailed.value = "检查更新失败，请确认本机答题服务正常。";
    });
  registerCopyHotkey(() => copyHotkeyAnswer()).catch(() => {});
  refreshCheckpointPending();
});

onUnmounted(() => {
  unregisterCopyHotkey().catch(() => {});
});

function displayParts(question) {
  if (Array.isArray(question.parts) && question.parts.length) {
    return question.parts;
  }
  return [{ label: "", text: question.answer || "" }];
}

async function copyText(value) {
  const text = String(value || "").trim();
  if (!text) {
    Toast.warning("这一空没有答案");
    return;
  }
  try {
    await navigator.clipboard.writeText(text);
    Toast.success("已复制");
  } catch (err) {
    error.value = "复制失败，请手动选择这段答案";
  }
}

async function openKeyPage() {
  try {
    await api.openUrl(keyPage);
  } catch (err) {
    window.open(keyPage, "_blank");
  }
}

function isChecked(event) {
  if (typeof event === "boolean") return event;
  return !!(event && event.target && event.target.checked);
}

function toggleFile(name, event) {
  const checked = isChecked(event);
  if (checked) {
    if (!selectedFiles.value.includes(name)) {
      selectedFiles.value = [...selectedFiles.value, name];
    }
    return;
  }
  selectedFiles.value = selectedFiles.value.filter((item) => item !== name);
}

async function changeSave(event) {
  const enabled = isChecked(event);
  saveAnswers.value = enabled;
  confirmAll.value = false;
  const data = await api.setSaveAnswers(enabled);
  saveAnswers.value = data.saveAnswers !== false;
  answerFiles.value = data.files || [];
  Toast.success(saveAnswers.value ? "之后会写入答案文件夹" : "之后不再写入答案文件");
}

async function refreshFiles() {
  const data = await api.listAnswers();
  answerFiles.value = data.files || [];
  selectedFiles.value = selectedFiles.value.filter((name) =>
    answerFiles.value.some((file) => file.name === name)
  );
}

async function removeSelected() {
  if (!selectedFiles.value.length) {
    Toast.warning("先勾选要删除的文件");
    return;
  }
  const data = await api.deleteAnswers([...selectedFiles.value]);
  answerFiles.value = data.files || [];
  selectedFiles.value = [];
  confirmAll.value = false;
  Toast.success("已删除选中的答案文件");
}

async function removeAll() {
  if (!confirmAll.value) {
    confirmAll.value = true;
    return;
  }
  const data = await api.deleteAllAnswers();
  answerFiles.value = data.files || [];
  selectedFiles.value = [];
  confirmAll.value = false;
  Toast.success("已删除答案文件夹");
}

function paperTitle(paper) {
  if (!paper.ok) return paper.title || "这份作业没有取到";
  return paper.course ? `${paper.course} · ${paper.title}` : paper.title || "作业";
}

function failBannerType(kind) {
  if (kind === "rate_limit" || kind === "partial") return "warning";
  return "danger";
}

function paperFailText(paper) {
  if (!paper) return "";
  if (paper.failTitle && paper.error && paper.error !== paper.failTitle) {
    return `${paper.failTitle}：${paper.error}`;
  }
  return paper.failTitle || paper.checkpointHint || paper.error || "";
}

async function refreshCheckpointPending() {
  if (!url.value.trim()) {
    pendingRetryCount.value = 0;
    pendingRetryHint.value = "";
    return;
  }
  try {
    const data = await api.fetchCheckpointPending(
      url.value,
      provider.value,
      modelName.value,
      baseUrl.value,
      thinking.value && supportsThinking.value
    );
    pendingRetryCount.value = data.count || 0;
    const items = data.items || [];
    if (!items.length) {
      pendingRetryHint.value = "";
      return;
    }
    if (items.length === 1) {
      const item = items[0];
      pendingRetryHint.value = `1 份未答全（${item.answered}/${item.total} 题${item.failedGroups ? `，${item.failedGroups} 组失败` : ""}）`;
    } else {
      pendingRetryHint.value = `${items.length} 份未答全，可只重试失败部分`;
    }
  } catch {
    pendingRetryCount.value = 0;
    pendingRetryHint.value = "";
  }
}

async function clearCheckpoint() {
  try {
    await api.clearSolveCheckpoint(url.value);
    Toast.success(url.value.trim() ? "已清除地址框里作业的断点和题干缓存。" : "已清除本机全部断点和题干缓存。");
    await refreshCheckpointPending();
  } catch (err) {
    Toast.warning(err.message || "清除断点失败");
  }
}

function resolveFullFetchConfirm(ok) {
  fullFetchConfirmOpen.value = false;
  const done = fullFetchConfirmPending;
  fullFetchConfirmPending = null;
  if (done) done(!!ok);
}

function askFullFetchConfirm(items) {
  return new Promise((resolve) => {
    fullFetchConfirmItems.value = items || [];
    fullFetchConfirmOpen.value = true;
    fullFetchConfirmPending = resolve;
  });
}

async function runSolve(retryFailedOnly = false) {
  error.value = "";
  batchFailKind.value = "";
  batchFailTitle.value = "";
  batchFailNext.value = "";
  papers.value = [];
  sessionUsageText.value = "";
  sessionCacheText.value = "";
  if (!url.value.trim()) {
    error.value = "请输入作业页地址，每行一个。";
    return;
  }
  if (retryFailedOnly) {
    await refreshCheckpointPending();
    if (!pendingRetryCount.value) {
      Toast.warning("当前没有需要续答的作业。");
      return;
    }
    resumeCheckpoint.value = true;
  } else {
    try {
      const check = await api.fetchFullFetchConfirm(
        url.value,
        provider.value,
        modelName.value,
        baseUrl.value,
        thinking.value && supportsThinking.value,
        resumeCheckpoint.value,
        false
      );
      if (check.needConfirm && check.items && check.items.length) {
        const ok = await askFullFetchConfirm(check.items);
        if (!ok) return;
      }
    } catch {
      /* 检查失败不阻断获取 */
    }
  }
  loading.value = true;
  status.value = retryFailedOnly ? "正在仅重试未答全的作业…" : "正在同时获取每一份作业…";
  try {
    const resp = await api.solveBatch(
      url.value,
      apiKey.value,
      provider.value,
      modelName.value,
      baseUrl.value,
      thinking.value && supportsThinking.value,
      (message) => {
        status.value = message;
      },
      resumeCheckpoint.value,
      retryFailedOnly
    );
    if (!resp) throw new Error("没有返回结果");
    papers.value = resp.papers || [];
    page.value = 1;
    selectedQuestionN.value = null;
    selectedPartIndex.value = 0;
    if (isDocked.value) ensureDockSelection();
    sessionUsageText.value = resp.usageText || "";
    sessionCacheText.value = resp.cacheHint || "";
    status.value = resp.summary || "";
    if (resp.cacheHint && !resp.changedQuestions && resp.reusedQuestions) {
      Toast.success(resp.cacheHint);
    }
    batchFailKind.value = resp.failKind || "";
    batchFailTitle.value = resp.failTitle || "";
    batchFailNext.value = resp.failNext || "";
    await refreshFiles();
    await refreshCheckpointPending();
    if (!resp.ok && !papers.value.length) {
      error.value = resp.failTitle
        ? `${resp.failTitle}：${resp.error || "没有返回结果"}`
        : resp.error || "没有返回结果";
    }
  } catch (err) {
    error.value = err.message || String(err);
  } finally {
    loading.value = false;
  }
}

async function start() {
  await runSolve(false);
}

async function startRetryFailed() {
  await runSolve(true);
}

watch([url, provider, modelName, baseUrl, thinking], () => {
  refreshCheckpointPending();
});
</script>

<template>
  <div ref="scroller" class="page" :class="pageDisplayClasses">
    <div class="shell">
      <header class="brand">
        <img class="logo" src="/icon.png" alt="" />
        <div class="brand-copy">
          <div class="brand-title-row">
            <h1>智慧树答题</h1>
            <span v-if="appVersionText" class="app-version">v{{ appVersionText }}</span>
          </div>
          <p v-if="!isDocked">多份作业一次只显示一份，用分页切换。是否保存答案文件可以自己选。</p>
          <p v-else class="dock-tagline">贴边模式：用窄栏上一题/下一题或题号跳转对照答案；{{ hotkeyHint }} 复制当前空。</p>
        </div>
        <div class="brand-actions">
          <Button v-if="isDocked" size="small" @click="showDockSettings = !showDockSettings">
            {{ showDockSettings ? "收起设置" : "设置" }}
          </Button>
          <Button size="small" :loading="checkingUpdate" @click="manualUpdateCheck">检查更新</Button>
          <Button @click="helpOpen = true">帮助</Button>
        </div>
      </header>

      <div v-if="updateInfo" class="update-bar">
        <span>发现新版本 {{ updateInfo.latest }}，当前是 {{ updateInfo.current }}。</span>
        <Button size="small" theme="solid" type="primary" @click="downloadUpdate">下载更新</Button>
        <Button size="small" @click="updateInfo = null">关闭</Button>
      </div>
      <div v-if="updateCheckFailed" class="update-bar update-bar--warn">
        <span>{{ updateCheckFailed }}</span>
        <Button size="small" :loading="checkingUpdate" @click="retryUpdateCheck">重试</Button>
        <Button size="small" @click="updateCheckFailed = ''">关闭</Button>
      </div>

      <Card class="form-card dock-card" :bodyStyle="{ padding: '18px 18px 14px' }">
        <div class="field">
          <div class="field-label">贴边做题</div>
          <Select
            :value="dockSide"
            :optionList="dockModeOptions"
            style="width: 100%"
            @change="changeDockSide"
          />
          <div class="save-hint">
            贴在左或右侧并可选置顶，方便浏览器做题时对照答案。在软件里点一下题目或某一空，按
            {{ hotkeyHint }} 可复制到剪贴板，浏览器可保持焦点。
          </div>
        </div>
        <div v-if="isDocked" class="save-row dock-top-row">
          <div>
            <div class="field-label">窗口置顶</div>
            <div class="save-hint">关闭后仍贴边，但可能被其他窗口挡住。</div>
          </div>
          <Switch :checked="dockOnTop" @change="changeDockOnTop" />
        </div>
        <div v-if="isDocked" class="field display-field">
          <div class="field-label">窗口透明度</div>
          <Select
            :value="dockOpacity"
            :optionList="dockOpacityOptions"
            style="width: 100%"
            @change="changeDockOpacity"
          />
          <div class="save-hint">略透明可看到背后页面，文字可能更难辨认。恢复常规窗口会自动回到不透明。</div>
        </div>
        <div class="field display-field">
          <div class="field-label">答案显示</div>
          <Select
            :value="answerDisplayMode"
            :optionList="answerDisplayOptions"
            style="width: 100%"
            @change="changeAnswerDisplay"
          />
          <div class="save-hint">
            仅答案：常规窗口仍显示题干；贴边时只保留题号与答案行。含解析：在答案下方显示模型给出的说明。
          </div>
        </div>
        <div class="field display-field">
          <div class="field-label">答案字号</div>
          <Select
            :value="answerFontSize"
            :optionList="answerFontOptions"
            style="width: 100%"
            @change="changeAnswerFontSize"
          />
        </div>
      </Card>

      <Card v-show="!isDocked || showDockSettings" class="form-card" :bodyStyle="{ padding: '18px 18px 14px' }">
        <div class="field">
          <div class="field-label">作业页地址</div>
          <TextArea
            :value="url"
            :rows="5"
            placeholder="每行粘贴一个作业做题页地址。普通作业页和 AI 教学中心答题页都可以。"
            @change="(value) => (url = value)"
          />
        </div>
        <div class="field">
          <div class="field-label">模型</div>
          <Select :value="provider" :optionList="providerOptions" style="width: 100%" @change="chooseProvider" />
          <div class="save-hint">{{ currentProvider?.hint }}</div>
        </div>
        <div v-if="provider === 'custom' || provider === 'ollama' || provider === 'lmstudio' || provider === 'doubao'" class="field">
          <div class="field-label">接口地址</div>
          <Input :value="baseUrl" placeholder="https:// 或 http://127.0.0.1" @change="(value) => (baseUrl = value)" />
        </div>
        <div class="field">
          <div class="field-label">模型名称</div>
          <div class="model-row">
            <Input :value="modelName" placeholder="例如 deepseek-flash、qwen-plus" @change="(value) => (modelName = value)" />
            <Button :loading="loadingModels" @click="fetchModels">获取模型列表</Button>
          </div>
          <div v-if="modelHint" class="model-hint">{{ modelHint }}</div>
          <div v-if="supportsThinking" class="save-row thinking-row">
            <div>
              <div class="field-label">思考模式</div>
              <div v-if="thinking" class="model-hint">开启后模型会先思考再作答，获取答案会花更多时间。</div>
            </div>
            <Switch :checked="thinking" @change="(value) => (thinking = isChecked(value))" />
          </div>
          <Select
            v-if="modelOptions.length"
            :value="modelName"
            :optionList="modelOptions.map((name) => ({ value: name, label: name }))"
            style="width: 100%; margin-top: 8px"
            @change="(value) => (modelName = value)"
          />
        </div>
        <div class="field">
          <div class="field-label">{{ currentProvider?.needsKey ? "API Key" : "API Key（本地模型可以不填）" }}</div>
          <Input
            :value="apiKey"
            mode="password"
            placeholder="sk-..."
            @change="(value) => (apiKey = value)"
          />
          <div class="model-row" style="margin-top: 8px">
            <Button :loading="testingLink" @click="testConnection">测试连接</Button>
            <Button :loading="loadingUsage" @click="fetchUsage">查询用量</Button>
          </div>
          <div v-if="connectHint" class="model-hint" :class="{ 'is-ok': connectOk }">{{ connectHint }}</div>
          <div v-if="usageRows.length || usageNote" class="usage-panel">
            <div class="usage-head">
              <span class="field-label">用量 / 余额</span>
              <Button v-if="usageConsole" size="small" theme="borderless" type="primary" @click="openUsageConsole">
                打开控制台
              </Button>
            </div>
            <div v-for="(item, index) in usageRows" :key="index" class="usage-row">
              <span class="usage-label">{{ item.label }}</span>
              <span class="usage-value">{{ item.value }}</span>
              <span v-if="item.hint" class="usage-hint">{{ item.hint }}</span>
            </div>
            <div v-if="usageNote" class="model-hint" :class="{ 'is-ok': usageSupported && usageRows.length }">
              {{ usageNote }}
            </div>
          </div>
        </div>
        <div class="save-row checkpoint-row">
          <div>
            <div class="field-label">断点续答</div>
            <div class="save-hint">
              每 4 题一组请求模型。中途失败或关闭软件后，开启此项再获取会跳过已成功的题组。同一作业题干未变会沿用上次答案，只重做变更题。
              <span v-if="pendingRetryHint" class="pending-retry-hint">{{ pendingRetryHint }}</span>
            </div>
          </div>
          <Switch :checked="resumeCheckpoint" @change="(value) => (resumeCheckpoint = isChecked(value))" />
        </div>
        <div class="account">{{ accountName ? "当前账号：" + accountName : "当前账号：未登录" }}</div>
        <div class="actions">
          <Button theme="solid" type="primary" :loading="loggingIn" @click="login">
            {{ accountName ? "切换账号" : "登录账号" }}
          </Button>
          <Button theme="solid" type="primary" :loading="loading" :disabled="loggingIn" @click="start">获取答案</Button>
          <Button
            :loading="loading"
            :disabled="loggingIn || !pendingRetryCount"
            @click="startRetryFailed"
          >
            仅重试失败
          </Button>
          <Button :disabled="loading" @click="clearCheckpoint">清除断点</Button>
        </div>
        <div class="status">{{ status }}</div>
        <div v-if="sessionCacheText" class="cache-session">{{ sessionCacheText }}</div>
        <div v-if="sessionUsageText" class="usage-session">{{ sessionUsageText }}</div>
      </Card>

      <Card v-show="!isDocked || showDockSettings" class="form-card" :bodyStyle="{ padding: '18px 18px 14px' }">
        <div class="save-row">
          <div>
            <div class="field-label">保存到答案文件夹</div>
            <div class="save-hint">
              {{ saveAnswers ? "获取答案后，每份作业写成一个 txt。" : "关闭后只在窗口里显示，不写文件。" }}
            </div>
          </div>
          <Switch :checked="saveAnswers" @change="changeSave" />
        </div>
        <div v-if="answerFiles.length" class="file-list">
          <Checkbox
            v-for="file in visibleFiles"
            :key="file.name"
            :checked="selectedFiles.includes(file.name)"
            @change="(event) => toggleFile(file.name, event)"
          >
            {{ file.name }}
          </Checkbox>
          <Button v-if="answerFiles.length > 3" theme="borderless" type="primary" @click="showAllFiles = !showAllFiles">
            {{ showAllFiles ? "收起" : `显示全部（${answerFiles.length}）` }}
          </Button>
        </div>
        <div v-else class="save-hint">答案文件夹里还没有文件。</div>
        <div class="actions file-actions">
          <Button :disabled="!selectedFiles.length" @click="removeSelected">删除选中</Button>
          <Button type="danger" :disabled="!answerFiles.length" @click="removeAll">
            {{ confirmAll ? "确定删除全部" : "删除全部答案" }}
          </Button>
        </div>
      </Card>

      <Banner v-if="error" class="alert" :type="failBannerType(batchFailKind)" :description="error" />
      <p v-if="error && batchFailNext" class="fail-next">下一步：{{ batchFailNext }}</p>

      <section v-if="currentPaper" ref="paperAnchor" class="paper">
        <Pagination
          v-if="papers.length > 1"
          class="pager"
          :total="papers.length"
          :pageSize="1"
          :currentPage="page"
          size="small"
          @pageChange="showPage"
        />
        <div class="paper-head">
          <div class="paper-copy">
            <strong>{{ paperTitle(currentPaper) }}</strong>
            <span v-if="currentPaper.ok">第 {{ page }} / {{ papers.length }} 份 · {{ currentPaper.questions.length }} 题<span v-if="currentPaper.file"> · 答案/{{ currentPaper.file }}</span></span>
            <span v-else-if="currentPaper.questions?.length">第 {{ page }} / {{ papers.length }} 份 · 已显示 {{ currentPaper.questions.length }} 题（未答全）</span>
            <span v-else class="paper-url">第 {{ page }} / {{ papers.length }} 份 · {{ currentPaper.url }}</span>
          </div>
          <Button v-if="currentPaper.ok" size="small" @click="copyText(currentPaper.text)">复制本份</Button>
        </div>
        <Banner
          v-if="!currentPaper.ok && paperFailText(currentPaper)"
          class="alert"
          :type="failBannerType(currentPaper.failKind)"
          :description="paperFailText(currentPaper)"
        />
        <p v-if="!currentPaper.ok && currentPaper.failNext" class="fail-next">下一步：{{ currentPaper.failNext }}</p>
        <div v-if="isDocked && currentPaper.questions?.length && dockQuestions.length" class="dock-nav">
          <Button size="small" :disabled="dockQuestionIndex <= 0" @click="goPrevQuestion">上一题</Button>
          <Select
            :value="dockFocusedQuestion?.n"
            :optionList="dockQuestionOptions"
            class="dock-nav-select"
            size="small"
            @change="jumpDockQuestion"
          />
          <span class="dock-nav-pos">{{ dockQuestionIndex + 1 }} / {{ dockQuestions.length }}</span>
          <Button size="small" :disabled="dockQuestionIndex >= dockQuestions.length - 1" @click="goNextQuestion">
            下一题
          </Button>
        </div>
        <div
          v-if="isDocked && currentPaper.questions?.length && dockFocusedParts.length > 1"
          class="dock-part-nav"
        >
          <Button size="small" :disabled="selectedPartIndex <= 0" @click="goPrevPart">上一空</Button>
          <span class="dock-nav-pos">空 {{ selectedPartIndex + 1 }} / {{ dockFocusedParts.length }}</span>
          <Button
            size="small"
            :disabled="selectedPartIndex >= dockFocusedParts.length - 1"
            @click="goNextPart"
          >
            下一空
          </Button>
        </div>
        <div v-if="isDocked && currentPaper.questions?.length && dockQuestions.length > 1" class="dock-list-toggle">
          <Button size="small" theme="borderless" type="primary" @click="dockShowAllQuestions = !dockShowAllQuestions">
            {{ dockShowAllQuestions ? "收起题目列表" : "展开全部题目" }}
          </Button>
        </div>
        <div v-if="currentPaper.questions?.length" class="q-list">
          <Card
            v-for="question in visibleQuestions"
            :key="`${page}-${question.n}`"
            class="q-card"
            :class="{ 'q-card--selected': isQuestionSelected(question) }"
            :bodyStyle="{ padding: '14px 16px' }"
            @click="selectQuestion(question, 0)"
          >
            <div class="q-head">
              <span class="q-no">{{ question.n }}.</span>
              <Tag size="small" color="blue">{{ question.type }}</Tag>
              <Tag v-if="question.score" size="small">{{ question.score }}分</Tag>
            </div>
            <div v-if="showQuestionStem()" class="stem">{{ question.stem }}</div>
            <div v-if="showQuestionOptions(question)" class="options">
              <div
                v-for="option in question.options"
                :key="option"
                class="option"
                :class="{ 'is-hit': isHit(question, option) }"
              >
                <span v-if="isHit(question, option)" class="option-mark">正确</span>
                {{ option }}
              </div>
            </div>
            <div
              v-for="(part, index) in displayParts(question)"
              :key="index"
              class="answer"
              :class="{ 'answer--selected': isQuestionSelected(question) && selectedPartIndex === index }"
              @click.stop="selectQuestion(question, index)"
            >
              <span class="answer-text">
                <template v-if="part.label">{{ part.label }} </template>
                <template v-else>答案：</template>
                {{ part.text || "（无）" }}
              </span>
              <Button
                v-if="!question.options.length"
                size="small"
                theme="solid"
                type="primary"
                :disabled="!part.text"
                @click="copyText(part.text)"
              >
                复制
              </Button>
            </div>
            <div v-if="showQuestionReason(question)" class="reason">{{ question.reason }}</div>
          </Card>
        </div>
        <Pagination
          v-if="papers.length > 1"
          class="pager pager-bottom"
          :total="papers.length"
          :pageSize="1"
          :currentPage="page"
          size="small"
          @pageChange="showPage"
        />
      </section>

      <p class="foot">答案由 DeepSeek 生成，提交前请自行核对。</p>
    </div>
    <Modal
      :visible="fullFetchConfirmOpen"
      title="确认再次获取答案"
      :width="520"
      :footer="null"
      @cancel="resolveFullFetchConfirm(false)"
    >
      <p class="confirm-lead">
        以下作业在 24 小时内已经获取过答案。再次获取可能重复消耗模型额度（题干未变的题仍会沿用缓存，但可能仍有新请求）。
      </p>
      <ul class="confirm-url-list">
        <li v-for="(item, idx) in fullFetchConfirmItems" :key="idx">
          <span class="confirm-url">{{ item.url }}</span>
          <span class="confirm-meta">约 {{ item.hoursAgo }} 小时前</span>
        </li>
      </ul>
      <p class="confirm-tip">只是续答未完成的题组时，请用「仅重试失败」，不会弹此确认。</p>
      <div class="confirm-actions">
        <Button @click="resolveFullFetchConfirm(false)">取消</Button>
        <Button theme="solid" type="primary" @click="resolveFullFetchConfirm(true)">仍要获取</Button>
      </div>
    </Modal>

    <Modal :visible="helpOpen" title="帮助" :width="640" :footer="null" @cancel="helpOpen = false">
      <div class="help">
        <h2>获取 DeepSeek API Key</h2>
        <ol>
          <li>打开 DeepSeek 开放平台并登录。没有账号就先注册。</li>
          <li>进入「API keys」页面，点「创建 API key」，填一个名字后创建。</li>
          <li>创建成功后马上复制。Key 以 sk- 开头，关掉窗口后就看不到完整内容了。</li>
          <li>账户里需要有余额。余额用完后，接口会拒绝答题，到开放平台充值后再用。</li>
        </ol>
        <Button size="small" theme="solid" type="primary" @click="openKeyPage">打开 API keys 页面</Button>
        <h2>把 Key 填进软件</h2>
        <ol>
          <li>回到本软件，模型选 DeepSeek，把复制的 Key 粘贴到「API Key」。</li>
          <li>点一次「获取答案」。软件会记住这把 Key，下次打开不用再填。</li>
          <li>要换 Key 时，把输入框里的内容改掉，再点一次「获取答案」。</li>
        </ol>
        <h2>换成其他模型</h2>
        <p>模型可以换成通义千问、智谱、Kimi、豆包、OpenAI、Gemini，也可以用本机的 Ollama 或 LM Studio。这些接口都按同一种对话格式调用。本地模型要先在自己电脑上启动。没有列出的服务，选「自定义接口」，填它的地址和模型名。</p>
        <h2>查询用量</h2>
        <p>填好 API Key 后点「查询用量」，会按当前选的厂商查询余额或套餐额度（和 CC Switch 一样，界面统一、各家接口不同）。DeepSeek、通义、智谱、Kimi 等支持 API 查询；OpenAI、Gemini、豆包等若官方不提供 Key 余额接口，会提示到控制台查看。本地 Ollama / LM Studio 只显示本机状态。</p>
        <h2>怎么使用</h2>
        <ol>
          <li>点「登录账号」，在弹出的窗口登录正在做这份作业的智慧树账号。登录会保存，界面上能看到当前账号。要换人时再点「切换账号」。</li>
          <li>在浏览器打开正在做的作业，复制地址栏整段地址。多份作业就每行粘贴一个地址。普通作业页和 AI 教学中心的答题页都可以。</li>
          <li>点「获取答案」。多份作业会同时拉取、同时解答，只读取题目并给出答案，不会交卷。</li>
          <li>一次只显示一份作业，用分页切换到下一份。选择题会把正确选项标成绿色。填空题按网页上的空分成多行，每行有「复制」。</li>
          <li>打开「保存到答案文件夹」后，每份答案写成一个 txt。关掉后只在窗口里显示，不写文件。已有文件可以勾选删除，或点「删除全部答案」清掉整个文件夹。点「复制本份」只复制这一份。提交前自己核对一遍。</li>
        </ol>
        <h2>贴边做题</h2>
        <p>在「贴边做题」里选贴在屏幕左侧或右侧。窗口会收成窄栏并占满工作区高度，可选「窗口置顶」以免被挡住。贴边时默认只显示题目答案，点「设置」可展开模型与获取答案。下次打开会记住上次模式。切屏是否被平台记录与贴边无关，见 README 说明。</p>
        <h2>检查更新</h2>
        <p>标题旁会显示当前版本号（如 v1.7.6）。打开软件时会自动检查 Gitee 是否有新版本；也可随时点右上角「检查更新」。若网络异常，顶部会出现橙色提示，可点「重试」。</p>
        <h2>快捷键复制（贴边做题）</h2>
        <p>
          获取答案后，在题目区域点一下某道题或某一空（会高亮）。焦点留在浏览器时，按
          <strong>{{ hotkeyHint }}</strong>
          可把当前选中答案写入剪贴板，再到作业页粘贴。选择题复制选项字母组合，填空题复制当前空。
        </p>
        <h2>窄栏导航（贴边做题）</h2>
        <p>
          贴在左或右侧时，答案区上方有「上一题 / 下一题」和下拉选题号，默认只显示当前一题，少在长列表里滚动。多空填空题另有「上一空 / 下一空」。需要对照多题时可点「展开全部题目」。
        </p>
        <h2>答案显示与字号</h2>
        <p>
          在「贴边做题」卡片里可选「仅答案」或「含解析」，以及小/中/大字号。设置会记住，下次打开仍生效。贴边时「仅答案」会隐藏题干与选项，只留题号和答案行，方便窄栏对照。
        </p>
        <h2>窗口透明度（贴边）</h2>
        <p>
          贴在左或右侧时可选 95% / 90% / 85% 略透明，便于同时看到浏览器里的题目。透明度仅 Windows 贴边生效；切回常规窗口会恢复不透明。
        </p>
        <h2>断点续答与仅重试失败</h2>
        <p>
          题目按 4 题一组调用模型。开启「断点续答」后，每组成功会写入本机 checkpoint.json；再次「获取答案」且题干未变时会跳过已答组。失败的题组会单独记录，可点「仅重试失败」只处理未答全的作业、只请求未成功的题组（已完成的作业地址不会重复调模型）。换模型或关闭续答会重新全量请求。答全后断点自动清除，也可点「清除断点」。
        </p>
        <h2>24 小时内再次获取</h2>
        <p>
          同一作业地址在 24 小时内若已完整获取过答案，再次点「获取答案」（非「仅重试失败」）时会先弹窗确认，避免误点重复消耗模型额度。正在续答未答全的作业不会弹窗。
        </p>
        <h2>题干指纹（沿用上次答案）</h2>
        <p>
          每道题按题干和选项做指纹。同一作业再次获取时，未变的题直接沿用上次答案，不消耗模型额度；只把题干有变或尚未缓存的题送给模型。关闭「断点续答」或点「清除断点」会清空缓存并全量重答。
        </p>
        <h2>失败分类提示</h2>
        <p>
          拉题或调模型失败时，会区分登录过期、验证码、请求过频、余额不足、Key 无效、网络、作业地址不匹配等，并给出简短「下一步」。未答全时优先点「仅重试失败」，不必整份重来。
        </p>
        <div class="help-close">
          <Button theme="solid" type="primary" @click="helpOpen = false">知道了</Button>
        </div>
      </div>
    </Modal>
    <BackTop className="to-top" :visibilityHeight="160" :target="scrollTarget">
      <span class="to-top-label">顶部</span>
    </BackTop>
  </div>
</template>
