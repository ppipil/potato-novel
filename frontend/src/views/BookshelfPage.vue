<script setup>
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import LoadingOverlay from "../components/LoadingOverlay.vue";
import {
  deleteStory,
  generateLibraryStorySeed,
  generateCustomStorySession,
  getCurrentUser,
  listLibraryStories,
  listStories,
  startLibraryStoryFromSeed
} from "../lib/api";
import { readLibrarySessionCache, readLibraryStoriesCache, readStoriesCache, writeLibrarySessionCache, writeLibraryStoriesCache, writeStoriesCache } from "../lib/storyCache";
import { setTransferredStorySession } from "../lib/storySessionTransfer";
import { clearUserCache, readUserCache, writeUserCache } from "../lib/userCache";

const router = useRouter();
const user = ref(null);
const openingMode = ref("custom");
const selectedOpening = ref("");
const customOpening = ref("");
const selectedRole = ref("主人公");
const stories = ref([]);
const generating = ref(false);
const bootstrapping = ref(true);
const error = ref("");
const tipMessage = ref("");
const activeSeed = ref("");
const preloadedSession = ref(null);
const cacheStates = ref({});
const libraryStoriesById = ref({});
const deletingStoryId = ref("");
const pressedStoryId = ref("");
const suppressClickStoryId = ref("");
const CACHE_STORAGE_KEY = "potato-novel-cache-states";
const CACHE_DEBUG_KEY = "potato-novel-debug-cache-states";
const LIBRARY_STORIES_CACHE_TTL_MS = 5 * 60 * 1000;
const STORY_DELETE_LONG_PRESS_MS = 600;
let storyDeleteTimer = 0;

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

const libraryStoryRows = computed(() => Object.values(libraryStoriesById.value));

const shelfBooks = computed(() => {
  if (stories.value.length) {
    return stories.value.slice(0, 6).map((item, index) => ({
      id: item.id,
      story: item,
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
    return "自定义开头会直接生成完整故事包，生成完成后进入阅读。";
  }
  const openingId = libraryStoryIdByOpening(selectedOpening.value);
  const info = openingId ? libraryStoriesById.value[openingId] : null;
  if (info?.seedReady) {
    return "这本模板已播种完成，点击会直接复用数据库故事包。";
  }
  return "这本模板还未播种，首次进入会触发模型生成并写入数据库。";
});

function logStoryGenerationDebug(sessionPayload, source) {
  const debug = sessionPayload?.package?.debug;
  if (!debug) {
    return;
  }
  console.info("[potato-story-debug]", {
    source,
    sessionId: sessionPayload?.id || "",
    packageStatus: sessionPayload?.packageStatus || "",
    structure: debug.structure,
    choices: debug.choices,
    prose: debug.prose
  });
  try {
    if (localStorage.getItem("potato-story-debug") === "1") {
      window.__POTATO_DEBUG_SESSION__ = sessionPayload;
      window.__POTATO_DEBUG_PACKAGE__ = sessionPayload?.package || null;
      console.info("[potato-story-debug-full-package]", {
        source,
        sessionId: sessionPayload?.id || "",
        package: sessionPayload?.package || null,
        runtime: sessionPayload?.runtime || null
      });
    }
  } catch {
    // ignore debug exposure failures
  }
}

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
                    : "idle",
              mode: "preload",
              sessionId: state.sessionId || "",
              progress: state.status === "ready" ? 100 : 0,
              phase: state.status === "ready" ? "已完成" : ""
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

function loadLibraryStoriesCache() {
  const cache = readLibraryStoriesCache();
  const rows = Array.isArray(cache.rows) ? cache.rows : [];
  return {
    data: Object.fromEntries(rows.map((item) => [item.id, item])),
    updatedAt: Number(cache.updatedAt || 0)
  };
}

function persistLibraryStoriesCache() {
  writeLibraryStoriesCache(libraryStoryRows.value);
}

function isLibraryStoriesCacheFresh(updatedAt) {
  return Number(updatedAt || 0) > 0 && Date.now() - Number(updatedAt) < LIBRARY_STORIES_CACHE_TTL_MS;
}

function isLibrarySessionCacheUsable(cachedEntry, seedUpdatedAt) {
  if (!cachedEntry?.session?.package?.rootNodeId) {
    return false;
  }
  const cachedSeedUpdatedAt = Number(cachedEntry?.seedUpdatedAt || 0);
  const requiredSeedUpdatedAt = Number(seedUpdatedAt || 0);
  if (requiredSeedUpdatedAt <= 0) {
    return true;
  }
  return cachedSeedUpdatedAt >= requiredSeedUpdatedAt;
}

onMounted(async () => {
  console.info("[potato-bookshelf] mounted");
  if (!customOpening.value) {
    activeSeed.value = freeCreationSeeds[Math.floor(Math.random() * freeCreationSeeds.length)];
    customOpening.value = activeSeed.value;
  }
  cacheStates.value = loadCacheStates();
  const libraryStoriesCache = loadLibraryStoriesCache();
  libraryStoriesById.value = libraryStoriesCache.data || {};
  if (!selectedOpening.value && libraryStoryRows.value.length) {
    selectedOpening.value = libraryStoryRows.value[0].opening;
  }
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
    if (!isLibraryStoriesCacheFresh(libraryStoriesCache.updatedAt)) {
      await refreshLibraryStories();
    }
    const cachedStories = readStoriesCache(userId);
    if (cachedStories.length) {
      void refreshStories(userId).catch((err) => {
        console.warn("[potato-bookshelf] background story refresh failed", err);
      });
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

async function refreshStories(userId = user.value?.userId || "") {
  const storiesResult = await listStories();
  stories.value = storiesResult.stories || [];
  writeStoriesCache(userId, stories.value);
}

async function refreshLibraryStories() {
  try {
    console.info("[potato-bookshelf] refreshLibraryStories called");
    const result = await listLibraryStories();
    const stories = Array.isArray(result?.stories) ? result.stories : [];
    libraryStoriesById.value = Object.fromEntries(
      stories.map((item) => [item.id, item])
    );
    if (!selectedOpening.value && stories.length) {
      selectedOpening.value = stories[0].opening;
    }
    persistLibraryStoriesCache();
  } catch (err) {
    console.warn("[potato-bookshelf] library story status refresh failed", err);
  }
}

function libraryStoryIdByOpening(opening) {
  const matched = libraryStoryRows.value.find((item) => item.opening === opening);
  return matched?.id || "";
}

function isLibrarySeedReady(opening) {
  const openingId = libraryStoryIdByOpening(opening);
  if (!openingId) {
    return false;
  }
  return Boolean(libraryStoriesById.value[openingId]?.seedReady);
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

function cloneValue(value) {
  if (typeof structuredClone === "function") {
    return structuredClone(value);
  }
  return JSON.parse(JSON.stringify(value));
}

function buildLocalSessionFromCachedLibrary(openingId, cachedEntry, role) {
  const cachedSession = cachedEntry?.session;
  if (!cachedSession?.package?.rootNodeId) {
    return null;
  }
  const nextSession = cloneValue(cachedSession);
  const rootNode = (nextSession.package?.nodes || []).find((item) => item.id === nextSession.package?.rootNodeId);
  if (!rootNode) {
    return null;
  }
  nextSession.id = `local-${openingId}-${Date.now()}`;
  nextSession.status = "ready";
  nextSession.completedRun = null;
  nextSession.updatedAt = Date.now();
  nextSession.meta = {
    ...(nextSession.meta || {}),
    role: role || nextSession.meta?.role || "主人公"
  };
  nextSession.runtime = {
    currentNodeId: rootNode.id,
    entries: [
      { turn: rootNode.turn, label: rootNode.stageLabel, text: rootNode.scene },
      ...(rootNode.directorNote ? [{ turn: rootNode.turn, label: "局势提示", text: rootNode.directorNote }] : [])
    ],
    path: [],
    state: cloneValue(nextSession.package?.initialState || {}),
    status: rootNode.kind === "ending" ? "complete" : "ongoing",
    endingNodeId: rootNode.kind === "ending" ? rootNode.id : "",
    summary: rootNode.kind === "ending" ? (rootNode.summary || rootNode.scene || "") : ""
  };
  return nextSession;
}

function clearStoryDeleteTimer() {
  if (storyDeleteTimer) {
    window.clearTimeout(storyDeleteTimer);
    storyDeleteTimer = 0;
  }
  pressedStoryId.value = "";
}

function beginStoryDeleteLongPress(story) {
  if (!story?.id || deletingStoryId.value) {
    return;
  }
  clearStoryDeleteTimer();
  pressedStoryId.value = story.id;
  storyDeleteTimer = window.setTimeout(() => {
    suppressClickStoryId.value = story.id;
    void confirmDeleteSavedStory(story);
  }, STORY_DELETE_LONG_PRESS_MS);
}

function openSavedStory(storyId) {
  if (!storyId) {
    return;
  }
  if (suppressClickStoryId.value === storyId) {
    suppressClickStoryId.value = "";
    return;
  }
  router.push({
    path: "/stories",
    query: {
      storyId
    }
  });
}

async function confirmDeleteSavedStory(story) {
  clearStoryDeleteTimer();
  if (!story?.id || deletingStoryId.value) {
    return;
  }

  const title = formatBookCoverTitle(story.meta?.opening || story.story || "未命名作品");
  const confirmed = window.confirm(`确认删除《${title}》吗？删除后会从“我的宇宙”中移除。`);
  if (!confirmed) {
    suppressClickStoryId.value = "";
    return;
  }

  deletingStoryId.value = story.id;
  const previousStories = [...stories.value];
  const nextStories = stories.value.filter((item) => item.id !== story.id);
  stories.value = nextStories;
  const userId = user.value?.userId || "";
  if (userId) {
    writeStoriesCache(userId, nextStories);
  }
  try {
    await deleteStory(story.id);
    error.value = "";
  } catch (err) {
    stories.value = previousStories;
    if (userId) {
      writeStoriesCache(userId, previousStories);
    }
    error.value = err instanceof Error ? err.message : "删除失败";
  } finally {
    deletingStoryId.value = "";
    suppressClickStoryId.value = "";
  }
}

async function withTimeout(requestFactory, timeoutMs = 90000, message = "进入故事超时，请稍后重试") {
  const controller = new AbortController();
  let timedOut = false;
  const timer = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeoutMs);

  try {
    return await requestFactory({ signal: controller.signal });
  } catch (err) {
    if (timedOut && err?.name === "AbortError") {
      throw new Error(message);
    }
    throw err;
  } finally {
    clearTimeout(timer);
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
  tipMessage.value = "";
  try {
    const isPresetOpening = Boolean(libraryStoryIdByOpening(openingToUse));
    const entryMode = isPresetOpening ? "library" : "custom";
    let result;
    if (isPresetOpening) {
      const storyId = libraryStoryIdByOpening(openingToUse);
      const seedReady = isLibrarySeedReady(openingToUse);
      const seedUpdatedAt = libraryStoriesById.value[storyId]?.seedUpdatedAt || 0;
      const cachedLibrarySession = readLibrarySessionCache(storyId);
      let seedResult = null;
      const localSession = seedReady && isLibrarySessionCacheUsable(cachedLibrarySession, seedUpdatedAt)
        ? buildLocalSessionFromCachedLibrary(storyId, cachedLibrarySession, selectedRole.value)
        : null;
      if (localSession) {
        result = { ok: true, session: localSession, reused: false, localCacheHit: true };
      } else {
        if (!seedReady) {
          seedResult = await withTimeout(
            (requestOptions) => generateLibraryStorySeed(storyId, {}, requestOptions),
            480000,
            "首次播种正在生成完整故事包（可能需要 1-8 分钟），请稍后重试。"
          );
        }
        result = await withTimeout(
          (requestOptions) => startLibraryStoryFromSeed(storyId, {
            role: selectedRole.value
          }, requestOptions),
          120000,
          "从数据库打开故事超时，请稍后重试。"
        );
        if (result?.session) {
          writeLibrarySessionCache(storyId, result.session, {
            seedUpdatedAt: libraryStoriesById.value[storyId]?.seedUpdatedAt || 0,
          });
        }
      }
      if (seedResult?.seedReady) {
        result = {
          ...result,
          pioneer: Boolean(seedResult?.pioneer),
          pioneerMessage: seedResult?.pioneerMessage || "",
          seedReady: true
        };
      }
    } else {
      result = await withTimeout(
        (requestOptions) => generateCustomStorySession({
          opening: openingToUse,
          role: selectedRole.value
        }, requestOptions),
        120000,
        "自定义故事生成超时，请稍后重试。"
      );
    }
    const nextSession = result.session;
    logStoryGenerationDebug(nextSession, isPresetOpening ? "bookshelf-start-library-session" : "bookshelf-generate-custom-session");
    if (result?.pioneer) {
      const pioneerMessage = result?.pioneerMessage || "你是这颗土豆宇宙的播种者，首次生成会稍慢。";
      tipMessage.value = pioneerMessage;
      sessionStorage.setItem("potato-novel-entry-tip", pioneerMessage);
      const openingId = libraryStoryIdByOpening(openingToUse);
      if (openingId) {
        libraryStoriesById.value = {
          ...libraryStoriesById.value,
          [openingId]: {
            ...(libraryStoriesById.value[openingId] || {}),
            id: openingId,
            seedReady: true,
            seedUpdatedAt: Date.now() / 1000
          }
        };
        persistLibraryStoriesCache();
      }
    } else {
      sessionStorage.removeItem("potato-novel-entry-tip");
    }
    if (isPresetOpening) {
      setCacheState(openingToUse, {
        status: "ready",
        mode: "preload",
        sessionId: nextSession?.id || "",
        progress: 100,
        phase: "已完成"
      });
    }
    sessionStorage.setItem("potato-novel-story-session", JSON.stringify(nextSession));
    setTransferredStorySession(nextSession);
    router.push({
      path: "/story/result",
      query: {
        entry: entryMode,
        pioneer: result?.pioneer ? "1" : "0"
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
  const rawTitle = String(opening || "")
    .split("\n")
    .find((line) => line.trim())
    ?.trim()
    ?.replace(/^《/, "")
    ?.replace(/》$/, "") || "未命名作品";
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
            <div class="space-y-1 text-right">
              <p class="text-xl text-paper-700/45">{{ stories.length }} 部作品</p>
              <p v-if="shelfBooks.length" class="text-xs text-paper-700/45">长按封面可删除</p>
            </div>
          </div>

          <div v-if="shelfBooks.length" class="hide-scrollbar flex gap-4 overflow-x-auto pb-2">
            <button
              v-for="book in shelfBooks"
              :key="book.id"
              class="book-cover active-press relative text-left"
              :disabled="deletingStoryId === book.id"
              @click="openSavedStory(book.id)"
              @pointerdown="beginStoryDeleteLongPress(book.story)"
              @pointerup="clearStoryDeleteTimer"
              @pointerleave="clearStoryDeleteTimer"
              @pointercancel="clearStoryDeleteTimer"
              @contextmenu.prevent
            >
              <div class="absolute inset-0" :class="book.tint"></div>
              <div class="absolute inset-x-0 bottom-0 z-10 px-4 pb-5">
                <p class="line-clamp-2 font-serif text-base leading-6 text-white">
                  {{ book.title }}
                </p>
                <p v-if="pressedStoryId === book.id" class="mt-2 text-[0.68rem] font-semibold tracking-[0.06em] text-white/92">
                  继续按住即可删除
                </p>
                <p v-else-if="deletingStoryId === book.id" class="mt-2 text-[0.68rem] font-semibold tracking-[0.06em] text-white/92">
                  正在删除
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
                  :disabled="generating"
                  @click="handleGenerate"
                >
                  {{ generating ? "进入中..." : "进入故事" }}
                </button>
              </div>
            </div>
          </article>

          <div class="space-y-5 pt-2">
            <button
              v-for="(libraryStory, index) in libraryStoryRows"
              :key="libraryStory.id"
              class="paper-card active-press grid grid-cols-[1fr_10rem] overflow-hidden text-left"
              :disabled="generating"
              @click="handleGenerate(libraryStory.opening)"
            >
              <div class="space-y-4 px-6 py-6">
                <div class="flex items-center gap-3">
                  <span class="inline-flex rounded-xl bg-paper-100 px-4 py-2 text-sm font-semibold text-paper-800">
                    {{ templateTags[index % templateTags.length] }}
                  </span>
                </div>
                <h3 class="font-serif text-[2rem] font-semibold leading-tight text-paper-900">
                  {{ libraryStory.title }}
                </h3>
                <p class="line-clamp-2 text-[1rem] leading-8 text-paper-700">
                  {{ libraryStory.summary }}
                </p>
              </div>

              <div class="relative min-h-full">
                <div
                  class="absolute right-0 top-0 h-full w-full"
                  :class="coverTints[index % coverTints.length]"
                ></div>
                <div class="absolute left-0 top-0 h-full w-1 bg-accent-400/70"></div>
                <div class="absolute bottom-3 right-3 left-3 space-y-2">
                  <p
                    v-if="libraryStory.seedReady"
                    class="text-right text-[0.7rem] font-semibold tracking-[0.08em] text-white/92"
                  >
                    已播种
                  </p>
                  <p
                    v-if="libraryStory.seedReady"
                    class="text-right text-[0.62rem] font-medium tracking-[0.04em] text-white/82"
                  >
                    已有数据库故事包
                  </p>
                </div>
              </div>
            </button>
          </div>

          <p v-if="selectedOpening && openingMode === 'preset'" class="rounded-2xl bg-paper-100/80 px-4 py-3 text-sm text-paper-800">
            模板卡片点一下就会进入；未播种会首访生成，已播种会直接复用数据库故事包。
          </p>
          <p v-if="tipMessage" class="rounded-2xl bg-amber-50 px-4 py-3 text-sm text-amber-700">{{ tipMessage }}</p>
          <p v-if="error" class="rounded-2xl bg-red-50 px-4 py-3 text-sm text-red-700">{{ error }}</p>
        </div>
      </section>
    </section>
  </main>
</template>
