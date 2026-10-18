<script setup>
import { computed, onMounted, ref } from "vue";
import { BackTop, Banner, Button, Card, Input, Tag, Toast } from "@kousum/semi-ui-vue";

const url = ref("");
const apiKey = ref("");
const scroller = ref(null);
const loading = ref(false);
const loggingIn = ref(false);
const accountName = ref("");
const status = ref("先点登录账号，在弹出的窗口登录。之后获取答案会一直用这个账号。");
const error = ref("");
const course = ref("");
const title = ref("");
const questions = ref([]);
const text = ref("");

const heading = computed(() => {
  if (!title.value) return "";
  return course.value ? `${course.value} · ${title.value}` : title.value;
});

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
    error.value = err.message || String(err);
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

async function copyAnswers() {
  if (!text.value) return;
  try {
    await navigator.clipboard.writeText(text.value);
    Toast.success("答案已复制");
  } catch (err) {
    error.value = "复制失败，请从下方卡片里手动选择";
  }
}

async function start() {
  error.value = "";
  if (!url.value.trim()) {
    error.value = "请输入作业页地址。";
    return;
  }
  if (typeof window.pywebview?.api?.solve !== "function") {
    error.value = "窗口还在准备，请过一两秒再点获取答案。";
    return;
  }
  loading.value = true;
  status.value = "正在拉取题目…";
  try {
    const resp = await window.pywebview.api.solve(url.value.trim(), apiKey.value);
    if (!resp || !resp.ok) throw new Error((resp && resp.error) || "没有返回结果");
    course.value = resp.course || "";
    title.value = resp.title || "";
    questions.value = resp.questions || [];
    text.value = resp.text || "";
    status.value = `已返回 ${questions.value.length} 题，并写入答案.txt`;
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
        <div>
          <h1>智慧树答题</h1>
          <p>输入作业地址，返回答案。用谁的账号登录，就查谁的作业。</p>
        </div>
      </header>

      <Card class="form-card" :bodyStyle="{ padding: '18px 18px 14px' }">
        <div class="field">
          <div class="field-label">作业页地址</div>
          <Input
            :value="url"
            placeholder="https://onlineexamh5new.zhihuishu.com/stuExamWeb.html#/webExamList/dohomework/..."
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
          <Button :disabled="!text" @click="copyAnswers">复制答案</Button>
        </div>
        <div class="status">{{ status }}</div>
      </Card>

      <Banner v-if="error" class="alert" type="danger" :description="error" />

      <div v-if="heading" class="summary">
        <strong>{{ heading }}</strong>
        <span>{{ questions.length }} 题</span>
      </div>

      <div class="q-list">
        <Card
          v-for="question in questions"
          :key="question.n"
          :bodyStyle="{ padding: '14px 16px' }"
        >
          <div class="q-head">
            <span class="q-no">{{ question.n }}.</span>
            <Tag size="small" color="blue">{{ question.type }}</Tag>
            <Tag v-if="question.score" size="small">{{ question.score }}分</Tag>
          </div>
          <div class="stem">{{ question.stem }}</div>
          <div v-if="question.options.length" class="options">
            <span
              v-for="option in question.options"
              :key="option"
              class="option"
              :class="{ 'is-hit': isHit(question, option) }"
            >
              {{ option }}
            </span>
          </div>
          <div class="answer">答案：{{ question.answer || "（无）" }}</div>
          <div v-if="question.reason" class="reason">{{ question.reason }}</div>
        </Card>
      </div>

      <p class="foot">答案由 DeepSeek 生成，提交前请自行核对。</p>
    </div>
    <BackTop className="to-top" :visibilityHeight="160" :target="scrollTarget">
      <span class="to-top-label">顶部</span>
    </BackTop>
  </div>
</template>
