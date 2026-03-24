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
  <main class="page page-home">
    <section class="hero">
      <p class="eyebrow">SecondMe A2A Story Demo</p>
      <h1>土豆小说</h1>
      <p class="lead">
        进入小说书架，选择开头与角色，让你的 AI 分身和其他 Agent 一起推动剧情，最终生成一篇属于你的短篇小说。
      </p>

      <div v-if="loading" class="card">
        <p>正在检查登录状态...</p>
      </div>

      <div v-else-if="user" class="card">
        <p class="status">已登录</p>
        <p>欢迎回来，{{ user.name || user.nickname || user.sub || "SecondMe 用户" }}</p>
        <button class="primary" @click="enterBookshelf">进入书架</button>
      </div>

      <div v-else class="card">
        <p class="status">未登录</p>
        <button class="primary" @click="login">使用 SecondMe 登录</button>
        <p class="hint">当前接的是本地联调流程，登录后会返回到前端回调页，再由后端完成 token 交换。</p>
      </div>
    </section>
  </main>
</template>
