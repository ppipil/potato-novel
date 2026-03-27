<script setup>
import { computed, onMounted, onUnmounted, ref } from "vue";
import { useRouter } from "vue-router";
import LoadingOverlay from "../components/LoadingOverlay.vue";
import { getOpeningSummary, getOpeningTitle, presetOpenings } from "../data/openings";
import {
  getCurrentUser,
  getStorySession,
  listStories,
  preloadStoryPackage,
  regenerateStoryPackage,
  startStorySession
} from "../lib/api";
import { readStoriesCache, writeStoriesCache } from "../lib/storyCache";
import { readStorySessionCache, removeStorySessionCache, writeStorySessionCache } from "../lib/storySessionCache";
import { setTransferredStorySession } from "../lib/storySessionTransfer";
import { clearUserCache, readUserCache, writeUserCache } from "../lib/userCache";

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
const bootstrapping = ref(true);
const error = ref("");
const activeSeed = ref("");
const preloadedSession = ref(null);
const cacheStates = ref({});
const CACHE_STORAGE_KEY = "potato-novel-cache-states";
const CACHE_DEBUG_KEY = "potato-novel-debug-cache-states";
const cacheTimers = new Map();
const cacheProgressMeta = new Map();

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
      tint: coverTints[index % coverTints.length],
      onClick: () =>
        router.push({
          path: "/stories",
          query: {
            storyId: item.id
          }
        })
    }));
  }

  return [];
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
    const normalizedMap = Object.fromEntries(
      Object.entries(parsed).map(([opening, state]) => {
        const normalized = typeof state === "object" && state
          ? {
              status:
                state.status === "ready"
                  ? "ready"
                  : state.status === "error"
                    ? "error"
                    : state.status === "loading"
                      ? "loading"
                      : "idle",
              mode: state.mode === "regenerate" ? "regenerate" : "preload",
              sessionId: state.sessionId || "",
              progress:
                state.status === "ready"
                  ? 100
                  : state.status === "loading"
                    ? Math.max(1, Math.min(96, Number(state.progress || 0)))
                    : 0,
              phase:
                state.status === "loading"
                  ? state.phase || getProgressPhase(Number(state.progress || 0), state.mode === "regenerate" ? "regenerate" : "preload")
                  : state.status === "ready"
                    ? "已完成"
                    : ""
            }
          : { status: "idle", mode: "preload", sessionId: "", progress: 0, phase: "" };
        return [opening, normalized];
      })
    );
    debugCache("load-cache-states", { raw: parsed, normalized: normalizedMap });
    return normalizedMap;
  } catch {
    return {};
  }
}

function persistCacheStates() {
  localStorage.setItem(CACHE_STORAGE_KEY, JSON.stringify(cacheStates.value));
  debugCache("persist-cache-states", { cacheStates: cacheStates.value });
}

onMounted(async () => {
  if (!customOpening.value) {
    activeSeed.value = freeCreationSeeds[Math.floor(Math.random() * freeCreationSeeds.length)];
    customOpening.value = activeSeed.value;
  }
  cacheStates.value = loadCacheStates();
  resumeLoadingStates();
  const cachedUser = readUserCache();
  if (cachedUser) {
    user.value = cachedUser;
    const cachedStories = readStoriesCache(cachedUser.userId || "");
    if (cachedStories.length) {
      stories.value = cachedStories;
      bootstrapping.value = false;
    }
  }
  try {
    const meResult = await getCurrentUser();
    if (!meResult.authenticated) {
      clearUserCache();
      router.replace("/");
      return;
    }
    user.value = meResult.user;
    writeUserCache(meResult.user);

    const userId = user.value?.userId || "";
    const cachedStories = readStoriesCache(userId);
    if (cachedStories.length) {
      void refreshStories(userId);
      return;
    }

    await refreshStories(userId);
  } catch {
    if (!user.value) {
      clearUserCache();
      router.replace("/");
      return;
    }
  } finally {
    if (bootstrapping.value) {
      bootstrapping.value = false;
    }
  }
});

onUnmounted(() => {
  for (const opening of cacheTimers.keys()) {
    stopCacheProgress(opening);
  }
});

async function refreshStories(userId = user.value?.userId || "") {
  const storiesResult = await listStories();
  stories.value = storiesResult.stories || [];
  writeStoriesCache(userId, stories.value);
}

function getCacheState(opening) {
  return cacheStates.value[opening] || { status: "idle", mode: "preload", sessionId: "", progress: 0, phase: "" };
}

function setCacheState(opening, nextState) {
  const previous = getCacheState(opening);
  cacheStates.value = {
    ...cacheStates.value,
    [opening]: {
      ...previous,
      ...nextState
    }
  };
  debugCache("set-cache-state", {
    opening,
    previous,
    next: cacheStates.value[opening]
  });
  persistCacheStates();
}

function isCacheDebugEnabled() {
  try {
    return localStorage.getItem(CACHE_DEBUG_KEY) === "1";
  } catch {
    return false;
  }
}

function debugCache(event, payload) {
  if (!isCacheDebugEnabled()) {
    return;
  }
  console.log(`[potato-cache] ${event}`, payload);
}

function getProgressPhase(progress, mode) {
  if (progress < 10) {
    return "准备中";
  }
  if (progress < 35) {
    return mode === "regenerate" ? "重建世界观" : "载入故事骨架";
  }
  if (progress < 62) {
    return mode === "regenerate" ? "整理新分支" : "整理章节内容";
  }
  if (progress < 82) {
    return mode === "regenerate" ? "校对走向" : "校验章节顺序";
  }
  return "即将完成";
}

function startCacheProgress(opening, mode) {
  stopCacheProgress(opening);
  cacheProgressMeta.set(opening, { startedAt: Date.now(), mode });
  debugCache("start-cache-progress", {
    opening,
    mode,
    state: getCacheState(opening)
  });
  cacheTimers.set(
    opening,
    setInterval(() => {
      const state = getCacheState(opening);
      if (state.status !== "loading") {
        stopCacheProgress(opening);
        return;
      }
      const meta = cacheProgressMeta.get(opening);
      const elapsed = Math.max(0, Date.now() - (meta?.startedAt || Date.now()));
      const maxProgress = mode === "regenerate" ? 95 : 96;
      const baseCurve = maxProgress * (1 - Math.exp(-elapsed / (mode === "regenerate" ? 7000 : 6200)));
      const wave = Math.sin(elapsed / 900) * 1.4;
      const floorBoost = elapsed < 1500 ? elapsed / 220 : 0;
      const nextProgress = Math.min(
        maxProgress,
        Math.max(state.progress || 0, Math.round(baseCurve + wave + floorBoost))
      );
      setCacheState(opening, { progress: nextProgress, phase: getProgressPhase(nextProgress, mode) });
    }, 280)
  );
}

function stopCacheProgress(opening) {
  const timer = cacheTimers.get(opening);
  if (timer) {
    clearInterval(timer);
    cacheTimers.delete(opening);
  }
  cacheProgressMeta.delete(opening);
  debugCache("stop-cache-progress", {
    opening,
    state: getCacheState(opening)
  });
}

function resumeLoadingStates() {
  for (const [opening, state] of Object.entries(cacheStates.value)) {
    if (state?.status === "loading") {
      debugCache("resume-loading-state", { opening, state });
      startCacheProgress(opening, state.mode === "regenerate" ? "regenerate" : "preload");
    }
  }
}

async function cacheTemplate(opening) {
  selectedOpening.value = opening;
  openingMode.value = "preset";
  error.value = "";
  preloadedSession.value = null;
  setCacheState(opening, { status: "loading", mode: "preload", sessionId: "", progress: 3, phase: getProgressPhase(3, "preload") });
  startCacheProgress(opening, "preload");
  preloading.value = true;

  try {
    const result = await preloadStoryPackage({
      opening,
      role: selectedRole.value
    });
    stopCacheProgress(opening);
    setCacheState(opening, { status: "ready", mode: "preload", sessionId: result.session?.id || "", progress: 100, phase: "已完成" });
    preloadedSession.value = result.session;
    writeStorySessionCache(result.session);
    debugCache("preload-success", {
      opening,
      sessionId: result.session?.id,
      packageStatus: result.session?.packageStatus,
      completedRun: Boolean(result.session?.completedRun)
    });
  } catch (err) {
    stopCacheProgress(opening);
    setCacheState(opening, { status: "error", mode: "preload", sessionId: "", progress: 0, phase: "" });
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
  setCacheState(opening, { status: "loading", mode: "regenerate", sessionId: "", progress: 2, phase: getProgressPhase(2, "regenerate") });
  startCacheProgress(opening, "regenerate");
  regeneratingPackage.value = true;

  try {
    const result = await regenerateStoryPackage({
      opening,
      role: selectedRole.value
    });
    stopCacheProgress(opening);
    setCacheState(opening, { status: "ready", mode: "regenerate", sessionId: result.session?.id || "", progress: 100, phase: "已完成" });
    preloadedSession.value = result.session;
    writeStorySessionCache(result.session);
    debugCache("regenerate-success", {
      opening,
      sessionId: result.session?.id,
      packageStatus: result.session?.packageStatus,
      completedRun: Boolean(result.session?.completedRun)
    });
  } catch (err) {
    stopCacheProgress(opening);
    setCacheState(opening, { status: "error", mode: "regenerate", sessionId: "", progress: 0, phase: "" });
    error.value = err instanceof Error ? err.message : "重新生成故事包失败";
  } finally {
    regeneratingPackage.value = false;
  }
}

async function handleGenerate(openingOverride = "") {
  const normalizedOpening =
    typeof openingOverride === "string"
      ? openingOverride
      : "";
  const openingToUse = (normalizedOpening || activeOpening.value || "").trim();
  if (!openingToUse) {
    error.value = "先写一个故事开局，或者选择一个模板。";
    return;
  }

  if (normalizedOpening) {
    selectedOpening.value = openingToUse;
    openingMode.value = "preset";
  }

  generating.value = true;
  error.value = "";
  try {
    const isPresetOpening = presetOpenings.includes(openingToUse);
    const cachedState = getCacheState(openingToUse);
    const entryMode = isPresetOpening ? "library" : "custom";
    let nextSession = null;
    debugCache("handle-generate-start", {
      opening: openingToUse,
      isPresetOpening,
      entryMode,
      cachedState
    });

    if (isPresetOpening && cachedState.status === "ready" && cachedState.sessionId) {
      try {
        const cachedSession = readStorySessionCache(cachedState.sessionId);
        debugCache("handle-generate-cache-hit", {
          opening: openingToUse,
          sessionId: cachedState.sessionId,
          hasCachedSession: Boolean(cachedSession),
          completedRun: Boolean(cachedSession?.completedRun)
        });
        if (cachedSession?.completedRun) {
          removeStorySessionCache(cachedState.sessionId);
          setCacheState(openingToUse, { status: "idle", sessionId: "" });
          const result = await startStorySession({
            opening: openingToUse,
            role: selectedRole.value
          });
          nextSession = result.session;
          writeStorySessionCache(result.session);
          sessionStorage.setItem("potato-novel-story-session", JSON.stringify(result.session));
          debugCache("handle-generate-restart-completed-session", {
            opening: openingToUse,
            oldSessionId: cachedState.sessionId,
            newSessionId: result.session?.id
          });
        } else if (cachedSession?.id) {
          preloadedSession.value = cachedSession;
          nextSession = cachedSession;
          sessionStorage.setItem("potato-novel-story-session", JSON.stringify(cachedSession));
          debugCache("handle-generate-open-local-session", {
            opening: openingToUse,
            sessionId: cachedSession.id
          });
        } else {
          const result = await getStorySession(cachedState.sessionId);
          if (result.session?.completedRun) {
            removeStorySessionCache(cachedState.sessionId);
            setCacheState(openingToUse, { status: "idle", sessionId: "" });
            const nextResult = await startStorySession({
              opening: openingToUse,
              role: selectedRole.value
            });
            nextSession = nextResult.session;
            writeStorySessionCache(nextResult.session);
            sessionStorage.setItem("potato-novel-story-session", JSON.stringify(nextResult.session));
            debugCache("handle-generate-restart-remote-completed-session", {
              opening: openingToUse,
              oldSessionId: cachedState.sessionId,
              newSessionId: nextResult.session?.id
            });
          } else {
          preloadedSession.value = result.session;
          nextSession = result.session;
          writeStorySessionCache(result.session);
          sessionStorage.setItem("potato-novel-story-session", JSON.stringify(result.session));
          debugCache("handle-generate-open-remote-session", {
            opening: openingToUse,
            sessionId: result.session?.id
          });
          }
        }
      } catch {
        removeStorySessionCache(cachedState.sessionId);
        setCacheState(openingToUse, { status: "idle", sessionId: "" });
        const result = await startStorySession({
          opening: openingToUse,
          role: selectedRole.value
        });
        nextSession = result.session;
        writeStorySessionCache(result.session);
        sessionStorage.setItem("potato-novel-story-session", JSON.stringify(result.session));
        debugCache("handle-generate-recover-from-cache-error", {
          opening: openingToUse,
          newSessionId: result.session?.id
        });
      }
    } else {
      const result = await startStorySession({
        opening: openingToUse,
        role: selectedRole.value
      });
      nextSession = result.session;
      writeStorySessionCache(result.session);
      if (isPresetOpening) {
        preloadedSession.value = result.session;
      }
      sessionStorage.setItem("potato-novel-story-session", JSON.stringify(result.session));
      debugCache("handle-generate-start-session", {
        opening: openingToUse,
        sessionId: result.session?.id,
        isPresetOpening
      });
    }
    setTransferredStorySession(nextSession);
    router.push({
      path: "/story/result",
      query: {
        entry: entryMode
      }
    });
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
        :visible="bootstrapping || generating"
        :title="bootstrapping ? '正在整理你的书架' : openingMode === 'custom' ? '正在写下第一幕' : '正在翻开故事'"
        :description="bootstrapping ? '优先读取本地缓存，并和云端故事记录做一次同步。' : openingMode === 'custom' ? '土豆正在把你的开头整理成故事的第一页。' : '如果模板已经准备好，这次会直接带你进入那个宇宙。'"
      />

      <header class="sticky top-0 z-20 -mx-6 mb-8 bg-paper-50/92 px-6 pb-5 pt-2 backdrop-blur-sm sm:-mx-8 sm:px-8">
        <div class="flex items-center justify-between gap-4">
          <div class="space-y-2">
            <p class="text-sm uppercase tracking-[0.24em] text-paper-700/55">Welcome Back</p>
            <h1 class="font-serif text-[2.6rem] font-semibold text-paper-900">
              嗨，{{ user?.name || user?.nickname || "创作者_77X" }}
            </h1>
          </div>

          <div class="shrink-0 self-start pt-1">
            <div class="flex h-14 w-14 items-center justify-center rounded-full border-4 border-white bg-paper-200 text-lg text-paper-700 shadow-[0_6px_20px_rgba(74,59,50,0.12)]">
              {{ (user?.name || user?.nickname || "创")?.slice(0, 1) }}
            </div>
          </div>
        </div>
      </header>

      <section class="space-y-12 pb-10">
        <div class="space-y-5">
          <div class="flex items-end justify-between">
            <h2 class="section-title">我的宇宙</h2>
            <p class="text-xl text-paper-700/45">{{ stories.length }} 部作品</p>
          </div>

          <div v-if="shelfBooks.length" class="hide-scrollbar flex gap-4 overflow-x-auto pb-2">
            <button
              v-for="book in shelfBooks"
              :key="book.id"
              class="book-cover active-press text-left"
              @click="book.onClick"
            >
              <div class="absolute inset-0" :class="book.tint"></div>
              <div class="absolute inset-x-0 bottom-0 z-10 px-4 pb-5">
                <p class="line-clamp-2 font-serif text-base leading-6 text-white">
                  {{ book.title }}
                </p>
              </div>
            </button>
          </div>
          <div
            v-else
            class="rounded-[30px] border border-dashed border-paper-200 bg-white/55 px-6 py-10 text-center text-paper-700/60"
          >
            你的宇宙还是空的，先生成第一篇故事吧。
          </div>
        </div>

        <div class="space-y-4">
          <h2 class="font-serif text-[2.3rem] font-semibold text-paper-900">开启新篇章</h2>

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
                        ? getCacheState(opening).phase || '加载中'
                        : getCacheState(opening).status === 'ready'
                          ? '重新整理'
                          : getCacheState(opening).status === 'error'
                            ? '加载失败'
                            : '待加载'
                    }}
                  </p>
                  <p
                    v-if="getCacheState(opening).status === 'ready'"
                    class="text-right text-[0.62rem] font-medium tracking-[0.04em] text-white/82"
                  >
                    已准备好，可直接进入
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
