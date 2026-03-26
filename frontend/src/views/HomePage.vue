<script setup>
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { getCurrentUser, getLoginUrl } from "../lib/api";

const router = useRouter();
const loading = ref(true);
const user = ref(null);

onMounted(async () => {
  try {
    const data = await getCurrentUser();
    if (data.authenticated) {
      user.value = data.user;
    }
  } finally {
    loading.value = false;
  }
});

function login() {
  window.location.href = getLoginUrl();
}

function enterBookshelf() {
  router.push("/bookshelf");
}
</script>

<template>
  <main class="paper-shell">
    <section class="paper-page flex min-h-screen flex-col justify-center px-8 py-14 text-center">
      <div class="pointer-events-none absolute right-10 top-12 h-44 w-44 rounded-full bg-accent-400/25 blur-3xl"></div>
      <div class="pointer-events-none absolute bottom-16 left-8 h-44 w-44 rounded-full bg-rose-glow/35 blur-3xl"></div>

      <div class="relative z-10 mx-auto flex w-full max-w-[22rem] flex-col items-center gap-8">
        <div
          class="active-press flex h-32 w-32 -rotate-6 items-center justify-center rounded-[28px] bg-white text-[3.8rem]"
          style="box-shadow: var(--shadow-float)"
        >
          🥔
        </div>

        <div class="space-y-4">
          <h1 class="font-serif text-5xl font-bold tracking-[0.2em] text-paper-900">土豆小说</h1>
          <p class="font-serif text-[1.05rem] tracking-[0.12em] text-paper-700/60">
            不仅是阅读，更是你的平行宇宙。
          </p>
        </div>

        <div v-if="loading" class="paper-card glass-panel w-full px-6 py-5 text-paper-800">
          正在检查登录状态...
        </div>

        <div v-else class="w-full space-y-6">
          <button
            v-if="!user"
            class="active-press w-full rounded-[26px] bg-paper-900 px-6 py-7 text-xl font-semibold text-paper-50"
            @click="login"
          >
            使用 SecondMe 登录
          </button>

          <button
            v-else
            class="active-press w-full rounded-[26px] bg-paper-900 px-6 py-7 text-xl font-semibold text-paper-50"
            @click="enterBookshelf"
          >
            进入我的宇宙
          </button>

          <div class="space-y-2 text-sm text-paper-700/55">
            <p v-if="user">欢迎回来，{{ user.name || user.nickname || "创作者" }}</p>
            <p v-else>登录即代表同意用户协议</p>
          </div>
        </div>
      </div>
    </section>
  </main>
</template>
