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
    message.value = "登录换取 token 失败。";
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
