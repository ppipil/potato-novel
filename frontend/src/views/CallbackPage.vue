<script setup>
import { onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { exchangeCode } from "../lib/api";

const route = useRoute();
const router = useRouter();
const message = ref("正在完成 SecondMe 登录...");
const error = ref("");

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
    router.replace("/bookshelf");
  } catch (err) {
    error.value = err instanceof Error ? err.message : "未知错误";
    message.value = "登录换取 token 失败。请检查后端环境变量与 OAuth 端点。";
  }
});
</script>

<template>
  <main class="page page-callback">
    <section class="card narrow">
      <p class="status">OAuth Callback</p>
      <h1>{{ message }}</h1>
      <p v-if="error" class="error">{{ error }}</p>
      <p v-else>稍等片刻，马上进入你的书架。</p>
    </section>
  </main>
</template>
