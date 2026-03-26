<script setup>
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import LoadingOverlay from "../components/LoadingOverlay.vue";
import { presetOpenings, getOpeningTitle, getOpeningSummary } from "../data/openings";
import {
  analyzeStoryEnding,
  finalizeStorySession,
  getStorySession,
  hydrateStorySession,
  saveStory,
  startStorySession
} from "../lib/api";

const router = useRouter();
const session = ref(null);
const runtime = ref(null);
const error = ref("");
const saveMessage = ref("");
const loading = ref(true);
const saving = ref(false);
const hydratingPackage = ref(false);
const finalizedPayload = ref(null);
const currentIndex = ref(-1);
const endingAnalysis = ref(null);
const analyzingEnding = ref(false);
const hydratingChoice = ref(false);
const pendingChoiceId = ref("");

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
const currentParagraphs = computed(() => {
  const paragraphs = currentNode.value?.paragraphs;
  if (Array.isArray(paragraphs) && paragraphs.length > 0) {
    return paragraphs;
  }

  const scene = currentNode.value?.scene || "";
  return scene
    .split(/\n\s*\n+/)
    .map((item) => item.trim())
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
const canSave = computed(() => Boolean(session.value?.id) && isSessionComplete.value && !saving.value);
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
  if (saving.value) {
    return "正在整理书页";
  }
  if (analyzingEnding.value) {
    return "正在解读你这颗土豆";
  }
  if (hydratingChoice.value) {
    return "正在加载下一回合";
  }
  if (hydratingPackage.value) {
    return "正在补全后续剧情";
  }
  return "正在处理";
});
const overlayDescription = computed(() => {
  if (saving.value) {
    return "土豆正在把这局互动小说装订成可回看的完整记录。";
  }
  if (analyzingEnding.value) {
    return "SecondMe 正在根据你走出的分支生成一份结局签语。";
  }
  if (hydratingChoice.value) {
    return "你点中的分支还没补完，正在把下一回合接上。";
  }
  if (hydratingPackage.value) {
    return "先让你进入第一幕，后续节点正在后台补齐。";
  }
  return "请稍候。";
});
const recommendedUniverses = computed(() => {
  const currentTitle = pageTitle.value;
  const persona = currentState.value?.persona || {};
  const sincerity = persona["真诚"] || 0;
  const scheming = persona["心机"] || 0;

  const preferred = presetOpenings
    .filter((opening) => getOpeningTitle(opening) !== currentTitle)
    .sort((left, right) => {
      const leftScore = (scheming > sincerity && /怪谈|绞肉机|规则/.test(left) ? 1 : 0) + (sincerity >= scheming && /修养|攻略|婚/.test(left) ? 1 : 0);
      const rightScore = (scheming > sincerity && /怪谈|绞肉机|规则/.test(right) ? 1 : 0) + (sincerity >= scheming && /修养|攻略|婚/.test(right) ? 1 : 0);
      return rightScore - leftScore;
    });

  return preferred.slice(0, 2).map((opening) => ({
    opening,
    title: getOpeningTitle(opening),
    summary: getOpeningSummary(opening)
  }));
});

onMounted(async () => {
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
    const result = await getStorySession(storedSession.id);
    session.value = result.session;
    runtime.value = restoreRuntime(result.session, storedSession.runtime);
    persistLocalSession();
    void hydrateInBackground();
  } catch (err) {
    error.value = err instanceof Error ? err.message : "加载互动故事失败";
  } finally {
    loading.value = false;
  }
});

function buildNodeEntries(node) {
  if (!node) {
    return [];
  }
  return [
    { turn: node.turn, label: node.stageLabel, text: node.scene },
    ...(node.directorNote ? [{ turn: node.turn, label: "局势提示", text: node.directorNote }] : [])
  ];
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
  persistLocalSession();
}

async function hydrateInBackground() {
  if (!session.value?.id || packageStatus.value === "ready" || hydratingPackage.value) {
    return;
  }
  hydratingPackage.value = true;
  try {
    const result = await hydrateStorySession(session.value.id);
    mergeSession(result.session);
  } catch (err) {
    error.value = err instanceof Error ? err.message : "后台补全剧情失败";
  } finally {
    hydratingPackage.value = false;
  }
}

function revealNextParagraph() {
  if (currentParagraphs.value.length === 0 || isRevealComplete.value) {
    return;
  }
  currentIndex.value += 1;
}

function applyChoiceEffects(previousState, choice, nextNode, nextPathLength) {
  const nextState = {
    stage: nextNode.kind === "ending" ? "ending" : nextNode.turn <= 1 ? "opening" : nextNode.turn >= 4 ? "climax" : "conflict",
    flags: [...(previousState.flags || [])],
    relationship: { ...(previousState.relationship || {}) },
    persona: { ...(previousState.persona || {}) },
    turn: nextNode.turn || nextPathLength,
    endingHint: ""
  };

  for (const [key, value] of Object.entries(choice.effects?.persona || {})) {
    nextState.persona[key] = (nextState.persona[key] || 0) + Number(value || 0);
  }
  for (const [key, value] of Object.entries(choice.effects?.relationship || {})) {
    nextState.relationship[key] = (nextState.relationship[key] || 0) + Number(value || 0);
  }

  if (choice.style === "trust" || choice.style === "support" || choice.style === "soft") {
    if (!nextState.flags.includes("soft_route")) {
      nextState.flags.push("soft_route");
    }
  }
  if (choice.style === "tease") {
    if (!nextState.flags.includes("spark_route")) {
      nextState.flags.push("spark_route");
    }
  }
  if (["strategy", "manipulation", "observation"].includes(choice.style)) {
    if (!nextState.flags.includes("hidden_route")) {
      nextState.flags.push("hidden_route");
    }
  }
  if (nextNode.kind === "ending") {
    nextState.endingHint = (nextState.relationship["好感"] || 0) >= 2
      ? "你把这个宇宙推向了高好感收束。"
      : "这个宇宙留下了更克制也更耐回味的尾音。";
  }

  return nextState;
}

async function chooseOption(choice) {
  if (!choice || !currentNode.value || isSessionComplete.value) {
    return;
  }

  let nextNode = nodeMap.value[choice.nextNodeId];
  if (nextNode && nextNode.loaded === false) {
    hydratingChoice.value = true;
    pendingChoiceId.value = choice.id;
    try {
      const result = await hydrateStorySession(session.value.id);
      mergeSession(result.session);
      nextNode = result.session.package?.nodes?.find((item) => item.id === choice.nextNodeId) || nodeMap.value[choice.nextNodeId];
    } catch (err) {
      error.value = err instanceof Error ? err.message : "后续剧情加载失败";
    } finally {
      hydratingChoice.value = false;
      pendingChoiceId.value = "";
    }
  }
  if (!nextNode) {
    error.value = "故事包里的下一个节点丢失了。";
    return;
  }

  const nextPath = [
    ...(runtime.value?.path || []),
    {
      fromNodeId: currentNode.value.id,
      choiceId: choice.id,
      choiceText: choice.text,
      nextNodeId: nextNode.id,
      turn: currentNode.value.turn,
      effects: choice.effects || {}
    }
  ];
  const nextEntries = [
    ...(runtime.value?.entries || []),
    { turn: currentNode.value.turn, label: "玩家行动", text: choice.text },
    ...buildNodeEntries(nextNode)
  ];
  const nextState = applyChoiceEffects(
    runtime.value?.state || packageData.value?.initialState || {},
    choice,
    nextNode,
    nextPath.length + 1
  );

  runtime.value = {
    currentNodeId: nextNode.id,
    entries: nextEntries,
    path: nextPath,
    state: nextState,
    status: nextNode.kind === "ending" ? "complete" : "ongoing",
    endingNodeId: nextNode.kind === "ending" ? nextNode.id : "",
    summary: nextNode.kind === "ending" ? nextNode.summary || nextNode.scene : runtime.value?.summary || ""
  };
  currentIndex.value = -1;
  error.value = "";
  saveMessage.value = "";
  persistLocalSession();

}

async function handleSave() {
  if (!session.value?.id || !isSessionComplete.value || saving.value) {
    return;
  }

  saving.value = true;
  error.value = "";
  saveMessage.value = "";
  try {
    const finalized = finalizedPayload.value || (await finalizeStorySession({
      sessionId: session.value.id,
      completedRun: {
        currentNodeId: runtime.value.currentNodeId,
        endingNodeId: runtime.value.endingNodeId,
        summary: runtime.value.summary,
        transcript: runtime.value.entries,
        state: runtime.value.state,
        path: runtime.value.path
      }
    }));
    finalizedPayload.value = finalized;
    const result = await saveStory({
      story: finalized.story,
      meta: {
        ...finalized.meta,
        endingAnalysis: endingAnalysis.value || finalized.meta?.endingAnalysis || null
      }
    });
    session.value = {
      ...session.value,
      status: "complete",
      completedRun: {
        currentNodeId: runtime.value.currentNodeId,
        endingNodeId: runtime.value.endingNodeId,
        summary: runtime.value.summary,
        transcript: runtime.value.entries,
        state: runtime.value.state,
        path: runtime.value.path
      }
    };
    persistLocalSession();
    saveMessage.value = `已保存，共记录 ${result.story.meta.turnCount || finalized.meta.turnCount || runtime.value.path.length + 1} 个回合。`;
  } catch (err) {
    error.value = err instanceof Error ? err.message : "保存失败";
  } finally {
    saving.value = false;
  }
}

async function ensureEndingAnalysis() {
  if (!session.value?.id || !isSessionComplete.value || endingAnalysis.value || analyzingEnding.value) {
    return;
  }

  analyzingEnding.value = true;
  try {
    const completedRunPayload = {
      summary: runtime.value.summary,
      transcript: runtime.value.entries,
      state: runtime.value.state,
      opening: session.value.meta?.opening || "",
      role: session.value.meta?.role || ""
    };
    const result = session.value.completedRun
      ? await analyzeStoryEnding({
          sessionId: session.value.id
        })
      : await analyzeStoryEnding({
          meta: completedRunPayload,
          story: runtime.value.summary || currentNode.value?.scene || ""
        });
    endingAnalysis.value = result.analysis;
  } catch (err) {
    error.value = err instanceof Error ? err.message : "尾声分析生成失败";
  } finally {
    analyzingEnding.value = false;
  }
}

async function launchRecommendedUniverse(opening) {
  loading.value = true;
  error.value = "";
  saveMessage.value = "";
  try {
    const result = await startStorySession({
      opening,
      role: "主人公"
    });
    sessionStorage.setItem("potato-novel-story-session", JSON.stringify(result.session));
    router.replace("/story/result");
  } catch (err) {
    error.value = err instanceof Error ? err.message : "进入新宇宙失败";
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <main class="paper-shell">
    <section class="paper-page relative flex min-h-screen flex-col px-0 pb-0 pt-0">
      <LoadingOverlay
        :visible="saving || analyzingEnding || hydratingChoice || (hydratingPackage && !currentNodeLoaded)"
        :title="overlayTitle"
        :description="overlayDescription"
      />

      <header class="glass-panel sticky top-0 z-30 flex items-center justify-between border-b border-paper-200/70 px-6 py-5 safe-pb sm:px-8">
        <button class="active-press text-3xl text-paper-700" @click="router.push('/bookshelf')">←</button>
        <h1 class="mx-4 truncate font-serif text-[1.18rem] font-semibold text-paper-900">{{ pageTitle }}</h1>
        <button
          class="active-press rounded-full px-3 py-1.5 text-lg font-semibold text-accent-500 disabled:text-paper-700/40"
          :disabled="!canSave"
          @click="handleSave"
        >
          {{ saving ? "保存中" : isSessionComplete ? "保存书架" : "未完待续" }}
        </button>
      </header>

      <div v-if="loading" class="flex flex-1 items-center justify-center px-8 py-16 text-paper-800">正在恢复故事会话...</div>
      <div v-else-if="!session || !runtime || !currentNode" class="flex flex-1 items-center justify-center px-8 py-16 text-paper-800">还没有开始互动故事，请先回到书架创建一个开局。</div>
      <div v-else class="flex min-h-0 flex-1 flex-col">
        <div class="hide-scrollbar flex-1 overflow-y-auto px-6 pb-12 pt-8 sm:px-8" @click="revealNextParagraph">
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
                    @click="launchRecommendedUniverse(item.opening)"
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
              :disabled="hydratingChoice"
              @click="chooseOption(choice)"
            >
              <div class="flex items-start gap-3">
                <span class="mt-2 h-1.5 w-1.5 rounded-full bg-accent-400"></span>
                <div class="space-y-1">
                  <p class="text-[1.08rem] leading-8">{{ choice.text }}</p>
                  <p class="text-sm text-paper-700/55">
                    <span v-if="pendingChoiceId === choice.id">正在加载下一回合 · </span>
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
