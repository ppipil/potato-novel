<script setup>
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { getStory, listStories } from "../lib/api";

const router = useRouter();
const stories = ref([]);
const currentStory = ref(null);
const loading = ref(true);
const error = ref("");

const reviewTitle = computed(() => {
  if (!currentStory.value?.story) {
    return "阅读回顾";
  }
  const firstLine = currentStory.value.story.split("\n").find((line) => line.trim());
  return firstLine?.replace(/^《/, "").replace(/》$/, "") || "阅读回顾";
});

const parsedBlocks = computed(() => parseStoryBlocks(currentStory.value?.story || ""));

onMounted(async () => {
  try {
    const result = await listStories();
    stories.value = result.stories || [];
    if (stories.value[0]?.id) {
      await openStory(stories.value[0].id);
    }
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
    error.value = "";
  } catch (err) {
    error.value = err instanceof Error ? err.message : "读取失败";
  }
}

function parseStoryBlocks(storyText) {
  if (!storyText.trim()) {
    return [];
  }

  const segments = storyText
    .split(/\n{2,}/)
    .map((item) => item.trim())
    .filter(Boolean);

  const blocks = [];
  let pendingType = null;
  let pendingLabel = "";

  for (const segment of segments) {
    if (segment.startsWith("《")) {
      blocks.push({ type: "title", text: segment });
      continue;
    }

    if (segment.startsWith("玩家身份：") || segment.startsWith("创作者：")) {
      blocks.push({ type: "meta", text: segment });
      continue;
    }

    if (/^【第 .*玩家行动】$/.test(segment)) {
      pendingType = "action";
      pendingLabel = segment.replace(/^【|】$/g, "");
      continue;
    }

    if (/^【第 .*局势提示】$/.test(segment) || segment === "【结局摘要】") {
      pendingType = segment === "【结局摘要】" ? "summary" : "note";
      pendingLabel = segment.replace(/^【|】$/g, "");
      continue;
    }

    if (/^【.+】$/.test(segment)) {
      blocks.push({ type: "heading", text: segment.replace(/^【|】$/g, "") });
      continue;
    }

    if (pendingType) {
      blocks.push({ type: pendingType, label: pendingLabel, text: segment });
      pendingType = null;
      pendingLabel = "";
      continue;
    }

    blocks.push({ type: "story", text: segment });
  }

  return blocks;
}
</script>

<template>
  <main class="paper-shell">
    <section class="paper-page px-0 pt-0">
      <header class="glass-panel sticky top-0 z-20 border-b border-paper-200/70 px-6 py-5 sm:px-8">
        <div class="flex items-center justify-between gap-4">
          <button class="active-press text-base text-paper-700" @click="router.push('/bookshelf')">返回书架</button>
          <h1 class="truncate text-center font-serif text-[1.45rem] font-semibold text-paper-900">
            {{ currentStory ? reviewTitle : "阅读回顾" }}
          </h1>
          <span class="w-16 text-right text-sm text-paper-700/55">{{ stories.length }} 本</span>
        </div>
      </header>

      <div class="hide-scrollbar h-[calc(100vh-4.5rem)] overflow-y-auto px-6 pb-16 pt-8 sm:px-8">
        <section v-if="loading" class="text-paper-800">正在加载历史记录...</section>

        <section v-else class="space-y-8">
          <div class="hide-scrollbar flex gap-4 overflow-x-auto pb-2">
            <button
              v-for="(item, index) in stories"
              :key="item.id"
              class="book-cover active-press text-left"
              @click="openStory(item.id)"
            >
              <div
                class="absolute inset-0"
                :class="index % 3 === 0 ? 'bg-slate-800/20' : index % 3 === 1 ? 'bg-rose-300/28' : 'bg-amber-700/18'"
              ></div>
              <div class="absolute right-4 top-4 rounded-xl bg-stone-400/80 px-3 py-2 text-sm text-white">
                {{ item.meta?.turnCount || 1 }} 轮
              </div>
              <div class="absolute inset-x-0 bottom-0 z-10 px-4 pb-5 text-lg font-serif text-white">
                {{ (item.meta?.opening || "未命名作品").split('\n').find(Boolean) }}
              </div>
            </button>
          </div>

          <p v-if="error" class="rounded-[22px] bg-red-50 px-4 py-3 text-sm text-red-700">{{ error }}</p>
          <p v-if="!stories.length" class="text-paper-700/70">还没有保存的小说，先去生成一篇吧。</p>

          <article v-if="currentStory" class="space-y-6">
            <p class="text-center font-serif text-[2.35rem] font-semibold text-paper-900">
              {{ reviewTitle }}
            </p>

            <div class="space-y-6">
              <template v-for="(block, index) in parsedBlocks" :key="`${block.type}-${index}`">
                <p v-if="block.type === 'title'" class="hidden">{{ block.text }}</p>

                <p v-else-if="block.type === 'meta'" class="text-center text-sm text-paper-700/60">
                  {{ block.text }}
                </p>

                <p v-else-if="block.type === 'heading'" class="pt-4 text-center font-serif text-[1.4rem] text-paper-900">
                  {{ block.text }}
                </p>

                <div v-else-if="block.type === 'action'" class="story-divider">
                  <span class="story-divider-label">{{ block.text }}</span>
                </div>

                <div v-else-if="block.type === 'note'" class="rounded-[22px] bg-white/70 px-5 py-4 text-paper-700 shadow-[0_2px_12px_rgba(0,0,0,0.04)]">
                  <p class="text-xs uppercase tracking-[0.24em] text-accent-500/70">{{ block.label }}</p>
                  <p class="mt-2 leading-8">{{ block.text }}</p>
                </div>

                <div v-else-if="block.type === 'summary'" class="rounded-[28px] border border-paper-200 bg-paper-100/70 px-5 py-5">
                  <p class="mb-2 text-xs uppercase tracking-[0.24em] text-paper-700/55">{{ block.label }}</p>
                  <p class="story-prose no-indent">{{ block.text }}</p>
                </div>

                <p v-else class="story-prose">{{ block.text }}</p>
              </template>
            </div>
          </article>
        </section>
      </div>
    </section>
  </main>
</template>
