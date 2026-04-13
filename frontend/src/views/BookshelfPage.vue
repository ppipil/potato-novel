<script setup>
import { computed, onMounted, onUnmounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
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
import {
  readCustomPackagesCache,
  readLibrarySessionCache,
  readLibraryStoriesCache,
  readStoriesCache,
  upsertCustomPackageCache,
  writeLibrarySessionCache,
  writeLibraryStoriesCache,
  writeStoriesCache
} from "../lib/storyCache";
import { setTransferredStorySession } from "../lib/storySessionTransfer";
import { clearUserCache, readUserCache, writeUserCache } from "../lib/userCache";

const router = useRouter();
const route = useRoute();
const user = ref(null);
const viewerMode = ref("authenticated");
const activeShelfTab = ref("public");
const openingMode = ref("custom");
const selectedOpening = ref("");
const customOpening = ref("");
const selectedRole = ref("主人公");
const stories = ref([]);
const customPackages = ref([]);
const generating = ref(false);
const generatingLabel = ref("");
const generatingElapsedSec = ref(0);
const generatingEntryMode = ref("");
const bootstrapping = ref(true);
const error = ref("");
const tipMessage = ref("");
const activeSeed = ref("");
const preloadedSession = ref(null);
const dismissedHints = ref({});
const cacheStates = ref({});
const libraryStoriesById = ref({});
const deletingStoryId = ref("");
const pressedStoryId = ref("");
const suppressClickStoryId = ref("");
const CACHE_STORAGE_KEY = "potato-novel-cache-states";
const CACHE_DEBUG_KEY = "potato-novel-debug-cache-states";
const OPEN_SHELF_TAB_KEY = "potato-novel-open-shelf-tab";
const FORCE_REFRESH_LIBRARY_KEY = "potato-novel-force-refresh-library";
const WORKBENCH_UNLOCK_KEY = "potato-novel-workbench-unlock-v1";
const BACKGROUND_READY_KEY = "potato-novel-background-ready-session";
const BACKGROUND_PENDING_KEY = "potato-novel-background-pending-generation";
const BACKGROUND_PENDING_TTL_MS = 12 * 60 * 1000;
const DISMISSED_HINTS_KEY = "potato-novel-dismissed-hints-v1";
const LIBRARY_STORIES_CACHE_TTL_MS = 5 * 60 * 1000;
const STORY_DELETE_LONG_PRESS_MS = 600;
const GUEST_CACHE_USER_ID = "__guest_local__";
let storyDeleteTimer = 0;
let generatingTicker = 0;
let workbenchTapTimer = 0;
let bookshelfMounted = true;
const workbenchTapCount = ref(0);
const showWorkbenchEntry = ref(false);

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
const isGuestViewer = computed(() => viewerMode.value === "guest");
const effectiveUserId = computed(() => user.value?.userId || GUEST_CACHE_USER_ID);

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

const customPackageCards = computed(() =>
  customPackages.value.map((item, index) => ({
    id: item.id,
    title: formatBookCoverTitle(item?.title || item?.opening || "未命名互动包"),
    summary: String(item?.opening || "").slice(0, 60),
    tint: coverTints[index % coverTints.length],
    session: item?.session || null,
  }))
);

const activeOpening = computed(() => {
  return openingMode.value === "custom"
    ? customOpening.value.trim() || activeSeed.value || freeCreationSeeds[0]
    : selectedOpening.value;
});

const packageStatusText = computed(() => {
  if (openingMode.value === "custom") {
    return isGuestViewer.value
      ? "游客模式会生成完整故事包并保存在本机“我的”中，不会上传云端。"
      : "自定义开头会直接生成完整故事包，生成完成后进入阅读。";
  }
  const openingId = libraryStoryIdByOpening(selectedOpening.value);
  const info = openingId ? libraryStoriesById.value[openingId] : null;
  if (info?.seedReady) {
    return "这本模板已播种完成，点击会直接复用数据库故事包。";
  }
  return "这本模板还未播种，首次进入会触发模型生成并写入数据库。";
});
const showGuestBannerHint = computed(() => isGuestViewer.value && !dismissedHints.value.guest_banner);
const showRoleHint = computed(() => !dismissedHints.value.role_tip);
const showPackageHint = computed(() => !dismissedHints.value.package_tip);
const showMarketHint = computed(() => !dismissedHints.value.market_tip);

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

function loadDismissedHints() {
  try {
    const raw = localStorage.getItem(DISMISSED_HINTS_KEY);
    if (!raw) {
      return {};
    }
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    return {};
  }
}

function persistDismissedHints() {
  localStorage.setItem(DISMISSED_HINTS_KEY, JSON.stringify(dismissedHints.value));
}

function dismissHint(key) {
  dismissedHints.value = {
    ...dismissedHints.value,
    [key]: true,
  };
  persistDismissedHints();
}

function loadWorkbenchUnlock() {
  try {
    showWorkbenchEntry.value = localStorage.getItem(WORKBENCH_UNLOCK_KEY) === "1";
  } catch {
    showWorkbenchEntry.value = false;
  }
}

function unlockWorkbenchEntry() {
  showWorkbenchEntry.value = true;
  try {
    localStorage.setItem(WORKBENCH_UNLOCK_KEY, "1");
  } catch {
    // ignore localStorage failures
  }
  tipMessage.value = "已解锁隐藏入口：导入工作台";
}

function handleMarketTitleSecretTap() {
  if (showWorkbenchEntry.value) {
    return;
  }
  workbenchTapCount.value += 1;
  if (workbenchTapTimer) {
    window.clearTimeout(workbenchTapTimer);
  }
  workbenchTapTimer = window.setTimeout(() => {
    workbenchTapCount.value = 0;
  }, 1800);
  if (workbenchTapCount.value >= 5) {
    unlockWorkbenchEntry();
    workbenchTapCount.value = 0;
    if (workbenchTapTimer) {
      window.clearTimeout(workbenchTapTimer);
      workbenchTapTimer = 0;
    }
  }
}

function buildViewerScopeKey(mode = viewerMode.value, userId = effectiveUserId.value) {
  const normalizedMode = mode === "guest" ? "guest" : "authenticated";
  const normalizedUserId = userId || GUEST_CACHE_USER_ID;
  return `${normalizedMode}:${normalizedUserId}`;
}

function loadPendingGenerationPayload() {
  try {
    const pendingRaw = sessionStorage.getItem(BACKGROUND_PENDING_KEY);
    if (!pendingRaw) {
      return null;
    }
    const pendingPayload = JSON.parse(pendingRaw);
    const startedAt = Number(pendingPayload?.startedAt || 0);
    const ageMs = startedAt > 0 ? Date.now() - startedAt : Number.POSITIVE_INFINITY;
    const hasValidMode = pendingPayload?.entryMode === "custom" || pendingPayload?.entryMode === "library";
    const ownerScopeKey = String(pendingPayload?.ownerScopeKey || "");
    if (startedAt <= 0 || ageMs < 0 || ageMs > BACKGROUND_PENDING_TTL_MS || !hasValidMode || !ownerScopeKey) {
      sessionStorage.removeItem(BACKGROUND_PENDING_KEY);
      return null;
    }
    return pendingPayload;
  } catch {
    sessionStorage.removeItem(BACKGROUND_PENDING_KEY);
    return null;
  }
}

function restorePendingGenerationForScope(scopeKey, pendingPayload) {
  if (!pendingPayload) {
    return;
  }
  if (pendingPayload.ownerScopeKey !== scopeKey) {
    sessionStorage.removeItem(BACKGROUND_PENDING_KEY);
    return;
  }
  generating.value = true;
  generatingEntryMode.value = pendingPayload?.entryMode || "";
  generatingLabel.value = pendingPayload?.label || "正在后台生成剧情";
  startGeneratingTicker();
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
  const queryTab = route.query.tab === "mine" || route.query.tab === "public" ? route.query.tab : "";
  const rememberedTab = sessionStorage.getItem(OPEN_SHELF_TAB_KEY);
  const legacyForceMine = sessionStorage.getItem("potato-novel-open-mine-tab") === "1";
  const nextTab = queryTab || (rememberedTab === "mine" || rememberedTab === "public" ? rememberedTab : "") || (legacyForceMine ? "mine" : "");
  if (nextTab === "mine" || nextTab === "public") {
    activeShelfTab.value = nextTab;
  }
  sessionStorage.removeItem(OPEN_SHELF_TAB_KEY);
  sessionStorage.removeItem("potato-novel-open-mine-tab");
  const forceRefreshLibrary = sessionStorage.getItem(FORCE_REFRESH_LIBRARY_KEY) === "1";
  sessionStorage.removeItem(FORCE_REFRESH_LIBRARY_KEY);
  bookshelfMounted = true;
  const pendingPayload = loadPendingGenerationPayload();
  try {
    const readyRaw = sessionStorage.getItem(BACKGROUND_READY_KEY);
    if (readyRaw) {
      const readyPayload = JSON.parse(readyRaw);
      if (readyPayload?.session?.id) {
        tipMessage.value = readyPayload.message || "你离开页面时那局已经准备好了，点这里继续。";
        preloadedSession.value = readyPayload.session;
      }
    }
  } catch {
    // ignore malformed background-ready payload
  }
  console.info("[potato-bookshelf] mounted");
  if (!customOpening.value) {
    activeSeed.value = freeCreationSeeds[Math.floor(Math.random() * freeCreationSeeds.length)];
    customOpening.value = activeSeed.value;
  }
  dismissedHints.value = loadDismissedHints();
  loadWorkbenchUnlock();
  cacheStates.value = loadCacheStates();
  const libraryStoriesCache = loadLibraryStoriesCache();
  libraryStoriesById.value = libraryStoriesCache.data || {};
  const hasCachedLibraryStories = libraryStoryRows.value.length > 0;
  if (!selectedOpening.value && libraryStoryRows.value.length) {
    selectedOpening.value = libraryStoryRows.value[0].opening;
  }
  const cachedUser = readUserCache();
    if (cachedUser) {
      viewerMode.value = "authenticated";
      user.value = cachedUser;
      restorePendingGenerationForScope(buildViewerScopeKey("authenticated", cachedUser.userId || ""), pendingPayload);
      const cachedStories = readStoriesCache(cachedUser.userId || "");
    if (cachedStories.length) {
      stories.value = cachedStories;
      if (nextTab === "mine") {
        activeShelfTab.value = "mine";
      }
      bootstrapping.value = false;
    }
    customPackages.value = readCustomPackagesCache(cachedUser.userId || "");
  }
  try {
    const meResult = await getCurrentUser();
    if (!meResult.authenticated) {
      clearUserCache();
      viewerMode.value = "guest";
      user.value = { userId: GUEST_CACHE_USER_ID, name: "游客旅人" };
      restorePendingGenerationForScope(buildViewerScopeKey("guest", GUEST_CACHE_USER_ID), pendingPayload);
      stories.value = readStoriesCache(GUEST_CACHE_USER_ID);
      customPackages.value = readCustomPackagesCache(GUEST_CACHE_USER_ID);
      activeShelfTab.value = stories.value.length ? "mine" : "public";
      if (!hasCachedLibraryStories || forceRefreshLibrary) {
        await refreshLibraryStories();
      } else if (!isLibraryStoriesCacheFresh(libraryStoriesCache.updatedAt)) {
        void refreshLibraryStories();
      }
      return;
    }
    viewerMode.value = "authenticated";
    user.value = meResult.user;
    restorePendingGenerationForScope(buildViewerScopeKey("authenticated", meResult.user?.userId || ""), pendingPayload);
    writeUserCache(meResult.user);

    const userId = user.value?.userId || "";
    if (!hasCachedLibraryStories || forceRefreshLibrary) {
      await refreshLibraryStories();
    } else if (!isLibraryStoriesCacheFresh(libraryStoriesCache.updatedAt)) {
      void refreshLibraryStories();
    }
    const cachedStories = readStoriesCache(userId);
    if (cachedStories.length) {
      if (nextTab === "mine") {
        activeShelfTab.value = "mine";
      }
      customPackages.value = readCustomPackagesCache(userId);
      void refreshStories(userId).catch((err) => {
        console.warn("[potato-bookshelf] background story refresh failed", err);
      });
      return;
    }

    await refreshStories(userId);
    customPackages.value = readCustomPackagesCache(userId);
    if (stories.value.length && nextTab === "mine") {
      activeShelfTab.value = "mine";
    }
  } catch {
    if (!user.value) {
      clearUserCache();
      viewerMode.value = "guest";
      user.value = { userId: GUEST_CACHE_USER_ID, name: "游客旅人" };
      restorePendingGenerationForScope(buildViewerScopeKey("guest", GUEST_CACHE_USER_ID), pendingPayload);
      stories.value = readStoriesCache(GUEST_CACHE_USER_ID);
      customPackages.value = readCustomPackagesCache(GUEST_CACHE_USER_ID);
      activeShelfTab.value = stories.value.length ? "mine" : "public";
    }
  } finally {
    if (bootstrapping.value) {
      bootstrapping.value = false;
    }
  }
});

onUnmounted(() => {
  bookshelfMounted = false;
  stopGeneratingTicker();
  if (workbenchTapTimer) {
    window.clearTimeout(workbenchTapTimer);
    workbenchTapTimer = 0;
  }
});

async function refreshStories(userId = user.value?.userId || "") {
  if (isGuestViewer.value) {
    stories.value = readStoriesCache(GUEST_CACHE_USER_ID);
    return;
  }
  const storiesResult = await listStories();
  stories.value = mergeStoryShelf(readStoriesCache(userId), storiesResult.stories || []);
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

function hasReusableLocalLibrarySession(storyId) {
  if (!storyId) {
    return false;
  }
  const seedUpdatedAt = libraryStoriesById.value[storyId]?.seedUpdatedAt || 0;
  const cachedLibrarySession = readLibrarySessionCache(storyId);
  return isLibrarySessionCacheUsable(cachedLibrarySession, seedUpdatedAt);
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
  const confirmed = window.confirm(`确认删除《${title}》吗？删除后会从“我的故事间”中移除。`);
  if (!confirmed) {
    suppressClickStoryId.value = "";
    return;
  }

  deletingStoryId.value = story.id;
  const previousStories = [...stories.value];
  const nextStories = stories.value.filter((item) => item.id !== story.id);
  stories.value = nextStories;
  const userId = effectiveUserId.value;
  if (userId) {
    writeStoriesCache(userId, nextStories);
  }
  if (isGuestViewer.value) {
    deletingStoryId.value = "";
    suppressClickStoryId.value = "";
    error.value = "";
    return;
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

async function withTimeout(requestFactory, timeoutMs = 300000, message = "进入故事超时，请稍后重试") {
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

function startGeneratingTicker() {
  stopGeneratingTicker();
  try {
    const pendingRaw = sessionStorage.getItem(BACKGROUND_PENDING_KEY);
    if (pendingRaw) {
      const pendingPayload = JSON.parse(pendingRaw);
      const startedAt = Number(pendingPayload?.startedAt || 0);
      generatingElapsedSec.value = startedAt > 0 ? Math.max(0, Math.floor((Date.now() - startedAt) / 1000)) : 0;
    } else {
      generatingElapsedSec.value = 0;
    }
  } catch {
    generatingElapsedSec.value = 0;
  }
  generatingTicker = window.setInterval(() => {
    generatingElapsedSec.value += 1;
  }, 1000);
}

function stopGeneratingTicker() {
  if (generatingTicker) {
    window.clearInterval(generatingTicker);
    generatingTicker = 0;
  }
}

function mergeStoryShelf(localStories, remoteStories) {
  const localList = Array.isArray(localStories) ? localStories : [];
  const remoteList = Array.isArray(remoteStories) ? remoteStories : [];
  const merged = [...remoteList];
  for (const localItem of localList) {
    if (!localItem?.id) {
      continue;
    }
    if (remoteList.some((item) => item?.id === localItem.id)) {
      continue;
    }
    const localSessionId = String(localItem?.meta?.sessionId || "");
    const hasRemoteSession = localSessionId && remoteList.some((item) => String(item?.meta?.sessionId || "") === localSessionId);
    if (!hasRemoteSession) {
      merged.push(localItem);
    }
  }
  return merged.filter((item, index, arr) => arr.findIndex((row) => row?.id === item?.id) === index);
}

function normalizeGenerationError(err) {
  const message = err instanceof Error ? err.message : String(err || "");
  if (!message) {
    return "进入故事失败，请稍后重试。";
  }
  if (message.includes("Failed to fetch") || message.includes("NetworkError") || message.includes("网络")) {
    return "网络连接不稳定，故事暂时没连上。请检查网络后重试。";
  }
  if (message.includes("超时")) {
    return `${message} 你可以先浏览书架，稍后再试。`;
  }
  return message;
}

function openCustomPackage(item) {
  const sessionPayload = item?.session;
  if (!sessionPayload?.id) {
    return;
  }
  sessionStorage.setItem("potato-novel-story-session", JSON.stringify(sessionPayload));
  setTransferredStorySession(sessionPayload);
  router.push({
    path: "/story/result",
    query: {
      entry: "custom",
      pioneer: "0",
      fromTab: "mine",
    }
  });
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
  generatingLabel.value = "正在准备故事...";
  try {
    const isPresetOpening = Boolean(libraryStoryIdByOpening(openingToUse));
    const entryMode = isPresetOpening ? "library" : "custom";
    generatingEntryMode.value = entryMode;
    startGeneratingTicker();
    generatingLabel.value = entryMode === "custom"
      ? "正在生成自定义剧情（可能需要几分钟）"
      : "正在准备模板剧情";
    sessionStorage.setItem(
      BACKGROUND_PENDING_KEY,
      JSON.stringify({
        startedAt: Date.now(),
        entryMode,
        opening: openingToUse,
        label: generatingLabel.value,
        ownerScopeKey: buildViewerScopeKey(),
      })
    );
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
            "首次播种正在生成完整故事包（可能需要 1-8 分钟），当前请求超时。"
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
        300000,
        "自定义故事生成超时（当前链路可能需要数分钟）。"
      );
    }
    const nextSession = result.session;
    // 先落地结果，避免页面卸载导致成功结果丢失
    sessionStorage.setItem("potato-novel-story-session", JSON.stringify(nextSession));
    setTransferredStorySession(nextSession);

    const backgroundReadyPayload = {
      session: nextSession,
      message: "你离开页面时那局已经准备好了，点这里继续。"
    };
    sessionStorage.setItem(BACKGROUND_READY_KEY, JSON.stringify(backgroundReadyPayload));
    preloadedSession.value = nextSession;
    if (!isPresetOpening) {
      upsertCustomPackageCache(effectiveUserId.value, nextSession);
      customPackages.value = readCustomPackagesCache(effectiveUserId.value);
      activeShelfTab.value = "mine";
    }

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
    if (!bookshelfMounted) {
      return;
    }
    sessionStorage.removeItem(BACKGROUND_READY_KEY);
    preloadedSession.value = null;
    router.push({
      path: "/story/result",
      query: {
        entry: entryMode,
        pioneer: result?.pioneer ? "1" : "0",
        fromTab: activeShelfTab.value === "public" ? "public" : "mine",
      }
    });
  } catch (err) {
    error.value = normalizeGenerationError(err);
  } finally {
    sessionStorage.removeItem(BACKGROUND_PENDING_KEY);
    generating.value = false;
    generatingEntryMode.value = "";
    generatingLabel.value = "";
    stopGeneratingTicker();
  }
}

function handleCustomInput() {
  openingMode.value = "custom";
}

function handleCustomFocus() {
  openingMode.value = "custom";
  if (customOpening.value === activeSeed.value) {
    customOpening.value = "";
  }
}

function handleCustomBlur() {
  if (customOpening.value.trim()) {
    return;
  }
  if (!activeSeed.value) {
    activeSeed.value = freeCreationSeeds[Math.floor(Math.random() * freeCreationSeeds.length)];
  }
  customOpening.value = activeSeed.value;
}

function continueBackgroundReadySession() {
  if (!preloadedSession.value?.id) {
    return;
  }
  const nextSession = preloadedSession.value;
  sessionStorage.setItem("potato-novel-story-session", JSON.stringify(nextSession));
  setTransferredStorySession(nextSession);
  sessionStorage.removeItem(BACKGROUND_READY_KEY);
  preloadedSession.value = null;
  tipMessage.value = "";
  router.push({
    path: "/story/result",
    query: {
      entry: "custom",
      pioneer: "0",
      fromTab: activeShelfTab.value === "public" ? "public" : "mine",
    }
  });
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
        :visible="bootstrapping"
        :title="'正在整理你的书架'"
        :description="'优先读取本地缓存，并和云端故事记录做一次同步。'"
      />

      <header class="sticky top-0 z-20 -mx-6 mb-8 border-b border-paper-200/60 bg-paper-50/92 px-6 pb-4 pt-2 backdrop-blur-xl sm:-mx-8 sm:px-8">
        <div class="flex items-center justify-between gap-4">
          <div class="space-y-2">
            <p class="text-sm uppercase tracking-[0.24em] text-paper-700/55">{{ isGuestViewer ? "Guest Mode" : "Welcome Back" }}</p>
            <h1 class="font-serif text-[2.2rem] font-semibold text-paper-900">
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

      <section class="space-y-6 pb-10">
        <div class="relative overflow-hidden rounded-[24px] border border-paper-200 bg-gradient-to-r from-white/82 to-paper-100/85 p-1.5 shadow-[0_10px_24px_rgba(74,59,50,0.08)]">
          <div class="grid grid-cols-2 gap-1.5">
            <button
              class="active-press rounded-[18px] px-4 py-2.5 text-sm font-semibold tracking-[0.06em]"
              :class="activeShelfTab === 'public' ? 'bg-paper-900 text-paper-50 shadow-[0_8px_16px_rgba(45,36,30,0.24)]' : 'bg-white/72 text-paper-800'"
              @click="activeShelfTab = 'public'"
            >
              逛书市
            </button>
            <button
              class="active-press rounded-[18px] px-4 py-2.5 text-sm font-semibold tracking-[0.06em]"
              :class="activeShelfTab === 'mine' ? 'bg-paper-900 text-paper-50 shadow-[0_8px_16px_rgba(45,36,30,0.24)]' : 'bg-white/72 text-paper-800'"
              @click="activeShelfTab = 'mine'"
            >
              我的故事
            </button>
          </div>
        </div>

        <div
          v-if="showGuestBannerHint"
          class="relative rounded-2xl border border-paper-200/80 bg-gradient-to-r from-white to-paper-100/80 px-4 py-3 pr-11 text-sm text-paper-700 shadow-[0_8px_20px_rgba(74,59,50,0.06)]"
        >
          <p>当前为游客模式：你的故事只保存在当前设备；登录后可同步到云端并使用尾声签语。</p>
          <button
            class="active-press absolute -right-1 -top-1 h-5 w-5 rounded-full border border-paper-200 bg-white/95 text-[0.72rem] leading-none text-paper-700/70 transition hover:text-paper-900 hover:shadow-[0_4px_8px_rgba(74,59,50,0.14)]"
            type="button"
            aria-label="关闭提示"
            @click="dismissHint('guest_banner')"
          >
            ×
          </button>
        </div>

        <template v-if="activeShelfTab === 'mine'">
          <div class="space-y-5">
            <div class="flex items-end justify-between">
              <h2 class="section-title">我的故事间</h2>
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
              你的宇宙还是空的，先写一个开局吧。
            </div>
          </div>

          <article class="paper-card relative overflow-hidden px-5 py-5">
            <div class="absolute right-6 top-6 h-16 w-16 rounded-full bg-accent-400/20 blur-2xl"></div>
            <div class="space-y-5">
              <div class="flex items-center justify-between gap-3 text-accent-500">
                <div class="flex items-center gap-3">
                  <span class="text-2xl">✎</span>
                  <h3 class="text-[1.55rem] font-semibold">自由创作</h3>
                </div>
                <span class="rounded-full border border-paper-300 bg-white/80 px-3 py-1 text-xs font-semibold text-paper-700">
                  仅你可见
                </span>
              </div>

              <textarea
                v-model="customOpening"
                class="shadow-inner-soft min-h-32 w-full resize-none rounded-[24px] border border-paper-100 bg-paper-50 px-5 py-4 font-serif text-[1rem] leading-8 placeholder:text-paper-700/28"
                :class="customOpening === activeSeed ? 'text-paper-700/42' : 'text-paper-900'"
                placeholder="描述你的故事开局和你的身份..."
                @focus="handleCustomFocus"
                @blur="handleCustomBlur"
                @input="handleCustomInput"
              />

              <div
                v-if="generating && generatingEntryMode === 'custom'"
                class="px-0.5 py-0.5"
              >
                <p class="text-[0.8rem] font-semibold text-amber-700">{{ generatingLabel }}</p>
                <p class="text-[0.68rem] text-amber-700/76">已等待 {{ generatingElapsedSec }}s · 你可以继续浏览书城</p>
              </div>

              <div class="space-y-3">
                <div
                  v-if="showRoleHint"
                  class="relative rounded-2xl border border-paper-200/75 bg-white/90 px-4 py-3 pr-11 text-sm text-paper-800 shadow-[0_8px_18px_rgba(74,59,50,0.05)]"
                >
                  <p>当前默认以“{{ selectedRole }}”身份进入故事，完成后会进入你的私人宇宙书架。</p>
                  <button
                    class="active-press absolute -right-1 -top-1 h-5 w-5 rounded-full border border-paper-200 bg-white/95 text-[0.72rem] leading-none text-paper-700/70 transition hover:text-paper-900 hover:shadow-[0_4px_8px_rgba(74,59,50,0.14)]"
                    type="button"
                    aria-label="关闭提示"
                    @click="dismissHint('role_tip')"
                  >
                    ×
                  </button>
                </div>
                <div
                  v-if="showPackageHint"
                  class="relative rounded-2xl border border-paper-200/75 bg-white/90 px-4 py-3 pr-11 text-sm text-paper-800 shadow-[0_8px_18px_rgba(74,59,50,0.05)]"
                >
                  <p>{{ packageStatusText }}</p>
                  <button
                    class="active-press absolute -right-1 -top-1 h-5 w-5 rounded-full border border-paper-200 bg-white/95 text-[0.72rem] leading-none text-paper-700/70 transition hover:text-paper-900 hover:shadow-[0_4px_8px_rgba(74,59,50,0.14)]"
                    type="button"
                    aria-label="关闭提示"
                    @click="dismissHint('package_tip')"
                  >
                    ×
                  </button>
                </div>
                <button
                  class="active-press rounded-[16px] bg-stone-500 px-5 py-3 text-xl font-semibold text-white disabled:opacity-60"
                  :disabled="generating"
                  @click="handleGenerate"
                >
                  {{ generating ? "生成中..." : "生成并进入" }}
                </button>
              </div>
            </div>
          </article>

          <div class="space-y-4 pt-2">
            <div class="flex items-end justify-between">
              <h3 class="font-serif text-[1.45rem] font-semibold text-paper-900">进行中的故事</h3>
              <p class="text-xs tracking-[0.08em] text-paper-700/58">可继续交互</p>
            </div>
            <div v-if="customPackageCards.length" class="space-y-3">
              <button
                v-for="(item, index) in customPackageCards"
                :key="item.id"
                class="paper-card active-press grid grid-cols-[1fr_7.2rem] overflow-hidden text-left"
                @click="openCustomPackage(item)"
              >
                <div class="space-y-2 px-4 py-4">
                  <span class="inline-flex rounded-xl bg-paper-100 px-3 py-1 text-[0.7rem] font-semibold text-paper-700">互动包</span>
                  <p class="font-serif text-[1.15rem] font-semibold leading-tight text-paper-900">{{ item.title }}</p>
                  <p class="line-clamp-2 text-sm leading-6 text-paper-700/80">{{ item.summary || "继续进入这段正在生长的宇宙。" }}</p>
                </div>
                <div class="relative min-h-full">
                  <div class="absolute inset-0" :class="item.tint"></div>
                  <div class="absolute inset-x-0 bottom-0 bg-black/28 px-2 py-2 text-right text-[0.62rem] font-semibold tracking-[0.08em] text-white/90">
                    继续互动
                  </div>
                </div>
              </button>
            </div>
            <div
              v-else
              class="rounded-[22px] border border-dashed border-paper-200 bg-white/60 px-4 py-6 text-center text-sm text-paper-700/65"
            >
              你还没有互动包。先在上面的自由创作生成一篇，就会在这里出现可继续交互的入口。
            </div>
          </div>
        </template>

        <template v-else>
          <div class="space-y-4">
            <div
              v-if="generating && generatingEntryMode === 'library'"
              class="rounded-xl border border-amber-200 bg-amber-50/85 px-3 py-2"
            >
              <p class="text-[0.8rem] font-semibold text-amber-700">{{ generatingLabel }}</p>
              <p class="text-[0.68rem] text-amber-700/76">已等待 {{ generatingElapsedSec }}s · 你可以继续浏览书市</p>
            </div>

            <div class="flex items-end justify-between">
              <h2 class="section-title" @click="handleMarketTitleSecretTap">土豆书市</h2>
              <div class="flex items-center gap-2">
                <button
                  v-if="!isGuestViewer && showWorkbenchEntry"
                  class="active-press rounded-full border border-paper-300 bg-white/80 px-3 py-2 text-[0.68rem] font-semibold tracking-[0.08em] text-paper-700"
                  @click="router.push('/workbench/library-import')"
                >
                  导入工作台
                </button>
                <button
                  class="active-press rounded-full border border-paper-300 bg-white/80 px-4 py-2 text-xs font-semibold tracking-[0.08em] text-paper-700"
                  @click="activeShelfTab = 'mine'"
                >
                  去写新故事
                </button>
              </div>
            </div>

            <div class="space-y-4">
              <button
                v-for="(libraryStory, index) in libraryStoryRows"
                :key="libraryStory.id"
                class="paper-card active-press grid grid-cols-[1fr_8.5rem] overflow-hidden text-left"
                @click="handleGenerate(libraryStory.opening)"
              >
                <div class="space-y-3 px-5 py-4">
                  <div class="flex items-center gap-3">
                    <span class="inline-flex rounded-xl bg-paper-100 px-3 py-1.5 text-xs font-semibold text-paper-800">
                      {{ templateTags[index % templateTags.length] }}
                    </span>
                  </div>
                  <h3 class="font-serif text-[1.55rem] font-semibold leading-tight text-paper-900">
                    {{ libraryStory.title }}
                  </h3>
                  <p class="line-clamp-2 text-[0.92rem] leading-6 text-paper-700">
                    {{ libraryStory.summary }}
                  </p>
                </div>

                <div class="relative min-h-full">
                  <div
                    class="absolute right-0 top-0 h-full w-full"
                    :class="coverTints[index % coverTints.length]"
                  ></div>
                  <div class="absolute left-0 top-0 h-full w-1 bg-accent-400/70"></div>
                  <div class="absolute bottom-3 right-3 left-3">
                    <span
                      v-if="libraryStory.seedReady"
                      class="ml-auto inline-flex items-center gap-1.5 rounded-full border border-white/80 bg-white/88 px-2.5 py-1 text-[0.62rem] font-semibold tracking-[0.02em] text-paper-800 backdrop-blur-[2px]"
                    >
                      <svg
                        v-if="hasReusableLocalLibrarySession(libraryStory.id)"
                        class="h-3.5 w-3.5 text-emerald-600"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        stroke-width="2"
                        stroke-linecap="round"
                        stroke-linejoin="round"
                        aria-hidden="true"
                      >
                        <path d="M20 6 9 17l-5-5" />
                      </svg>
                      <svg
                        v-else
                        class="h-3.5 w-3.5 text-amber-600"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        stroke-width="2"
                        stroke-linecap="round"
                        stroke-linejoin="round"
                        aria-hidden="true"
                      >
                        <path d="M12 3v12" />
                        <path d="m7 10 5 5 5-5" />
                        <path d="M5 21h14" />
                      </svg>
                      {{ hasReusableLocalLibrarySession(libraryStory.id) ? "已缓存" : "需下载" }}
                    </span>
                  </div>
                </div>
              </button>
            </div>

            <div
              v-if="showMarketHint"
              class="relative rounded-2xl border border-paper-200/75 bg-white/90 px-4 py-3 pr-11 text-sm text-paper-800"
            >
              <p>这里是大家都在逛的土豆书市；你写的故事会留在“我的故事”。</p>
              <button
                class="active-press absolute -right-1 -top-1 h-5 w-5 rounded-full border border-paper-200 bg-white/95 text-[0.72rem] leading-none text-paper-700/70 transition hover:text-paper-900"
                type="button"
                aria-label="关闭提示"
                @click="dismissHint('market_tip')"
              >
                ×
              </button>
            </div>
          </div>
        </template>

        <button
          v-if="tipMessage && preloadedSession?.id"
          class="active-press w-full rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-left text-sm text-amber-700"
          @click="continueBackgroundReadySession"
        >
          {{ tipMessage }}
        </button>
        <p v-else-if="tipMessage" class="rounded-2xl bg-amber-50 px-4 py-3 text-sm text-amber-700">{{ tipMessage }}</p>
        <p v-if="error" class="rounded-2xl bg-red-50 px-4 py-3 text-sm text-red-700">{{ error }}</p>
      </section>
    </section>
  </main>
</template>
