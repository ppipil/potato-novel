<script setup>
import { computed, ref } from "vue";
import { useRouter } from "vue-router";
import { saveStory } from "../lib/api";

const router = useRouter();
const raw = sessionStorage.getItem("potato-novel-story");
const payload = raw ? JSON.parse(raw) : null;

const story = computed(() => payload?.story || "");
const meta = computed(() => payload?.meta || {});
const saveMessage = ref("");
const saving = ref(false);

function backToShelf() {
  router.push("/bookshelf");
}

async function handleSave() {
  if (!story.value) {
    return;
  }
  saving.value = true;
  saveMessage.value = "";
  try {
    const result = await saveStory({
      story: story.value,
      meta: meta.value
    });
    sessionStorage.setItem("potato-novel-story", JSON.stringify({ ...payload, saved: result.story }));
    saveMessage.value = "已保存到你的小说记录。";
  } catch (err) {
    saveMessage.value = err instanceof Error ? err.message : "保存失败";
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <main class="page">
    <section class="topbar">
      <div>
        <p class="status">SecondMe 共创结果</p>
        <h1>短篇小说结果页</h1>
      </div>
      <button class="ghost" @click="backToShelf">返回书架</button>
    </section>

    <section v-if="story" class="card story-result">
      <p>角色：{{ meta.role }}</p>
      <p>开头：{{ meta.opening }}</p>
      <p>创作者：{{ meta.author }}</p>
      <div class="result-actions">
        <button class="primary" :disabled="saving" @click="handleSave">
          {{ saving ? "正在保存..." : "保存这篇小说" }}
        </button>
        <button class="ghost" @click="router.push('/stories')">查看历史</button>
      </div>
      <p v-if="saveMessage" class="hint">{{ saveMessage }}</p>
      <article class="story-body">{{ story }}</article>
    </section>

    <section v-else class="card">
      <p>还没有生成内容，请先回到书架发起一次共创。</p>
    </section>
  </main>
</template>
