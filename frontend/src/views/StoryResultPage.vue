<script setup>
import { computed, onMounted, onUnmounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import LoadingOverlay from "../components/LoadingOverlay.vue";
import {
  analyzeStoryEnding,
  generateLibraryStorySeed,
  generateCustomStorySession,
  saveStory,
  startLibraryStoryFromSeed
} from "../lib/api";
import { readLibrarySessionCache, readLibraryStoriesCache, upsertStoryCache, writeLibrarySessionCache } from "../lib/storyCache";
import { consumeTransferredStorySession, setTransferredStorySession } from "../lib/storySessionTransfer";
import { readUserCache } from "../lib/userCache";

const router = useRouter();
const route = useRoute();
const session = ref(null);
const runtime = ref(null);
const error = ref("");
const entryTip = ref("");
const saveMessage = ref("");
const loading = ref(true);
const loadingLabel = ref("正在进入故事...");
const syncingSave = ref(false);
const choosingOption = ref(false);
const finalizedPayload = ref(null);
const currentIndex = ref(-1);
const endingAnalysis = ref(null);
const analyzingEnding = ref(false);
const optimisticSavedStoryId = ref("");
let choiceAudioContext = null;
const activeRequestControllers = new Set();
const currentUserId = computed(() => {
  const cachedUser = readUserCache();
  return session.value?.userId || session.value?.user?.userId || cachedUser?.userId || "";
});

const packageData = computed(() => session.value?.package || null);
const nodeMap = computed(() => {
  const entries = packageData.value?.nodes || [];
  return Object.fromEntries(entries.map((item) => [item.id, item]));
});
const currentNode = computed(() => {
  if (!runtime.value?.currentNodeId) {
    return null;
  }
  return nodeMap.value[runtime.value.currentNodeId] || null;
});
const currentNodeLoaded = computed(() => Boolean(currentNode.value?.loaded !== false && currentNode.value?.scene));

function cleanDisplayText(text) {
  let value = String(text || "").trim();
  while (true) {
    let updated = value;
    for (const prefix of ['", "', '","', "', '", ",'", "',", '["', "['", '",', "',"]) {
      if (updated.startsWith(prefix)) {
        updated = updated.slice(prefix.length).trimStart();
      }
    }
    if (updated.startsWith("[") && updated.length > 1 && [`"`, "'"].includes(updated[1])) {
      updated = updated.slice(2).trimStart();
    }
    if (updated === value) {
      break;
    }
    value = updated;
  }
  return value.trim().replace(/^[\s'",\]]+/, "").trim();
}

const currentParagraphs = computed(() => {
  const paragraphs = currentNode.value?.paragraphs;
  if (Array.isArray(paragraphs) && paragraphs.length > 0) {
    return paragraphs
      .map((item) => cleanDisplayText(item))
      .filter(Boolean);
  }

  const scene = cleanDisplayText(currentNode.value?.scene || "");
  return scene
    .split(/\n\s*\n+/)
    .map((item) => cleanDisplayText(item))
    .filter(Boolean);
});
const visibleParagraphs = computed(() =>
  currentParagraphs.value.slice(0, Math.max(0, Math.min(currentIndex.value + 1, currentParagraphs.value.length)))
);
const isRevealComplete = computed(() => {
  return currentParagraphs.value.length > 0 && currentIndex.value >= currentParagraphs.value.length - 1;
});
const isSessionComplete = computed(() => runtime.value?.status === "complete");
const isEndingNode = computed(() => currentNode.value?.kind === "ending" || isSessionComplete.value);
const canSave = computed(() => isSessionComplete.value && !syncingSave.value);
const canRequestEndingAnalysis = computed(() =>
  Boolean(session.value?.id) && isSessionComplete.value && isRevealComplete.value && !endingAnalysis.value && !analyzingEnding.value
);
const currentState = computed(() => runtime.value?.state || packageData.value?.initialState || {});
const pageTitle = computed(() => packageData.value?.title || "互动故事");
const openingLead = computed(() => session.value?.meta?.opening || "");
const showOpeningLead = computed(() => (runtime.value?.path?.length || 0) === 0 && Boolean(openingLead.value));
const packageStatus = computed(() => session.value?.packageStatus || "ready");
const choiceList = computed(() => {
  if (isSessionComplete.value || !currentNodeLoaded.value) {
    return [];
  }
  return currentNode.value?.choices || [];
});
const historyEntries = computed(() => {
  const entries = runtime.value?.entries || [];
  const tailLength = currentNode.value?.directorNote ? 2 : 1;
  return entries.slice(0, Math.max(entries.length - tailLength, 0));
});
const renderedHistory = computed(() =>
  historyEntries.value.map((item, index) => ({
    id: `${item.turn || "x"}-${index}`,
    type: item.label?.includes("玩家行动") ? "action" : item.label?.includes("局势提示") ? "note" : "story",
    label: item.label,
    text: item.text || ""
  }))
);
const overlayTitle = computed(() => {
  if (analyzingEnding.value) {
    return "正在解读你这颗土豆";
  }
  return "正在处理";
});
const overlayDescription = computed(() => {
  if (analyzingEnding.value) {
    return "SecondMe 正在根据你走出的分支生成一份结局签语。";
  }
  return "请稍候。";
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

function createRequestController() {
  const controller = new AbortController();
  activeRequestControllers.add(controller);
  return controller;
}

function releaseRequestController(controller) {
  if (controller) {
    activeRequestControllers.delete(controller);
  }
}

function abortActiveStoryRequests() {
  for (const controller of activeRequestControllers) {
    controller.abort();
  }
  activeRequestControllers.clear();
}
const recommendedUniverses = computed(() => {
  const currentTitle = pageTitle.value;
  const persona = normalizePersonaState(currentState.value?.persona || {});
  const extrovert = persona.extrovert_introvert || 0;
  const scheming = persona.scheming_naive || 0;
  const optimistic = persona.optimistic_pessimistic || 0;

  const libraryStories = readLibraryStoriesCache().rows || [];
  const preferred = libraryStories
    .filter((item) => item?.opening && item?.title !== currentTitle)
    .sort((left, right) => {
      const leftOpening = left?.opening || "";
      const rightOpening = right?.opening || "";
      const leftScore =
        (scheming > 0 && /怪谈|绞肉机|规则/.test(leftOpening) ? 1 : 0) +
        (optimistic + extrovert >= 0 && /修养|攻略|婚/.test(leftOpening) ? 1 : 0);
      const rightScore =
        (scheming > 0 && /怪谈|绞肉机|规则/.test(rightOpening) ? 1 : 0) +
        (optimistic + extrovert >= 0 && /修养|攻略|婚/.test(rightOpening) ? 1 : 0);
      return rightScore - leftScore;
    });

  return preferred.slice(0, 2);
});

function toNumber(value, fallback = 0) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function clamp(value, minValue, maxValue) {
  return Math.min(maxValue, Math.max(minValue, value));
}

function normalizeRelationshipState(relationship = {}) {
  const legacyFavor =
    toNumber(relationship?.["好感"], 0) +
    toNumber(relationship?.["信任"], 0) -
    toNumber(relationship?.["警惕"], 0);
  return {
    favor: toNumber(relationship?.favor, legacyFavor)
  };
}

function normalizePersonaState(persona = {}) {
  const legacySincerity = toNumber(persona?.["真诚"], 0);
  const legacyBlunt = toNumber(persona?.["嘴硬"], 0);
  const legacyScheming = toNumber(persona?.["心机"], 0);
  const legacyCourage = toNumber(persona?.["胆量"], 0);
  return {
    extrovert_introvert: toNumber(persona?.extrovert_introvert, legacyCourage - legacyBlunt),
    scheming_naive: toNumber(persona?.scheming_naive, legacyScheming),
    optimistic_pessimistic: toNumber(persona?.optimistic_pessimistic, legacySincerity - legacyBlunt)
  };
}

function normalizeChoiceEffects(effects = {}) {
  const relationshipEffects = effects?.relationship || {};
  const personaEffects = effects?.persona || {};
  const favorDelta = relationshipEffects.favor !== undefined
    ? toNumber(relationshipEffects.favor, 0)
    : toNumber(relationshipEffects?.["好感"], 0) +
      toNumber(relationshipEffects?.["信任"], 0) -
      toNumber(relationshipEffects?.["警惕"], 0);
  return {
    relationship: {
      favor: favorDelta
    },
    persona: {
      extrovert_introvert:
        toNumber(personaEffects.extrovert_introvert, 0) +
        toNumber(personaEffects?.["胆量"], 0) -
        toNumber(personaEffects?.["嘴硬"], 0),
      scheming_naive:
        toNumber(personaEffects.scheming_naive, 0) +
        toNumber(personaEffects?.["心机"], 0),
      optimistic_pessimistic:
        toNumber(personaEffects.optimistic_pessimistic, 0) +
        toNumber(personaEffects?.["真诚"], 0) -
        toNumber(personaEffects?.["嘴硬"], 0)
    }
  };
}

onMounted(async () => {
  const pioneerFromQuery = typeof route.query.pioneer === "string" && route.query.pioneer === "1";
  entryTip.value = sessionStorage.getItem("potato-novel-entry-tip") || "";
  if (!entryTip.value && pioneerFromQuery) {
    entryTip.value = "你是这颗土豆宇宙的播种者，首次生成需要多一点时间。";
  }
  const isPioneerEntry = pioneerFromQuery || Boolean(entryTip.value);
  if (entryTip.value) {
    sessionStorage.removeItem("potato-novel-entry-tip");
  }
  const entryType = typeof route.query.entry === "string" ? route.query.entry : "";
  loadingLabel.value = isPioneerEntry
    ? "你是这颗土豆宇宙的播种者，正在播种完整章节..."
    : entryType === "custom"
      ? "第一幕正在落页..."
      : entryType === "library"
        ? "正在翻开故事..."
        : "正在恢复故事会话...";
  const transferredSession = consumeTransferredStorySession();
  if (transferredSession?.id) {
    session.value = transferredSession;
    logStoryGenerationDebug(transferredSession, "transferred-session");
    runtime.value = restoreRuntime(transferredSession, transferredSession.runtime);
    persistLocalSession();
    loading.value = false;
    return;
  }

  const raw = sessionStorage.getItem("potato-novel-story-session");
  if (!raw) {
    loading.value = false;
    return;
  }

  try {
    const storedSession = JSON.parse(raw);
    if (!storedSession?.id) {
      loading.value = false;
      return;
    }
    session.value = storedSession;
    runtime.value = restoreRuntime(storedSession, storedSession.runtime);
    persistLocalSession();
    loading.value = false;

  } catch (err) {
    error.value = err instanceof Error ? err.message : "加载互动故事失败";
  } finally {
    loading.value = false;
  }
});

onUnmounted(() => {
  abortActiveStoryRequests();
});

function goBack() {
  abortActiveStoryRequests();
  analyzingEnding.value = false;
  loading.value = false;
  if (window.history.length > 1) {
    router.back();
    return;
  }
  router.push("/bookshelf");
}

function buildNodeEntries(node) {
  if (!node) {
    return [];
  }
  return [
    { turn: node.turn, label: node.stageLabel, text: node.scene },
    ...(node.directorNote ? [{ turn: node.turn, label: "局势提示", text: node.directorNote }] : [])
  ];
}

function cloneValue(value) {
  if (typeof structuredClone === "function") {
    return structuredClone(value);
  }
  return JSON.parse(JSON.stringify(value));
}

function buildLocalSessionFromCachedLibrary(openingId, cachedEntry, role = "主人公") {
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
    role
  };
  nextSession.runtime = {
    currentNodeId: rootNode.id,
    entries: buildNodeEntries(rootNode),
    path: [],
    state: cloneValue(nextSession.package?.initialState || {}),
    status: rootNode.kind === "ending" ? "complete" : "ongoing",
    endingNodeId: rootNode.kind === "ending" ? rootNode.id : "",
    summary: rootNode.kind === "ending" ? (rootNode.summary || rootNode.scene || "") : ""
  };
  return nextSession;
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

function applyChoiceEffects(previousState, choice, nextNode, nextPathLength) {
  const normalizedRelationship = normalizeRelationshipState(previousState?.relationship || {});
  const normalizedPersona = normalizePersonaState(previousState?.persona || {});
  const normalizedEffects = normalizeChoiceEffects(choice?.effects || {});
  const nextState = {
    stage: nextNode?.kind === "ending"
      ? "ending"
      : Number(nextNode?.turn || 1) <= 1
        ? "opening"
        : Number(nextNode?.turn || 1) >= 4
          ? "climax"
          : "conflict",
    flags: [...(previousState?.flags || [])],
    relationship: normalizedRelationship,
    persona: normalizedPersona,
    turn: Number(nextNode?.turn || nextPathLength || 1),
    endingHint: ""
  };

  Object.entries(normalizedEffects?.persona || {}).forEach(([key, value]) => {
    nextState.persona[key] = (nextState.persona[key] || 0) + Number(value || 0);
  });
  Object.entries(normalizedEffects?.relationship || {}).forEach(([key, value]) => {
    nextState.relationship[key] = (nextState.relationship[key] || 0) + Number(value || 0);
  });

  nextState.relationship.favor = clamp(nextState.relationship.favor || 0, -5, 5);
  nextState.persona.extrovert_introvert = clamp(nextState.persona.extrovert_introvert || 0, -5, 5);
  nextState.persona.scheming_naive = clamp(nextState.persona.scheming_naive || 0, -5, 5);
  nextState.persona.optimistic_pessimistic = clamp(nextState.persona.optimistic_pessimistic || 0, -5, 5);

  const style = choice?.style || "";
  if (["trust", "support", "soft"].includes(style) && !nextState.flags.includes("soft_route")) {
    nextState.flags.push("soft_route");
  }
  if (style === "tease" && !nextState.flags.includes("spark_route")) {
    nextState.flags.push("spark_route");
  }
  if (["strategy", "manipulation", "observation"].includes(style) && !nextState.flags.includes("hidden_route")) {
    nextState.flags.push("hidden_route");
  }
  if (nextNode?.kind === "ending") {
    if ((nextState.relationship.favor || 0) >= 2) {
      nextState.endingHint = "你把这个宇宙推向了高好感收束。";
    } else if ((nextState.persona.scheming_naive || 0) >= 2) {
      nextState.endingHint = "你用偏心机的策略推进了关系，结局会带一点反转后劲。";
    } else {
      nextState.endingHint = "这个宇宙留下了更克制也更耐回味的尾音。";
    }
  }
  return nextState;
}

function resolveInfluencedEndingNode(targetNode, projectedState) {
  if (!targetNode || targetNode.kind !== "ending") {
    return targetNode;
  }
  const endings = (packageData.value?.nodes || []).filter((item) => item?.kind === "ending");
  if (!endings.length) {
    return targetNode;
  }

  const favor = toNumber(projectedState?.relationship?.favor, 0);
  const extrovert = toNumber(projectedState?.persona?.extrovert_introvert, 0);
  const scheming = toNumber(projectedState?.persona?.scheming_naive, 0);
  const optimistic = toNumber(projectedState?.persona?.optimistic_pessimistic, 0);

  let preferredEndingType = "bittersweet";
  if (favor >= 2 && optimistic >= 0 && scheming <= 1) {
    preferredEndingType = "good";
  } else if (favor <= -1 || optimistic <= -2) {
    preferredEndingType = "open";
  } else if (scheming >= 2 || extrovert <= -1) {
    preferredEndingType = "bittersweet";
  } else if (favor >= 1) {
    preferredEndingType = "good";
  }

  const preferredEndingNode = endings.find((item) => item?.endingType === preferredEndingType);
  return preferredEndingNode || targetNode;
}

function playPageTurnSound() {
  if (typeof window === "undefined") {
    return;
  }
  const AudioContextCtor = window.AudioContext || window.webkitAudioContext;
  if (!AudioContextCtor) {
    return;
  }

  try {
    if (!choiceAudioContext) {
      choiceAudioContext = new AudioContextCtor();
    }
    if (choiceAudioContext.state === "suspended") {
      void choiceAudioContext.resume();
    }
    const now = choiceAudioContext.currentTime + 0.005;
    const master = choiceAudioContext.createGain();
    master.gain.setValueAtTime(0.001, now);
    master.gain.exponentialRampToValueAtTime(0.32, now + 0.01);
    master.gain.exponentialRampToValueAtTime(0.001, now + 0.18);
    master.connect(choiceAudioContext.destination);

    const toneA = choiceAudioContext.createOscillator();
    const gainA = choiceAudioContext.createGain();
    toneA.type = "triangle";
    toneA.frequency.setValueAtTime(980, now);
    toneA.frequency.exponentialRampToValueAtTime(620, now + 0.09);
    gainA.gain.setValueAtTime(0.001, now);
    gainA.gain.exponentialRampToValueAtTime(0.24, now + 0.008);
    gainA.gain.exponentialRampToValueAtTime(0.001, now + 0.1);
    toneA.connect(gainA);
    gainA.connect(master);

    const toneB = choiceAudioContext.createOscillator();
    const gainB = choiceAudioContext.createGain();
    toneB.type = "sine";
    toneB.frequency.setValueAtTime(430, now + 0.03);
    toneB.frequency.exponentialRampToValueAtTime(260, now + 0.16);
    gainB.gain.setValueAtTime(0.001, now + 0.03);
    gainB.gain.exponentialRampToValueAtTime(0.18, now + 0.045);
    gainB.gain.exponentialRampToValueAtTime(0.001, now + 0.17);
    toneB.connect(gainB);
    gainB.connect(master);

    toneA.start(now);
    toneA.stop(now + 0.11);
    toneB.start(now + 0.03);
    toneB.stop(now + 0.18);
  } catch (err) {
    try {
      if (localStorage.getItem("potato-story-debug") === "1") {
        console.warn("[potato-story-audio] page turn sound failed", err);
      }
    } catch {
      // ignore debug logging failures
    }
  }
}

function createInitialRuntime(sessionPayload) {
  const storyPackage = sessionPayload?.package;
  const rootNode = (storyPackage?.nodes || []).find((item) => item.id === storyPackage?.rootNodeId);
  if (!rootNode) {
    return null;
  }
  return {
    currentNodeId: rootNode.id,
    entries: buildNodeEntries(rootNode),
    path: [],
    state: structuredClone(storyPackage.initialState || {}),
    status: rootNode.kind === "ending" ? "complete" : "ongoing",
    endingNodeId: rootNode.kind === "ending" ? rootNode.id : "",
    summary: rootNode.kind === "ending" ? rootNode.summary || rootNode.scene : ""
  };
}

function restoreRuntime(sessionPayload, storedRuntime) {
  if (sessionPayload?.completedRun) {
    return {
      currentNodeId: sessionPayload.completedRun.currentNodeId || sessionPayload.completedRun.endingNodeId,
      entries: sessionPayload.completedRun.transcript || [],
      path: sessionPayload.completedRun.path || [],
      state: sessionPayload.completedRun.state || sessionPayload.package?.initialState || {},
      status: "complete",
      endingNodeId: sessionPayload.completedRun.endingNodeId || "",
      summary: sessionPayload.completedRun.summary || ""
    };
  }

  if (storedRuntime?.currentNodeId && nodeMapFromPackage(sessionPayload.package)[storedRuntime.currentNodeId]) {
    return {
      ...storedRuntime,
      entries: storedRuntime.entries || [],
      path: storedRuntime.path || [],
      state: storedRuntime.state || sessionPayload.package?.initialState || {},
      status: storedRuntime.status || "ongoing",
      endingNodeId: storedRuntime.endingNodeId || "",
      summary: storedRuntime.summary || ""
    };
  }

  return createInitialRuntime(sessionPayload);
}

function nodeMapFromPackage(storyPackage) {
  return Object.fromEntries((storyPackage?.nodes || []).map((item) => [item.id, item]));
}

function persistLocalSession() {
  if (!session.value) {
    return;
  }
  sessionStorage.setItem(
    "potato-novel-story-session",
    JSON.stringify({
      ...session.value,
      runtime: runtime.value
    })
  );
}

function mergeSession(nextSession) {
  session.value = nextSession;
  logStoryGenerationDebug(nextSession, "merge-session");
  persistLocalSession();
}

function buildCompletedRunPayload() {
  return {
    currentNodeId: runtime.value.currentNodeId,
    endingNodeId: runtime.value.endingNodeId,
    summary: runtime.value.summary,
    transcript: runtime.value.entries,
    state: runtime.value.state,
    path: runtime.value.path
  };
}

function buildOptimisticStoryText() {
  const title = pageTitle.value ? `《${pageTitle.value.replace(/^《|》$/g, "")}》` : "《未命名互动宇宙》";
  const metaLines = [
    title,
    `玩家身份：${session.value?.meta?.role || "主人公"}`,
    `创作者：${session.value?.meta?.author || "SecondMe 用户"}`
  ];
  const bodyLines = (runtime.value?.entries || [])
    .filter((item) => item?.text)
    .map((item) => {
      const label = item.label ? `【${item.label}】` : "";
      return `${label}\n${item.text}`;
    });
  return [...metaLines, ...bodyLines].join("\n\n");
}

function buildOptimisticSavedStory(finalized) {
  const turnCount = finalized?.meta?.turnCount || runtime.value?.path?.length + 1 || 1;
  return {
    id: `local-${session.value?.id || Date.now()}`,
    createdAt: Date.now(),
    updatedAt: Date.now(),
    userId: currentUserId.value,
    meta: {
      ...(finalized?.meta || {}),
      opening: finalized?.meta?.opening || session.value?.meta?.opening || "",
      role: finalized?.meta?.role || session.value?.meta?.role || "",
      author: finalized?.meta?.author || session.value?.meta?.author || "SecondMe 用户",
      sessionId: session.value?.id || "",
      turnCount,
      endingAnalysis: endingAnalysis.value || finalized?.meta?.endingAnalysis || null
    },
    story: finalized?.story || buildOptimisticStoryText()
  };
}

function revealNextParagraph() {
  if (currentParagraphs.value.length === 0 || isRevealComplete.value) {
    return;
  }
  currentIndex.value += 1;
}

async function chooseOption(choice) {
  if (!choice || !currentNode.value || isSessionComplete.value || choosingOption.value) {
    return;
  }

  choosingOption.value = true;
  error.value = "";
  saveMessage.value = "";
  try {
    const targetNode = nodeMap.value[choice.nextNodeId];
    if (!targetNode) {
      throw new Error("下一剧情节点不存在");
    }
    playPageTurnSound();
    const previousState = runtime.value?.state || packageData.value?.initialState || {};
    const projectedState = applyChoiceEffects(previousState, choice, targetNode, (runtime.value?.path?.length || 0) + 1);
    const nextNode = resolveInfluencedEndingNode(targetNode, projectedState);
    const nextPath = [
      ...(runtime.value?.path || []),
      {
        fromNodeId: currentNode.value.id,
        choiceId: choice.id,
        choiceText: choice.text,
        nextNodeId: nextNode.id,
        selectedNextNodeId: choice.nextNodeId,
        turn: currentNode.value.turn,
        effects: choice.effects || {}
      }
    ];
    const nextEntries = [
      ...(runtime.value?.entries || []),
      { turn: currentNode.value.turn, label: "玩家行动", text: choice.text },
      ...buildNodeEntries(nextNode)
    ];
    const nextState = applyChoiceEffects(previousState, choice, nextNode, nextPath.length + 1);
    runtime.value = {
      currentNodeId: nextNode.id,
      entries: nextEntries,
      path: nextPath,
      state: nextState,
      status: nextNode.kind === "ending" ? "complete" : "ongoing",
      endingNodeId: nextNode.kind === "ending" ? nextNode.id : "",
      summary: nextNode.kind === "ending" ? (nextNode.summary || nextNode.scene || "") : (runtime.value?.summary || "")
    };
    if (runtime.value.status === "complete") {
      session.value = {
        ...session.value,
        status: "complete",
        completedRun: buildCompletedRunPayload()
      };
    }
    currentIndex.value = -1;
    persistLocalSession();
  } catch (err) {
    error.value = err instanceof Error ? err.message : "推进故事失败";
  } finally {
    choosingOption.value = false;
  }
}

async function handleSave() {
  if (!isSessionComplete.value || syncingSave.value) {
    return;
  }

  syncingSave.value = true;
  error.value = "";
  saveMessage.value = "";
  const completedRun = buildCompletedRunPayload();
  const optimisticStory = buildOptimisticSavedStory({
    meta: {
      opening: session.value?.meta?.opening || "",
      role: session.value?.meta?.role || "",
      author: session.value?.meta?.author || "SecondMe 用户",
      turnCount: runtime.value?.path?.length + 1 || 1,
      endingAnalysis: endingAnalysis.value || null
    },
    story: buildOptimisticStoryText()
  });
  optimisticSavedStoryId.value = optimisticStory.id;
  upsertStoryCache(optimisticStory.userId, optimisticStory);
  saveMessage.value = `已加入书架，正在同步云端，共记录 ${optimisticStory.meta.turnCount || runtime.value.path.length + 1} 个回合。`;
  session.value = {
    ...session.value,
    status: "complete",
    completedRun: completedRun
  };
  persistLocalSession();

  void (async () => {
    try {
      const finalized = finalizedPayload.value || {
        story: buildOptimisticStoryText(),
        meta: {
          opening: session.value?.meta?.opening || "",
          role: session.value?.meta?.role || "",
          author: session.value?.meta?.author || "SecondMe 用户",
          turnCount: runtime.value?.path?.length + 1 || 1,
          status: "complete",
          state: runtime.value?.state || {},
          completedRun,
          package: session.value?.package || null
        }
      };
      finalizedPayload.value = finalized;
      const result = await saveStory({
        story: finalized.story,
        meta: {
          ...finalized.meta,
          endingAnalysis: endingAnalysis.value || finalized.meta?.endingAnalysis || null
        }
      });
      upsertStoryCache(result.story?.userId, result.story);
      saveMessage.value = `已保存，共记录 ${result.story.meta.turnCount || finalized.meta.turnCount || runtime.value.path.length + 1} 个回合。`;
    } catch (err) {
      saveMessage.value = "已加入本地书架，但云端同步失败，请稍后重试。";
      error.value = err instanceof Error ? err.message : "保存失败";
    } finally {
      syncingSave.value = false;
    }
  })();
}

async function ensureEndingAnalysis() {
  if (!isSessionComplete.value || endingAnalysis.value || analyzingEnding.value) {
    return;
  }

  analyzingEnding.value = true;
  const controller = createRequestController();
  try {
    const completedRunPayload = {
      summary: runtime.value.summary,
      transcript: runtime.value.entries,
      state: runtime.value.state,
      opening: session.value.meta?.opening || "",
      role: session.value.meta?.role || ""
    };
    const result = await analyzeStoryEnding({
      meta: completedRunPayload,
      story: runtime.value.summary || currentNode.value?.scene || ""
    }, { signal: controller.signal });
    releaseRequestController(controller);
    endingAnalysis.value = result.analysis;
  } catch (err) {
    if (err?.name !== "AbortError") {
      error.value = err instanceof Error ? err.message : "尾声分析生成失败";
    }
  } finally {
    releaseRequestController(controller);
    analyzingEnding.value = false;
  }
}

async function launchRecommendedUniverse(libraryStory) {
  loading.value = true;
  error.value = "";
  saveMessage.value = "";
  const controller = createRequestController();
  try {
    const isPresetOpening = Boolean(libraryStory?.id && libraryStory?.opening);
    const result = isPresetOpening
        ? await (async () => {
          const storyId = libraryStory.id;
          const seedUpdatedAt = Number(libraryStory?.seedUpdatedAt || 0);
          const cachedLibrarySession = readLibrarySessionCache(storyId);
          const localSession = isLibrarySessionCacheUsable(cachedLibrarySession, seedUpdatedAt)
            ? buildLocalSessionFromCachedLibrary(storyId, cachedLibrarySession, "主人公")
            : null;
          if (localSession) {
            return { ok: true, session: localSession, reused: false, localCacheHit: true };
          }
          try {
            const remoteResult = await startLibraryStoryFromSeed(
              storyId,
              { role: "主人公" },
              { signal: controller.signal }
            );
            if (remoteResult?.session) {
              writeLibrarySessionCache(storyId, remoteResult.session, { seedUpdatedAt });
            }
            return remoteResult;
          } catch (err) {
            if (err instanceof Error && err.message.includes("公共内容还没播种完成")) {
              await generateLibraryStorySeed(storyId, {}, { signal: controller.signal });
              const seededResult = await startLibraryStoryFromSeed(
                storyId,
                { role: "主人公" },
                { signal: controller.signal }
              );
              if (seededResult?.session) {
                writeLibrarySessionCache(storyId, seededResult.session, { seedUpdatedAt: Date.now() / 1000 });
              }
              return seededResult;
            }
            throw err;
          }
        })()
      : await generateCustomStorySession(
          { opening: libraryStory?.opening || "", role: "主人公" },
          { signal: controller.signal }
        );
    releaseRequestController(controller);
    setTransferredStorySession(result.session);
    sessionStorage.setItem("potato-novel-story-session", JSON.stringify(result.session));
    session.value = result.session;
    logStoryGenerationDebug(result.session, "launch-recommended-universe");
    runtime.value = restoreRuntime(result.session, result.session.runtime);
    endingAnalysis.value = null;
    finalizedPayload.value = null;
    currentIndex.value = -1;
    persistLocalSession();
  } catch (err) {
    if (err?.name !== "AbortError") {
      error.value = err instanceof Error ? err.message : "进入新宇宙失败";
    }
  } finally {
    releaseRequestController(controller);
    loading.value = false;
  }
}
</script>

<template>
  <main class="paper-shell">
    <section class="paper-page relative flex min-h-screen flex-col px-0 pb-0 pt-0">
      <LoadingOverlay
        :visible="analyzingEnding"
        :title="overlayTitle"
        :description="overlayDescription"
      />

      <header class="glass-panel fixed left-1/2 top-0 z-30 w-full max-w-md -translate-x-1/2 shrink-0 border-b border-paper-200/70 px-6 py-4 shadow-[0_10px_28px_rgba(74,59,50,0.08)] sm:px-8">
        <div class="flex items-center justify-between gap-3">
          <button
            class="active-press inline-flex h-11 min-w-11 items-center justify-center rounded-full border border-paper-200 bg-white/88 px-3 text-xl text-paper-700 shadow-[0_4px_14px_rgba(0,0,0,0.06)]"
            aria-label="返回"
            @click="goBack"
          >
            ←
          </button>
          <h1 class="mx-2 flex-1 truncate text-center font-serif text-[1.18rem] font-semibold text-paper-900">{{ pageTitle }}</h1>
          <div class="flex justify-end">
        <button
          class="active-press min-w-[6.5rem] rounded-full border border-paper-200 bg-white/80 px-3 py-2 text-sm font-semibold text-accent-600 shadow-[0_4px_14px_rgba(0,0,0,0.05)] disabled:text-paper-700/40"
          :disabled="!canSave"
          @click="handleSave"
        >
          {{ syncingSave ? "同步中" : isSessionComplete ? "保存书架" : "未完待续" }}
        </button>
          </div>
        </div>
      </header>

      <div v-if="loading" class="flex flex-1 items-center justify-center px-8 py-16 text-paper-800">{{ loadingLabel }}</div>
      <div v-else-if="!session || !runtime || !currentNode" class="flex flex-1 items-center justify-center px-8 py-16 text-paper-800">还没有开始互动故事，请先回到书架创建一个开局。</div>
      <div v-else class="flex min-h-0 flex-1 flex-col">
        <div class="hide-scrollbar flex-1 overflow-y-auto px-6 pb-12 pt-28 sm:px-8" @click="revealNextParagraph">
          <div class="space-y-8">
            <div
              v-for="item in renderedHistory"
              :key="item.id"
              class="chunk-in"
            >
              <div v-if="item.type === 'story'" class="space-y-4">
                <p class="font-serif text-[1.05rem] text-paper-700/55">{{ item.label }}</p>
                <p class="story-prose no-indent">{{ item.text }}</p>
              </div>

              <div v-else-if="item.type === 'note'" class="rounded-[24px] bg-white/70 px-5 py-4 text-paper-700 shadow-[0_2px_12px_rgba(0,0,0,0.04)]">
                <p class="text-sm uppercase tracking-[0.24em] text-accent-500/70">{{ item.label }}</p>
                <p class="mt-2 leading-7">{{ item.text }}</p>
              </div>

              <div v-else class="ml-auto max-w-[84%] rounded-[24px] rounded-tr-sm bg-paper-200 px-5 py-4 text-right text-paper-900 shadow-[0_2px_12px_rgba(0,0,0,0.04)]">
                <span class="mr-2 font-semibold text-accent-500">我：</span>
                <span class="leading-8">{{ item.text }}</span>
              </div>
            </div>

            <div class="space-y-6">
              <div
                v-if="showOpeningLead"
                class="rounded-[28px] border border-paper-200 bg-paper-100/70 px-5 py-5"
              >
                <p class="mb-2 text-xs uppercase tracking-[0.24em] text-paper-700/55">前情提要</p>
                <p class="story-prose no-indent">{{ openingLead }}</p>
              </div>

              <p class="text-center font-serif text-[2.1rem] leading-[1.8] text-paper-900">
                {{ currentNode.stageLabel }}
              </p>

              <div
                v-if="entryTip"
                class="rounded-[24px] border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-700"
              >
                {{ entryTip }}
              </div>

              <div
                v-if="isEndingNode"
                class="rounded-[22px] border border-accent-300/60 bg-accent-50/70 px-4 py-3 text-center text-sm font-semibold tracking-[0.08em] text-accent-700"
              >
                结局
              </div>

              <div
                v-if="!currentNodeLoaded"
                class="rounded-[24px] bg-white/70 px-5 py-4 text-center text-paper-700 shadow-[0_2px_12px_rgba(0,0,0,0.04)]"
              >
                后续剧情正在后台补全，请稍等片刻。
              </div>

              <p
                v-for="(paragraph, index) in visibleParagraphs"
                :key="`${currentNode.id}-${index}`"
                class="story-prose chunk-in"
              >
                {{ paragraph }}
              </p>

              <div v-if="currentNode.directorNote" class="rounded-[24px] bg-white/70 px-5 py-4 text-paper-700 shadow-[0_2px_12px_rgba(0,0,0,0.04)]">
                <p class="text-sm uppercase tracking-[0.24em] text-accent-500/70">局势提示</p>
                <p class="mt-2 leading-7">{{ currentNode.directorNote }}</p>
              </div>

              <div v-if="isSessionComplete && endingAnalysis" class="chunk-in space-y-4 rounded-[30px] border border-paper-200 bg-white/82 px-5 py-5 shadow-[0_2px_12px_rgba(0,0,0,0.04)]">
                <p class="text-center font-serif text-[1.45rem] text-paper-900">尾声签语</p>
                <div class="rounded-[22px] bg-paper-100/80 px-4 py-4">
                  <p class="font-serif text-[1.05rem] font-semibold text-paper-900">{{ endingAnalysis.title }}</p>
                  <div v-if="endingAnalysis.personaTags?.length" class="mt-3 flex flex-wrap gap-2">
                    <span
                      v-for="tag in endingAnalysis.personaTags"
                      :key="tag"
                      class="rounded-full bg-white px-3 py-1.5 text-xs font-semibold text-paper-800"
                    >
                      {{ tag }}
                    </span>
                  </div>
                  <p class="mt-3 text-sm leading-7 text-paper-700/80">{{ endingAnalysis.romance }}</p>
                  <p class="mt-2 text-sm leading-7 text-paper-700/70">{{ endingAnalysis.life }}</p>
                </div>

                <div class="space-y-2">
                  <p class="text-sm leading-6 text-paper-700/75">{{ endingAnalysis.nextUniverseHook }}</p>
                  <p class="text-xs uppercase tracking-[0.24em] text-paper-700/55">推荐下一个宇宙</p>
                  <button
                    v-for="item in recommendedUniverses"
                    :key="item.title"
                    class="active-press w-full rounded-[22px] border border-paper-200 bg-paper-50 px-4 py-4 text-left"
                    :disabled="loading"
                    @click.stop="launchRecommendedUniverse(item)"
                  >
                    <p class="font-serif text-[1.02rem] text-paper-900">{{ item.title }}</p>
                    <p class="mt-1 line-clamp-2 text-sm leading-6 text-paper-700/70">{{ item.summary }}</p>
                  </button>
                </div>
              </div>

              <button
                v-else-if="canRequestEndingAnalysis"
                class="active-press chunk-in w-full rounded-[30px] border border-paper-200 bg-white/82 px-5 py-5 text-left shadow-[0_2px_12px_rgba(0,0,0,0.04)]"
                @click.stop="ensureEndingAnalysis"
              >
                <p class="text-center font-serif text-[1.35rem] text-paper-900">
                  {{ analyzingEnding ? "正在生成尾声签语" : "生成尾声签语" }}
                </p>
              </button>

              <p
                v-if="currentNodeLoaded && !isRevealComplete && !isSessionComplete"
                class="rounded-[26px] bg-white/70 px-5 py-4 text-center text-paper-700/70 shadow-[0_2px_12px_rgba(0,0,0,0.04)]"
              >
                轻触页面，继续展开这一回合；正文完全展开后才会出现选项
              </p>

              <p
                v-else-if="currentNodeLoaded && !isRevealComplete && isSessionComplete"
                class="rounded-[26px] bg-white/70 px-5 py-4 text-center text-paper-700/70 shadow-[0_2px_12px_rgba(0,0,0,0.04)]"
              >
                轻触页面，继续展开结局内容
              </p>

              <p v-if="saveMessage" class="rounded-[24px] bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
                {{ saveMessage }}
              </p>
              <p v-if="error" class="rounded-[24px] bg-red-50 px-4 py-3 text-sm text-red-700">{{ error }}</p>
            </div>
          </div>
        </div>

        <footer
          v-if="currentNodeLoaded && isRevealComplete && !isSessionComplete"
          class="glass-panel slide-up border-t border-paper-200/70 px-5 pb-5 pt-4 safe-pb sm:px-6"
        >
          <div class="mx-auto max-w-md space-y-3">
            <button
              v-for="choice in choiceList"
              :key="choice.id"
              class="active-press w-full rounded-[24px] border px-5 py-5 text-left shadow-[0_2px_12px_rgba(0,0,0,0.04)]"
              :class="choice.isRecommended ? 'border-accent-500/55 bg-white text-paper-900' : 'border-paper-200 bg-white text-paper-900'"
              :disabled="choosingOption"
              @click="chooseOption(choice)"
            >
              <div class="flex items-start gap-3">
                <span class="mt-2 h-1.5 w-1.5 rounded-full bg-accent-400"></span>
                <div class="space-y-1">
                  <p class="text-[1.08rem] leading-8">{{ choice.text }}</p>
                  <p class="text-sm text-paper-700/55">
                    {{ choice.tone || choice.style }}
                    <span v-if="choice.isRecommended"> · 推荐</span>
                    <span v-if="choice.isAiChoice"> · AI 会选</span>
                  </p>
                </div>
              </div>
            </button>
          </div>
        </footer>
      </div>
    </section>
  </main>
</template>
