<script setup>
import { computed, onMounted, ref } from "vue";
import { BackTop, Banner, Button, Card, Checkbox, Input, Modal, Pagination, Select, Switch, Tag, TextArea, Toast } from "@kousum/semi-ui-vue";
import * as api from "./api";
import { applyDockLayout, DOCK_WIDTH_DEFAULT } from "./dock";

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
const papers = ref([]);
const saveAnswers = ref(true);
const answerFiles = ref([]);
const showAllFiles = ref(false);
const selectedFiles = ref([]);
const confirmAll = ref(false);
const page = ref(1);
const paperAnchor = ref(null);
const helpOpen = ref(false);
const updateInfo = ref(null);
const updateCheckFailed = ref("");
const checkingUpdate = ref(false);
const keyPage = "https://platform.deepseek.com/api_keys";
const dockSide = ref("off");
const dockWidth = ref(DOCK_WIDTH_DEFAULT);
const dockOnTop = ref(true);
const showDockSettings = ref(true);
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

function showPage(next) {
  const total = papers.value.length;
  const value = Math.min(Math.max(Number(next) || 1, 1), total || 1);
  page.value = value;
  paperAnchor.value?.scrollIntoView({ block: "start" });
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
  showDockSettings.value = !isDocked.value;
  if (isDocked.value) {
    try {
      await applyDockLayout(dockSide.value, dockWidth.value, dockOnTop.value);
    } catch (err) {
      Toast.warning(err.message || "贴边模式没能应用，请再选一次。");
    }
  }
}

async function changeDockSide(value) {
  const next = value || "off";
  dockSide.value = next;
  showDockSettings.value = next === "off";
  try {
    await api.setDockPref(next, dockWidth.value, dockOnTop.value);
    await applyDockLayout(next, dockWidth.value, dockOnTop.value);
    if (next === "off") {
      Toast.success("已恢复常规窗口");
    } else {
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
    await api.setDockPref(dockSide.value, dockWidth.value, dockOnTop.value);
    await applyDockLayout(dockSide.value, dockWidth.value, dockOnTop.value);
  } catch (err) {
    Toast.warning(err.message || "置顶设置失败");
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

async function retryUpdateCheck() {
  checkingUpdate.value = true;
  updateCheckFailed.value = "";
  try {
    const current = await api.appVersion();
    const info = await api.checkUpdate(current);
    applyUpdateCheck(info);
    if (info && info.update) {
      Toast.success(`发现新版本 ${info.latest}`);
    } else if (info && info.checkOk === false) {
      Toast.warning(info.checkMessage || "检查更新失败");
    } else {
      Toast.success("当前已是最新版本");
    }
  } catch (err) {
    updateCheckFailed.value = "检查更新失败，请确认本机答题服务正常。";
    Toast.warning(updateCheckFailed.value);
  } finally {
    checkingUpdate.value = false;
  }
}

onMounted(() => {
  loadSettings();
  api
    .appVersion()
    .then((current) => api.checkUpdate(current))
    .then((info) => applyUpdateCheck(info))
    .catch(() => {
      updateCheckFailed.value = "检查更新失败，请确认本机答题服务正常。";
    });
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

async function start() {
  error.value = "";
  papers.value = [];
  sessionUsageText.value = "";
  if (!url.value.trim()) {
    error.value = "请输入作业页地址，每行一个。";
    return;
  }
  loading.value = true;
  status.value = "正在同时获取每一份作业…";
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
      }
    );
    if (!resp) throw new Error("没有返回结果");
    papers.value = resp.papers || [];
    page.value = 1;
    sessionUsageText.value = resp.usageText || "";
    status.value = resp.summary || "";
    await refreshFiles();
    if (!resp.ok && !papers.value.length) {
      error.value = resp.error || "没有返回结果";
    }
  } catch (err) {
    error.value = err.message || String(err);
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <div ref="scroller" class="page" :class="{ 'page--dock': isDocked }">
    <div class="shell">
      <header class="brand">
        <img class="logo" src="/icon.png" alt="" />
        <div class="brand-copy">
          <h1>智慧树答题</h1>
          <p v-if="!isDocked">多份作业一次只显示一份，用分页切换。是否保存答案文件可以自己选。</p>
          <p v-else class="dock-tagline">贴边模式：浏览器做题，这里看答案。点「设置」可改模型或重新获取。</p>
        </div>
        <div class="brand-actions">
          <Button v-if="isDocked" size="small" @click="showDockSettings = !showDockSettings">
            {{ showDockSettings ? "收起设置" : "设置" }}
          </Button>
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
            贴在左或右侧并可选置顶，方便浏览器做题时对照答案。不往网页里注入，和插件无关。
          </div>
        </div>
        <div v-if="isDocked" class="save-row dock-top-row">
          <div>
            <div class="field-label">窗口置顶</div>
            <div class="save-hint">关闭后仍贴边，但可能被其他窗口挡住。</div>
          </div>
          <Switch :checked="dockOnTop" @change="changeDockOnTop" />
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
        <div class="account">{{ accountName ? "当前账号：" + accountName : "当前账号：未登录" }}</div>
        <div class="actions">
          <Button theme="solid" type="primary" :loading="loggingIn" @click="login">
            {{ accountName ? "切换账号" : "登录账号" }}
          </Button>
          <Button theme="solid" type="primary" :loading="loading" :disabled="loggingIn" @click="start">获取答案</Button>
        </div>
        <div class="status">{{ status }}</div>
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

      <Banner v-if="error" class="alert" type="danger" :description="error" />

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
            <span v-else class="paper-url">第 {{ page }} / {{ papers.length }} 份 · {{ currentPaper.url }}</span>
          </div>
          <Button v-if="currentPaper.ok" size="small" @click="copyText(currentPaper.text)">复制本份</Button>
        </div>
        <Banner v-if="!currentPaper.ok" class="alert" type="danger" :description="currentPaper.error" />
        <div v-else class="q-list">
          <Card
            v-for="question in currentPaper.questions"
            :key="`${page}-${question.n}`"
            :bodyStyle="{ padding: '14px 16px' }"
          >
            <div class="q-head">
              <span class="q-no">{{ question.n }}.</span>
              <Tag size="small" color="blue">{{ question.type }}</Tag>
              <Tag v-if="question.score" size="small">{{ question.score }}分</Tag>
            </div>
            <div class="stem">{{ question.stem }}</div>
            <div v-if="question.options.length" class="options">
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
            <div v-for="(part, index) in displayParts(question)" :key="index" class="answer">
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
            <div v-if="question.reason" class="reason">{{ question.reason }}</div>
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
