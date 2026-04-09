<script setup>
import { computed, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import LoadingOverlay from "../components/LoadingOverlay.vue";
import { analyzeStoryEnding, cacheStoryEndingAnalysis, getStory, listStories } from "../lib/api";
import { readStoriesCache, writeStoriesCache } from "../lib/storyCache";
import { readUserCache } from "../lib/userCache";

const route = useRoute();
const router = useRouter();
const stories = ref([]);
const currentStory = ref(null);
const loading = ref(true);
const error = ref("");
const endingAnalysis = ref(null);
const analyzingEnding = ref(false);

const reviewTitle = computed(() => {
  if (!currentStory.value?.story) {
    return "阅读回顾";
  }
  const firstLine = currentStory.value.story.split("\n").find((line) => line.trim());
  return firstLine?.replace(/^《/, "").replace(/》$/, "") || "阅读回顾";
});

const parsedBlocks = computed(() =>
  parseStoryBlocks(currentStory.value?.story || "", currentStory.value?.meta?.opening || "")
);
const reviewPersonaSummary = computed(() => endingAnalysis.value);
const GUEST_CACHE_USER_ID = "__guest_local__";
const viewerUserId = ref("");
const isGuestViewer = computed(() => viewerUserId.value === GUEST_CACHE_USER_ID);

onMounted(async () => {
  const targetStoryId = typeof route.query.storyId === "string" ? route.query.storyId : "";
  const cachedUser = readUserCache();
  viewerUserId.value = cachedUser?.userId || GUEST_CACHE_USER_ID;
  const cachedStories = readStoriesCache(viewerUserId.value);
  if (cachedStories.length) {
    stories.value = cachedStories;
    const preferredStory = (targetStoryId && cachedStories.find((item) => item.id === targetStoryId)) || cachedStories[0];
    if (preferredStory) {
      currentStory.value = preferredStory;
      endingAnalysis.value = preferredStory.meta?.endingAnalysis || null;
      loading.value = false;
    }
  }

  if (isGuestViewer.value) {
    loading.value = false;
    return;
  }

  try {
    const result = await listStories();
    stories.value = result.stories || [];
    if (viewerUserId.value) {
      writeStoriesCache(viewerUserId.value, stories.value);
    }
    const preferredStoryId = targetStoryId || currentStory.value?.id || stories.value[0]?.id;
    if (preferredStoryId) {
      await openStory(preferredStoryId);
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : "加载失败";
  } finally {
    loading.value = false;
  }
});

function goBack() {
  if (window.history.length > 1) {
    router.back();
    return;
  }
  router.push("/bookshelf");
}

async function openStory(storyId) {
  if (isGuestViewer.value) {
    const localStory = stories.value.find((item) => item.id === storyId);
    if (!localStory) {
      error.value = "读取失败";
      return;
    }
    currentStory.value = localStory;
    endingAnalysis.value = localStory.meta?.endingAnalysis || null;
    error.value = "";
    return;
  }
  try {
    const result = await getStory(storyId);
    currentStory.value = result.story;
    error.value = "";
    endingAnalysis.value = result.story.meta?.endingAnalysis || null;
  } catch (err) {
    error.value = err instanceof Error ? err.message : "读取失败";
  }
}

async function ensureEndingAnalysis(storyRecord) {
  if (!storyRecord || analyzingEnding.value) {
    return;
  }
  if (isGuestViewer.value) {
    error.value = "游客模式暂不支持尾声签语，请登录后使用。";
    return;
  }

  if (storyRecord.meta?.endingAnalysis) {
    endingAnalysis.value = storyRecord.meta.endingAnalysis;
    return;
  }

  analyzingEnding.value = true;
  try {
    const result = await analyzeStoryEnding({
      story: storyRecord.story,
      meta: {
        ...storyRecord.meta,
        summary: storyRecord.meta?.summary || extractEndingSummary(storyRecord.story),
        transcript: storyRecord.meta?.transcript || extractTranscriptFromStory(storyRecord.story)
      }
    });
    endingAnalysis.value = result.analysis;
    if (storyRecord.id) {
      await cacheStoryEndingAnalysis(storyRecord.id, { analysis: result.analysis });
      currentStory.value = {
        ...storyRecord,
        meta: {
          ...(storyRecord.meta || {}),
          endingAnalysis: result.analysis
        }
      };
      stories.value = stories.value.map((item) =>
        item.id === storyRecord.id
          ? {
              ...item,
              meta: {
                ...(item.meta || {}),
                endingAnalysis: result.analysis
              }
            }
          : item
      );
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : "尾声分析生成失败";
  } finally {
    analyzingEnding.value = false;
  }
}

function parseStoryBlocks(storyText, openingFallback = "") {
  if (!storyText.trim()) {
    if (openingFallback.trim()) {
      return [
        { type: "heading", text: "故事开端" },
        { type: "story", text: openingFallback.trim() }
      ];
    }
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
    if (
      segment.includes("【结局状态】") ||
      segment.includes("\n阶段：") ||
      segment.startsWith("阶段：") ||
      segment.includes("\n旗标：") ||
      segment.startsWith("旗标：") ||
      segment.includes("\n关系：") ||
      segment.startsWith("关系：")
    ) {
      continue;
    }

    if (segment.startsWith("《")) {
      blocks.push({ type: "title", text: segment });
      continue;
    }

    if (segment.startsWith("玩家身份：") || segment.startsWith("创作者：")) {
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

  const hasOpeningHeading = blocks.some((item) => item.type === "heading" && String(item.text || "").includes("故事开端"));
  if (!hasOpeningHeading && openingFallback.trim()) {
    return [
      { type: "heading", text: "故事开端" },
      { type: "story", text: openingFallback.trim() },
      ...blocks
    ];
  }

  return blocks;
}

function extractEndingSummary(storyText) {
  const match = storyText.match(/【结局摘要】\n([\s\S]*?)(?:\n\n【|$)/);
  return match?.[1]?.trim() || storyText;
}

function extractTranscriptFromStory(storyText) {
  const segments = storyText
    .split(/\n{2,}/)
    .map((item) => item.trim())
    .filter(Boolean);
  const transcript = [];
  let pendingLabel = "";

  for (const segment of segments) {
    if (/^【第 .*】$/.test(segment)) {
      pendingLabel = segment.replace(/^【|】$/g, "");
      continue;
    }
    if (pendingLabel) {
      transcript.push({ label: pendingLabel, text: segment });
      pendingLabel = "";
    }
  }

  return transcript;
}
</script>

<template>
  <main class="paper-shell">
    <section class="paper-page px-0 pt-0">
      <LoadingOverlay
        :visible="loading || analyzingEnding"
        :title="analyzingEnding ? '正在解读这颗土豆' : '正在加载历史记录'"
        :description="analyzingEnding ? 'SecondMe 正在根据这局故事补全结局签语。' : '土豆正在翻找你书架里的旧宇宙，请稍候。'"
      />

      <header class="glass-panel sticky top-0 z-30 shrink-0 border-b border-paper-200/70 px-6 py-4 shadow-[0_10px_28px_rgba(74,59,50,0.08)] sm:px-8">
        <div class="flex items-center justify-between gap-4">
          <button
            class="active-press inline-flex h-11 min-w-11 items-center justify-center rounded-full border border-paper-200 bg-white/88 px-3 text-xl text-paper-700 shadow-[0_4px_14px_rgba(0,0,0,0.06)]"
            aria-label="返回"
            @click="goBack"
          >
            ←
          </button>
          <h1 class="truncate text-center font-serif text-[1.45rem] font-semibold text-paper-900">
            {{ currentStory ? reviewTitle : "阅读回顾" }}
          </h1>
          <span class="w-16 text-right text-sm text-paper-700/55">{{ stories.length }} 本</span>
        </div>
      </header>

      <div class="hide-scrollbar h-[calc(100vh-4.5rem)] overflow-y-auto px-6 pb-16 pt-8 sm:px-8">
        <section class="space-y-8">
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

              <div v-if="reviewPersonaSummary" class="space-y-4 rounded-[30px] border border-paper-200 bg-white/82 px-5 py-5 shadow-[0_2px_12px_rgba(0,0,0,0.04)]">
                <p class="text-center font-serif text-[1.45rem] text-paper-900">尾声签语</p>
                <div class="rounded-[22px] bg-paper-100/80 px-4 py-4">
                  <p class="font-serif text-[1.05rem] font-semibold text-paper-900">{{ reviewPersonaSummary.title }}</p>
                  <div v-if="reviewPersonaSummary.personaTags?.length" class="mt-3 flex flex-wrap gap-2">
                    <span
                      v-for="tag in reviewPersonaSummary.personaTags"
                      :key="tag"
                      class="rounded-full bg-white px-3 py-1.5 text-xs font-semibold text-paper-800"
                    >
                      {{ tag }}
                    </span>
                  </div>
                  <p class="mt-2 text-sm leading-7 text-paper-700/80">{{ reviewPersonaSummary.romance }}</p>
                  <p class="mt-2 text-sm leading-7 text-paper-700/70">{{ reviewPersonaSummary.life }}</p>
                  <p class="mt-2 text-sm leading-7 text-paper-700/70">{{ reviewPersonaSummary.nextUniverseHook }}</p>
                </div>
              </div>

              <button
                v-else-if="currentStory && !isGuestViewer"
                class="active-press w-full rounded-[30px] border border-paper-200 bg-white/82 px-5 py-5 text-center shadow-[0_2px_12px_rgba(0,0,0,0.04)]"
                :disabled="analyzingEnding"
                @click="ensureEndingAnalysis(currentStory)"
              >
                <span class="font-serif text-[1.2rem] text-paper-900">
                  {{ analyzingEnding ? "正在生成尾声签语" : "生成尾声签语" }}
                </span>
              </button>
            </div>
          </article>
        </section>
      </div>
    </section>
  </main>
</template>
