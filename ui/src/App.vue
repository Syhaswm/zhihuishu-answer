<script setup>
import { computed, onMounted, ref } from "vue";
import { BackTop, Banner, Button, Card, Input, Modal, Pagination, Tag, TextArea, Toast } from "@kousum/semi-ui-vue";

const url = ref("");
const apiKey = ref("");
const scroller = ref(null);
const loading = ref(false);
const loggingIn = ref(false);
const accountName = ref("");
const status = ref("先点登录账号，在弹出的窗口登录。之后获取答案会一直用这个账号。");
const error = ref("");
const papers = ref([]);
const page = ref(1);
const paperAnchor = ref(null);
const helpOpen = ref(false);
const keyPage = "https://platform.deepseek.com/api_keys";

const currentPaper = computed(() => papers.value[page.value - 1] || null);

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
  if (!window.pywebview?.api) return;
  const data = await window.pywebview.api.load_settings();
  apiKey.value = data.apiKey || "";
  accountName.value = data.name || "";
  if (data.expired) {
    status.value = "登录已过期。请点「切换账号」重新登录。";
  }
}

async function login() {
  error.value = "";
  if (typeof window.pywebview?.api?.begin_login !== "function") {
    error.value = "窗口还在准备，请过一两秒再点登录账号。";
    return;
  }
  loggingIn.value = true;
  status.value = "请在弹出的窗口登录，成功后会自动保存。";
  try {
    const resp = await window.pywebview.api.begin_login(Boolean(accountName.value));
    if (!resp || !resp.ok) throw new Error((resp && resp.error) || "没有保存登录");
    accountName.value = resp.name || "已登录";
    status.value = "已保存登录：" + accountName.value + "。现在可以获取答案。";
    Toast.success("登录已保存");
  } catch (err) {
    const message = err.message || String(err);
    error.value = message;
    status.value = message;
    try {
      const data = await window.pywebview.api.load_settings();
      accountName.value = data.name || "";
    } catch (ignore) {
      /* 账号显示保持原样 */
    }
  } finally {
    loggingIn.value = false;
  }
}

onMounted(() => {
  window.onSolveProgress = (message) => {
    status.value = message;
  };
  if (window.pywebview?.api) {
    loadSettings();
    return;
  }
  window.addEventListener("pywebviewready", loadSettings, { once: true });
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
  if (typeof window.pywebview?.api?.open_url === "function") {
    await window.pywebview.api.open_url(keyPage);
    return;
  }
  window.open(keyPage, "_blank");
}

function paperTitle(paper) {
  if (!paper.ok) return paper.title || "这份作业没有取到";
  return paper.course ? `${paper.course} · ${paper.title}` : paper.title || "作业";
}

async function start() {
  error.value = "";
  papers.value = [];
  if (!url.value.trim()) {
    error.value = "请输入作业页地址，每行一个。";
    return;
  }
  if (typeof window.pywebview?.api?.solve_batch !== "function") {
    error.value = "窗口还在准备，请过一两秒再点获取答案。";
    return;
  }
  loading.value = true;
  status.value = "正在同时获取每一份作业…";
  try {
    const resp = await window.pywebview.api.solve_batch(url.value, apiKey.value);
    if (!resp) throw new Error("没有返回结果");
    papers.value = resp.papers || [];
    page.value = 1;
    status.value = resp.summary || "";
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
  <div ref="scroller" class="page">
    <div class="shell">
      <header class="brand">
        <img class="logo" src="/icon.png" alt="" />
        <div class="brand-copy">
          <h1>智慧树答题</h1>
          <p>多份作业一次只显示一份，用分页切换。每份答案分开保存。</p>
        </div>
        <Button @click="helpOpen = true">帮助</Button>
      </header>

      <Card class="form-card" :bodyStyle="{ padding: '18px 18px 14px' }">
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
          <div class="field-label">DeepSeek API Key</div>
          <Input
            :value="apiKey"
            mode="password"
            placeholder="sk-..."
            @change="(value) => (apiKey = value)"
          />
        </div>
        <div class="account">{{ accountName ? "当前账号：" + accountName : "当前账号：未登录" }}</div>
        <div class="actions">
          <Button theme="solid" type="primary" :loading="loggingIn" @click="login">
            {{ accountName ? "切换账号" : "登录账号" }}
          </Button>
          <Button theme="solid" type="primary" :loading="loading" :disabled="loggingIn" @click="start">获取答案</Button>
        </div>
        <div class="status">{{ status }}</div>
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
            <span v-if="currentPaper.ok">第 {{ page }} / {{ papers.length }} 份 · {{ currentPaper.questions.length }} 题 · 答案/{{ currentPaper.file }}</span>
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
          <li>回到本软件，把复制的 Key 粘贴到「DeepSeek API Key」。</li>
          <li>点一次「获取答案」。软件会记住这把 Key，下次打开不用再填。</li>
          <li>要换 Key 时，把输入框里的内容改掉，再点一次「获取答案」。</li>
        </ol>
        <h2>怎么使用</h2>
        <ol>
          <li>点「登录账号」，在弹出的窗口登录正在做这份作业的智慧树账号。登录会保存，界面上能看到当前账号。要换人时再点「切换账号」。</li>
          <li>在浏览器打开正在做的作业，复制地址栏整段地址。多份作业就每行粘贴一个地址。普通作业页和 AI 教学中心的答题页都可以。</li>
          <li>点「获取答案」。多份作业会同时拉取、同时解答，只读取题目并给出答案，不会交卷。</li>
          <li>一次只显示一份作业，用分页切换到下一份。选择题会把正确选项标成绿色。填空题按网页上的空分成多行，每行有「复制」。</li>
          <li>每份答案单独保存在程序旁边的「答案」文件夹里，文件名是作业名称。点「复制本份」只复制这一份。提交前自己核对一遍。</li>
        </ol>
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
