<script setup>
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import LoadingOverlay from "../components/LoadingOverlay.vue";
import { getOpeningSummary, getOpeningTitle, presetOpenings } from "../data/openings";
import {
  getCurrentUser,
  getStorySession,
  listStories,
  logout,
  preloadStoryPackage,
  regenerateStoryPackage,
  startStorySession
} from "../lib/api";

const router = useRouter();
const user = ref(null);
const openingMode = ref("custom");
const selectedOpening = ref(presetOpenings[0] || "");
const customOpening = ref("");
const selectedRole = ref("主人公");
const stories = ref([]);
const generating = ref(false);
const preloading = ref(false);
const regeneratingPackage = ref(false);
const error = ref("");
const activeSeed = ref("");
const preloadedSession = ref(null);
const cacheStates = ref({});
const CACHE_STORAGE_KEY = "potato-novel-cache-states";
const cacheTimers = new Map();

const templateTags = ["悬疑惊悚", "都市言情", "无限流", "命运反转"];
const coverTints = [
  "bg-slate-800/22",
  "bg-rose-300/30",
  "bg-amber-700/18",
  "bg-emerald-700/16"
];
const freeCreationSeeds = [
  "我是一个刚入职的实习生，入职第一天就撞破了霸总的秘密。可他没有第一时间开除我，而是递来一份婚约草案。",
  "凌晨一点，我值夜班的便利店门口来了一个没有影子的人。他问我，今天是不是又少了一个活人。",
  "联姻三个月后，我终于发现丈夫能听见我的部分心声。问题是，他每次都只能听见最容易误会的那半句。",
  "我替妹妹出嫁的当天，新郎在婚礼后台递给我一张纸条：如果你也想逃，现在就跟我一起走。"
];

const shelfBooks = computed(() => {
  if (stories.value.length) {
    return stories.value.slice(0, 6).map((item, index) => ({
      id: item.id,
      title: formatBookCoverTitle(item.meta?.opening || "未命名作品"),
      turns: item.meta?.turnCount || 1,
      tint: coverTints[index % coverTints.length],
      onClick: () => router.push("/stories")
    }));
  }

  return [
    {
      id: "draft",
      title: "《便利店的无头客》",
      turns: 5,
      tint: "bg-slate-500/20",
      onClick: () => {
        openingMode.value = "custom";
        customOpening.value = "我是夜班便利店的临时店员，凌晨一点，一个没有影子的人推门走了进来。";
      }
    }
  ];
});

const activeOpening = computed(() => {
  return openingMode.value === "custom"
    ? customOpening.value.trim() || freeCreationSeeds[0]
    : selectedOpening.value;
});

const packageStatusText = computed(() => {
  if (openingMode.value === "custom") {
    return "自定义开头不做预缓存，直接点下方按钮进入生成。";
  }
  const state = getCacheState(selectedOpening.value);
  if (state.status === "ready") {
    return "这本模板已经缓存好，点封面会直接进入；点右侧图标会重新生成一套。";
  }
  if (state.status === "loading") {
    return state.mode === "regenerate"
      ? "这本模板正在重新生成，完成后会显示已缓存。"
      : "这本模板正在预缓存，完成后点封面会更快进入。";
  }
  if (state.status === "error") {
    return "这本模板上一次生成失败了，可以再点右侧图标重试。";
  }
  return "模板右侧图标负责预缓存，点封面会直接进入故事。";
});

function loadCacheStates() {
  try {
    const raw = localStorage.getItem(CACHE_STORAGE_KEY);
    if (!raw) {
      return {};
    }
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") {
      return {};
    }
    return Object.fromEntries(
      Object.entries(parsed).map(([opening, state]) => {
        const normalized = typeof state === "object" && state
          ? {
              status: state.status === "ready" ? "ready" : state.status === "error" ? "error" : "idle",
              mode: state.mode === "regenerate" ? "regenerate" : "preload",
              sessionId: state.sessionId || "",
              progress: state.status === "ready" ? 100 : 0
            }
          : { status: "idle", mode: "preload", sessionId: "", progress: 0 };
        return [opening, normalized];
      })
    );
  } catch {
    return {};
  }
}

function persistCacheStates() {
  localStorage.setItem(CACHE_STORAGE_KEY, JSON.stringify(cacheStates.value));
}

onMounted(async () => {
  if (!customOpening.value) {
    activeSeed.value = freeCreationSeeds[Math.floor(Math.random() * freeCreationSeeds.length)];
    customOpening.value = activeSeed.value;
  }
  cacheStates.value = loadCacheStates();

  const [meResult, storiesResult] = await Promise.allSettled([getCurrentUser(), listStories()]);

  if (meResult.status === "fulfilled") {
    if (!meResult.value.authenticated) {
      router.replace("/");
      return;
    }
    user.value = meResult.value.user;
  } else {
    router.replace("/");
    return;
  }

  if (storiesResult.status === "fulfilled") {
    stories.value = storiesResult.value.stories || [];
  }
});

function getCacheState(opening) {
  return cacheStates.value[opening] || { status: "idle", mode: "preload", sessionId: "", progress: 0 };
}

function setCacheState(opening, nextState) {
  cacheStates.value = {
    ...cacheStates.value,
    [opening]: {
      ...getCacheState(opening),
      ...nextState
    }
  };
  persistCacheStates();
}

function startCacheProgress(opening, mode) {
  stopCacheProgress(opening);
  cacheTimers.set(
    opening,
    setInterval(() => {
      const state = getCacheState(opening);
      if (state.status !== "loading") {
        stopCacheProgress(opening);
        return;
      }
      const increment = mode === "regenerate" ? 5 : 7;
      const ceiling = mode === "regenerate" ? 89 : 93;
      const nextProgress = Math.min((state.progress || 0) + increment, ceiling);
      setCacheState(opening, { progress: nextProgress });
    }, 220)
  );
}

function stopCacheProgress(opening) {
  const timer = cacheTimers.get(opening);
  if (timer) {
    clearInterval(timer);
    cacheTimers.delete(opening);
  }
}

async function cacheTemplate(opening) {
  selectedOpening.value = opening;
  openingMode.value = "preset";
  error.value = "";
  preloadedSession.value = null;
  setCacheState(opening, { status: "loading", mode: "preload", sessionId: "", progress: 12 });
  startCacheProgress(opening, "preload");
  preloading.value = true;

  try {
    const result = await preloadStoryPackage({
      opening,
      role: selectedRole.value
    });
    stopCacheProgress(opening);
    setCacheState(opening, { status: "ready", mode: "preload", sessionId: result.session?.id || "", progress: 100 });
    preloadedSession.value = result.session;
  } catch (err) {
    stopCacheProgress(opening);
    setCacheState(opening, { status: "error", mode: "preload", sessionId: "", progress: 0 });
    error.value = err instanceof Error ? err.message : "预生成故事包失败";
  } finally {
    preloading.value = false;
  }
}

async function regenerateTemplateCache(opening) {
  selectedOpening.value = opening;
  openingMode.value = "preset";
  error.value = "";
  preloadedSession.value = null;
  setCacheState(opening, { status: "loading", mode: "regenerate", sessionId: "", progress: 10 });
  startCacheProgress(opening, "regenerate");
  regeneratingPackage.value = true;

  try {
    const result = await regenerateStoryPackage({
      opening,
      role: selectedRole.value
    });
    stopCacheProgress(opening);
    setCacheState(opening, { status: "ready", mode: "regenerate", sessionId: result.session?.id || "", progress: 100 });
    preloadedSession.value = result.session;
  } catch (err) {
    stopCacheProgress(opening);
    setCacheState(opening, { status: "error", mode: "regenerate", sessionId: "", progress: 0 });
    error.value = err instanceof Error ? err.message : "重新生成故事包失败";
  } finally {
    regeneratingPackage.value = false;
  }
}

async function handleLogout() {
  await logout();
  router.replace("/");
}

async function handleGenerate(openingOverride = "") {
  const openingToUse = (openingOverride || activeOpening.value || "").trim();
  if (!openingToUse) {
    error.value = "先写一个故事开局，或者选择一个模板。";
    return;
  }

  if (openingOverride) {
    selectedOpening.value = openingToUse;
    openingMode.value = "preset";
  }

  generating.value = true;
  error.value = "";
  try {
    const isPresetOpening = presetOpenings.includes(openingToUse);
    const cachedState = getCacheState(openingToUse);

    if (isPresetOpening && cachedState.status === "ready" && cachedState.sessionId) {
      try {
        const result = await getStorySession(cachedState.sessionId);
        preloadedSession.value = result.session;
        sessionStorage.setItem("potato-novel-story-session", JSON.stringify(result.session));
      } catch {
        setCacheState(openingToUse, { status: "idle", sessionId: "" });
        const result = await startStorySession({
          opening: openingToUse,
          role: selectedRole.value
        });
        sessionStorage.setItem("potato-novel-story-session", JSON.stringify(result.session));
      }
    } else {
      const result = await startStorySession({
        opening: openingToUse,
        role: selectedRole.value
      });
      if (isPresetOpening) {
        preloadedSession.value = result.session;
      }
      sessionStorage.setItem("potato-novel-story-session", JSON.stringify(result.session));
    }
    router.push("/story/result");
  } catch (err) {
    error.value = err instanceof Error ? err.message : "进入故事失败";
  } finally {
    generating.value = false;
  }
}

function handleCustomInput() {
  openingMode.value = "custom";
  preloadedSession.value = null;
  if (!activeSeed.value && freeCreationSeeds.includes(customOpening.value)) {
    activeSeed.value = customOpening.value;
  }
}

function formatBookCoverTitle(opening) {
  const rawTitle = getOpeningTitle(opening).replace(/^《/, "").replace(/》$/, "").trim();
  if (!rawTitle) {
    return "未命名作品";
  }
  return rawTitle.length > 18 ? `${rawTitle.slice(0, 18)}…` : rawTitle;
}
</script>

<template>
  <main class="paper-shell">
    <section class="paper-page">
      <LoadingOverlay
        :visible="generating"
        title="正在进入故事"
        description="如果模板已经缓存成功，这次会优先直连那一套故事包。"
      />

      <header class="sticky top-0 z-20 -mx-6 mb-8 bg-paper-50/92 px-6 pb-5 pt-2 backdrop-blur-sm sm:-mx-8 sm:px-8">
        <div class="flex items-start justify-between gap-4">
          <div class="space-y-2">
            <p class="text-sm uppercase tracking-[0.24em] text-paper-700/55">Welcome Back</p>
            <h1 class="font-serif text-[2.6rem] font-semibold text-paper-900">
              嗨，{{ user?.name || user?.nickname || "创作者_77X" }}
            </h1>
          </div>

          <div class="flex flex-col items-end gap-3">
            <div class="flex h-14 w-14 items-center justify-center rounded-full border-4 border-white bg-paper-200 text-lg text-paper-700 shadow-[0_6px_20px_rgba(74,59,50,0.12)]">
              {{ (user?.name || user?.nickname || "创")?.slice(0, 1) }}
            </div>
            <div class="flex items-center gap-2 text-xs text-paper-700/65">
              <button class="active-press" @click="router.push('/stories')">历史</button>
              <span>·</span>
              <button class="active-press" @click="handleLogout">退出</button>
            </div>
          </div>
        </div>
      </header>

      <section class="space-y-12 pb-10">
        <div class="space-y-5">
          <div class="flex items-end justify-between">
            <h2 class="section-title">我的宇宙</h2>
            <p class="text-xl text-paper-700/45">{{ stories.length || 1 }} 部作品</p>
          </div>

          <div class="hide-scrollbar flex gap-4 overflow-x-auto pb-2">
            <button
              v-for="book in shelfBooks"
              :key="book.id"
              class="book-cover active-press text-left"
              @click="book.onClick"
            >
              <div class="absolute inset-0" :class="book.tint"></div>
              <div class="absolute right-4 top-4 rounded-xl bg-stone-400/80 px-3 py-2 text-sm text-white">
                {{ book.turns }} 轮
              </div>
              <div class="absolute inset-x-0 bottom-0 z-10 px-4 pb-5">
                <p class="line-clamp-2 font-serif text-base leading-6 text-white">
                  {{ book.title }}
                </p>
              </div>
            </button>
          </div>
        </div>

        <div class="space-y-4">
          <h2 class="font-serif text-[2.3rem] font-semibold text-paper-900">开启新篇章</h2>
          <p class="text-[1.08rem] text-paper-700/55">先在书架阶段把互动故事包预热好，点进去时就更接近秒开。</p>

          <article class="paper-card relative overflow-hidden px-6 py-7">
            <div class="absolute right-6 top-6 h-16 w-16 rounded-full bg-accent-400/20 blur-2xl"></div>
            <div class="space-y-6">
              <div class="flex items-center gap-3 text-accent-500">
                <span class="text-3xl">✎</span>
                <h3 class="text-[1.85rem] font-semibold">自由创作</h3>
              </div>

              <textarea
                v-model="customOpening"
                class="shadow-inner-soft min-h-40 w-full resize-none rounded-[28px] border border-paper-100 bg-paper-50 px-6 py-6 font-serif text-[1.05rem] leading-9 placeholder:text-paper-700/28"
                :class="customOpening === activeSeed ? 'text-paper-700/42' : 'text-paper-900'"
                placeholder="描述你的故事开局和你的身份..."
                @focus="openingMode = 'custom'"
                @input="handleCustomInput"
              />

              <div class="space-y-4">
                <p class="rounded-2xl bg-paper-100/80 px-4 py-3 text-sm text-paper-800">
                  当前默认以“{{ selectedRole }}”身份进入故事，这一版会先锁定三选一互动结构，不开放自定义行动。
                </p>
                <p class="rounded-2xl bg-paper-100/80 px-4 py-3 text-sm text-paper-800">
                  {{ packageStatusText }}
                </p>

                <button
                  class="active-press rounded-[18px] bg-stone-400 px-6 py-4 text-2xl font-semibold text-white disabled:opacity-60"
                  :disabled="generating || preloading || regeneratingPackage"
                  @click="handleGenerate"
                >
                  {{ generating ? "进入中..." : "进入故事" }}
                </button>
              </div>
            </div>
          </article>

          <div class="space-y-5 pt-2">
            <button
              v-for="(opening, index) in presetOpenings"
              :key="opening"
              class="paper-card active-press grid grid-cols-[1fr_10rem] overflow-hidden text-left"
              :disabled="generating"
              @click="handleGenerate(opening)"
            >
              <div class="space-y-4 px-6 py-6">
                <div class="flex items-center gap-3">
                  <span class="inline-flex rounded-xl bg-paper-100 px-4 py-2 text-sm font-semibold text-paper-800">
                    {{ templateTags[index % templateTags.length] }}
                  </span>
                </div>
                <h3 class="font-serif text-[2rem] font-semibold leading-tight text-paper-900">
                  {{ getOpeningTitle(opening) }}
                </h3>
                <p class="line-clamp-2 text-[1rem] leading-8 text-paper-700">
                  {{ getOpeningSummary(opening) }}
                </p>
              </div>

              <div class="relative min-h-full">
                <div
                  class="absolute right-0 top-0 h-full w-full"
                  :class="coverTints[index % coverTints.length]"
                ></div>
                <div class="absolute left-0 top-0 h-full w-1 bg-accent-400/70"></div>
                <div class="absolute inset-x-0 top-0 flex justify-end p-3">
                  <button
                    class="active-press flex h-12 w-12 items-center justify-center rounded-full border border-white/60 bg-white/88 text-paper-900 shadow-[0_4px_14px_rgba(0,0,0,0.08)] disabled:opacity-60"
                    :disabled="generating || getCacheState(opening).status === 'loading'"
                    @click.stop="getCacheState(opening).status === 'ready' ? regenerateTemplateCache(opening) : cacheTemplate(opening)"
                  >
                    <span v-if="getCacheState(opening).status === 'loading'" class="text-[0.68rem] font-semibold text-accent-600">
                      {{ getCacheState(opening).progress }}%
                    </span>
                    <span v-else-if="getCacheState(opening).status === 'ready'" class="text-lg text-emerald-600">↻</span>
                    <span v-else-if="getCacheState(opening).status === 'error'" class="text-lg text-red-600">!</span>
                    <span v-else class="text-lg">⇩</span>
                  </button>
                </div>
                <div class="absolute bottom-3 right-3 left-3 space-y-2">
                  <div
                    v-if="getCacheState(opening).status === 'loading'"
                    class="overflow-hidden rounded-full bg-white/35"
                  >
                    <div
                      class="h-1.5 rounded-full bg-white transition-all duration-200"
                      :style="{ width: `${getCacheState(opening).progress}%` }"
                    ></div>
                  </div>
                  <p
                    class="text-right text-[0.7rem] font-semibold tracking-[0.08em] text-white/92"
                  >
                    {{
                      getCacheState(opening).status === 'loading'
                        ? '下载中'
                        : getCacheState(opening).status === 'ready'
                          ? '重新下载'
                          : getCacheState(opening).status === 'error'
                            ? '下载失败'
                            : '未下载'
                    }}
                  </p>
                  <p
                    v-if="getCacheState(opening).status === 'ready'"
                    class="text-right text-[0.62rem] font-medium tracking-[0.04em] text-white/82"
                  >
                    已缓存，可直接进入
                  </p>
                </div>
              </div>
            </button>
          </div>

          <p v-if="selectedOpening && openingMode === 'preset'" class="rounded-2xl bg-paper-100/80 px-4 py-3 text-sm text-paper-800">
            模板封面点一下就会直接进入；右侧图标只负责预缓存和重新生成。
          </p>
          <p v-if="error" class="rounded-2xl bg-red-50 px-4 py-3 text-sm text-red-700">{{ error }}</p>
        </div>
      </section>
    </section>
  </main>
</template>
