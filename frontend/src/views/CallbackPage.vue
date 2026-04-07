<script setup>
import { onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { exchangeCode, getCurrentUser } from "../lib/api";
import { writeUserCache } from "../lib/userCache";

const route = useRoute();
const router = useRouter();
const message = ref("正在完成 SecondMe 登录...");
const error = ref("");

function explainAuthError(rawError) {
  const text = String(rawError || "").trim();
  const normalized = text.toLowerCase();

  if (!text) {
    return {
      message: "登录换取 token 失败。",
      detail: "没有拿到明确错误信息，请重新发起一次登录。"
    };
  }

  if (normalized.includes("oauth state mismatch")) {
    return {
      message: "登录状态已失效，请重新登录。",
      detail: "这通常是因为登录过程里刷新了页面、打开了多个登录页，或者本地地址在 localhost 和 127.0.0.1 之间切换，导致 state 对不上。"
    };
  }

  if (normalized.includes("missing code or state")) {
    return {
      message: "登录回调参数不完整。",
      detail: "SecondMe 回跳时缺少必要参数，重新点击登录通常可以恢复。"
    };
  }

  if (normalized.includes("token exchange failed")) {
    return {
      message: "SecondMe token 换取失败。",
      detail: "可能是回调地址不一致、client 配置不对，或者 SecondMe 上游接口暂时异常。"
    };
  }

  if (normalized.includes("token response missing access token")) {
    return {
      message: "SecondMe 返回了异常的 token 结果。",
      detail: "接口返回成功了，但没有拿到 access token，建议稍后重试并检查应用配置。"
    };
  }

  if (normalized.includes("failed to fetch user info")) {
    return {
      message: "登录成功了，但获取用户信息失败。",
      detail: "说明 token 可能已拿到，但拉取用户资料时出错了，可以稍后再试。"
    };
  }

  if (normalized.includes("unable to reach secondme oauth api")) {
    return {
      message: "当前无法连接 SecondMe 登录服务。",
      detail: "更像是网络或上游服务问题，不是你操作错了。"
    };
  }

  return {
    message: "登录换取 token 失败。",
    detail: text
  };
}

onMounted(async () => {
  const code = route.query.code;
  const state = route.query.state;
  const oauthError = route.query.error;

  if (oauthError) {
    error.value = String(oauthError);
    message.value = "SecondMe 返回了授权错误。";
    return;
  }

  if (!code || !state) {
    error.value = "缺少 code 或 state";
    message.value = "回调参数不完整。";
    return;
  }

  try {
    await exchangeCode({
      code: String(code),
      state: String(state)
    });
    const meResult = await getCurrentUser();
    if (meResult.authenticated && meResult.user) {
      writeUserCache(meResult.user);
    }
    router.replace("/bookshelf");
  } catch (err) {
    const explained = explainAuthError(err instanceof Error ? err.message : "未知错误");
    error.value = explained.detail;
    message.value = explained.message;
  }
});
</script>

<template>
  <main class="paper-shell">
    <section class="paper-page flex min-h-screen items-center justify-center px-8 py-12">
      <div class="paper-card glass-panel w-full rounded-[32px] px-7 py-10 text-center">
        <p class="mb-4 text-xs uppercase tracking-[0.32em] text-accent-500">SecondMe Callback</p>
        <h1 class="font-serif text-3xl leading-tight text-paper-900">{{ message }}</h1>
        <p class="mt-5 text-paper-700/70" v-if="!error">稍等片刻，马上进入你的书架。</p>
        <p class="mt-5 whitespace-pre-wrap text-sm text-red-700" v-else>{{ error }}</p>
      </div>
    </section>
  </main>
</template>
