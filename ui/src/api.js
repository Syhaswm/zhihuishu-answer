const API = "http://127.0.0.1:8765";
let appToken = "";

async function getToken() {
  if (appToken) return appToken;
  if (window.__ZHS_TOKEN__) {
    appToken = window.__ZHS_TOKEN__;
    return appToken;
  }
  try {
    const { invoke } = await import("@tauri-apps/api/core");
    appToken = await invoke("api_token");
  } catch (err) {
    appToken = "";
  }
  return appToken;
}

async function signedHeaders(method, path, body, extra) {
  const token = await getToken();
  if (!token) throw new Error("软件口令还没准备好，请重新打开软件。");
  const timestamp = Date.now().toString();
  const payload = `${timestamp}\n${method.toUpperCase()}\n${path}\n${body || ""}`;
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(token),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );
  const mac = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(payload));
  const sign = [...new Uint8Array(mac)].map((item) => item.toString(16).padStart(2, "0")).join("");
  return {
    ...(extra || {}),
    "X-Zhs-Timestamp": timestamp,
    "X-Zhs-Sign": sign,
  };
}

async function request(path, options) {
  const next = { ...(options || {}) };
  const method = next.method || "GET";
  const body = typeof next.body === "string" ? next.body : "";
  next.headers = await signedHeaders(method, path, body, next.headers);
  const response = await fetch(API + path, next);
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
  const body = JSON.stringify({ urls, apiKey });
  const response = await fetch(API + "/api/solve", {
    method: "POST",
    headers: await signedHeaders("POST", "/api/solve", body, {
      "Content-Type": "application/json",
    }),
    body,
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
