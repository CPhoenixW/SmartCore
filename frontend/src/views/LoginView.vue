<script setup lang="ts">
import { BrainCircuit } from "@lucide/vue";
import { computed, onMounted, ref } from "vue";
import { useRoute } from "vue-router";
import { authApi } from "@/api/auth";
import { i18n } from "@/locales";

const route = useRoute();
const language = ref<"zh" | "en">((localStorage.getItem("smartcoreLanguage") as "zh" | "en") || "zh");
const mode = ref<"loading" | "setup" | "login" | "register">("loading");
const userId = ref("");
const displayName = ref("");
const password = ref("");
const confirmation = ref("");
const error = ref("");
const busy = ref(false);

const copy = computed(() => language.value === "en" ? {
  title: "Sign in to SmartCore",
  subtitle: mode.value === "setup" ? "Create the initial password for the administrator account." : mode.value === "register" ? "Create a personal SmartCore account." : "Use your user ID and password to continue.",
  userId: mode.value === "register" ? "Login name" : "User ID",
  displayName: "Display name",
  password: "Password",
  confirm: "Confirm password",
  submit: mode.value === "setup" ? "Create password and continue" : mode.value === "register" ? "Create account" : "Sign in",
  register: "Create an account",
  signIn: "Back to sign in",
  setupHint: "The password is stored as a scrypt hash, never as plaintext.",
  mismatch: "The two passwords do not match.",
  minLength: "Password must contain at least 8 characters.",
  language: "中文",
} : {
  title: "登录 SmartCore",
  subtitle: mode.value === "setup" ? "为管理员账户设置初始密码。" : mode.value === "register" ? "创建你的 SmartCore 个人账户。" : "使用用户 ID 和密码进入工作台。",
  userId: mode.value === "register" ? "登录名" : "用户 ID",
  displayName: "显示名称",
  password: "密码",
  confirm: "确认密码",
  submit: mode.value === "setup" ? "设置密码并进入" : mode.value === "register" ? "创建账户" : "登录",
  register: "注册账户",
  signIn: "返回登录",
  setupHint: "密码只会以 scrypt 哈希形式保存，不会保存明文。",
  mismatch: "两次输入的密码不一致。",
  minLength: "密码至少需要 8 个字符。",
  language: "English",
});

function switchLanguage() {
  language.value = language.value === "zh" ? "en" : "zh";
  localStorage.setItem("smartcoreLanguage", language.value);
  i18n.global.locale.value = language.value === "en" ? "en-US" : "zh-CN";
}

function continueToWorkbench() {
  const requested = String(route.query.next ?? "");
  window.location.href = requested.startsWith("/work") ? requested : "/work";
}

function switchMode(next: "login" | "register") {
  mode.value = next;
  error.value = "";
  password.value = "";
  confirmation.value = "";
  if (next === "register") {
    userId.value = "";
    displayName.value = "";
  } else {
    userId.value = "";
  }
}

onMounted(async () => {
  try {
    const status = await authApi.status();
    userId.value = status.needsSetup ? status.defaultUserId : "";
    if (status.authenticated) {
      continueToWorkbench();
      return;
    }
    mode.value = status.needsSetup ? "setup" : "login";
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : String(reason);
    mode.value = "login";
  }
});

async function submit() {
  error.value = "";
  if (password.value.length < 8) {
    error.value = copy.value.minLength;
    return;
  }
  if ((mode.value === "setup" || mode.value === "register") && password.value !== confirmation.value) {
    error.value = copy.value.mismatch;
    return;
  }
  busy.value = true;
  try {
    if (mode.value === "setup") await authApi.setup(password.value, displayName.value);
    else if (mode.value === "register") await authApi.register(userId.value, password.value, displayName.value);
    else await authApi.login(userId.value, password.value);
    continueToWorkbench();
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : String(reason);
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <main class="login-page">
    <section class="login-panel">
      <header class="login-brand"><span><BrainCircuit :size="25" :stroke-width="2" aria-hidden="true" /></span><div><strong>SmartCore</strong><small>Personal student assistant</small></div></header>
      <button class="language-switch" type="button" @click="switchLanguage">{{ copy.language }}</button>
      <div class="login-copy"><h1>{{ copy.title }}</h1><p>{{ copy.subtitle }}</p></div>
      <div v-if="mode === 'loading'" class="login-loading">Loading…</div>
      <form v-else class="login-form" @submit.prevent="submit">
        <label><span>{{ copy.userId }}</span><input v-model="userId" autocomplete="username" :readonly="mode === 'setup'" required /></label>
        <label v-if="mode === 'setup' || mode === 'register'"><span>{{ copy.displayName }}</span><input v-model="displayName" autocomplete="name" :required="mode === 'register'" /></label>
        <label><span>{{ copy.password }}</span><input v-model="password" type="password" :autocomplete="mode === 'register' || mode === 'setup' ? 'new-password' : 'current-password'" minlength="8" required /></label>
        <label v-if="mode === 'setup' || mode === 'register'"><span>{{ copy.confirm }}</span><input v-model="confirmation" type="password" autocomplete="new-password" minlength="8" required /></label>
        <p v-if="mode === 'setup'" class="security-note">{{ copy.setupHint }}</p>
        <p v-if="error" class="login-error" role="alert">{{ error }}</p>
        <button class="login-submit" type="submit" :disabled="busy">{{ busy ? "…" : copy.submit }}</button>
        <button v-if="mode === 'login'" class="login-secondary" type="button" @click="switchMode('register')">{{ copy.register }}</button>
        <button v-else-if="mode === 'register'" class="login-secondary" type="button" @click="switchMode('login')">{{ copy.signIn }}</button>
      </form>
    </section>
  </main>
</template>

<style scoped>
.login-page{min-height:100vh;display:grid;place-items:center;padding:24px;background:radial-gradient(circle at 15% 10%,#dbeafe 0,transparent 34%),radial-gradient(circle at 85% 90%,#e0e7ff 0,transparent 34%),#f8fafc}.login-panel{position:relative;width:min(460px,100%);padding:34px;border:1px solid #e2e8f0;border-radius:24px;background:rgba(255,255,255,.94);box-shadow:0 28px 80px rgba(15,23,42,.12)}.login-brand{display:flex;align-items:center;gap:12px}.login-brand>span{display:grid;place-items:center;width:46px;height:46px;border-radius:14px;background:#2563eb;color:#fff;font-weight:850}.login-brand strong,.login-brand small{display:block}.login-brand small{margin-top:3px;color:#64748b}.language-switch{position:absolute;top:30px;right:30px;border:0;background:transparent;color:#2563eb;font-weight:700}.login-copy{margin:34px 0 24px}.login-copy h1{font-size:30px}.login-copy p{margin-top:8px;color:#64748b;line-height:1.6}.login-form{display:grid;gap:16px}.login-form label{display:grid;gap:7px;color:#475569;font-size:13px;font-weight:700}.login-form input{width:100%;padding:12px 13px;border:1px solid #cbd5e1;border-radius:11px;outline:0}.login-form input:focus{border-color:#60a5fa;box-shadow:0 0 0 4px rgba(59,130,246,.12)}.security-note{padding:11px 12px;border-radius:10px;background:#eff6ff;color:#1d4ed8;font-size:13px;line-height:1.5}.login-error{padding:11px 12px;border-radius:10px;background:#fef2f2;color:#b91c1c;font-size:13px}.login-submit{min-height:46px;border:0;border-radius:11px;background:#2563eb;color:#fff;font-weight:800}.login-submit:disabled{opacity:.55}.login-loading{padding:40px;text-align:center;color:#64748b}@media(max-width:520px){.login-panel{padding:26px}.language-switch{top:24px;right:24px}}
.login-secondary{border:0;background:transparent;color:#2563eb;font-weight:700}
</style>
