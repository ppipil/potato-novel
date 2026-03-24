<script setup>
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { getStory, listStories } from "../lib/api";

const router = useRouter();
const stories = ref([]);
const currentStory = ref(null);
const loading = ref(true);
const error = ref("");

onMounted(async () => {
  try {
    const result = await listStories();
    stories.value = result.stories || [];
  } catch (err) {
    error.value = err instanceof Error ? err.message : "加载失败";
  } finally {
    loading.value = false;
  }
});

async function openStory(storyId) {
  try {
    const result = await getStory(storyId);
    currentStory.value = result.story;
  } catch (err) {
    error.value = err instanceof Error ? err.message : "读取失败";
  }
}
</script>

<template>
  <main class="page">
    <section class="topbar">
      <div>
        <p class="status">本地保存记录</p>
        <h1>我的小说历史</h1>
      </div>
      <button class="ghost" @click="router.push('/bookshelf')">返回书架</button>
    </section>

    <section v-if="loading" class="card">
      <p>正在加载历史记录...</p>
    </section>

    <section v-else class="grid history-grid">
      <article class="card">
        <h2>已保存小说</h2>
        <p v-if="!stories.length">还没有保存的小说，先去生成一篇吧。</p>
        <div v-else class="stack">
          <button
            v-for="item in stories"
            :key="item.id"
            class="choice"
            @click="openStory(item.id)"
          >
            <strong>{{ item.meta.role }}</strong>
            <span>{{ item.meta.opening }}</span>
          </button>
        </div>
      </article>

      <article class="card">
        <h2>详情</h2>
        <p v-if="error" class="error">{{ error }}</p>
        <template v-else-if="currentStory">
          <p>角色：{{ currentStory.meta.role }}</p>
          <p>开头：{{ currentStory.meta.opening }}</p>
          <p>创作者：{{ currentStory.meta.author }}</p>
          <article class="story-body">{{ currentStory.story }}</article>
        </template>
        <p v-else>选择左侧一篇小说查看详情。</p>
      </article>
    </section>
  </main>
</template>
