<script setup>
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import LoadingOverlay from "../components/LoadingOverlay.vue";
import { presetOpenings, getOpeningTitle, getOpeningSummary } from "../data/openings";
import {
  analyzeStoryEnding,
  continueStorySession,
  finalizeStorySession,
  getStorySession,
  saveStory,
  startStorySession
} from "../lib/api";

const router = useRouter();
const session = ref(null);
const customAction = ref("");
const error = ref("");
const saveMessage = ref("");
const loading = ref(true);
const submitting = ref(false);
const saving = ref(false);
const finalizedPayload = ref(null);
const currentIndex = ref(0);
const endingAnalysis = ref(null);
const analyzingEnding = ref(false);

const canSave = computed(() => Boolean(session.value?.id) && (session.value?.turnCount || 0) >= 2);
const transcript = computed(() => session.value?.transcript || []);
const choiceList = computed(() => session.value?.choices || []);
const paragraphs = computed(() => session.value?.paragraphs || []);
const visibleParagraphs = computed(() => paragraphs.value.slice(0, currentIndex.value + 1));
const isRevealComplete = computed(() => {
  return paragraphs.value.length === 0 || currentIndex.value >= paragraphs.value.length - 1;
});
const isSessionComplete = computed(() => session.value?.status === "complete");
const pageTitle = computed(() => {
  const opening = session.value?.meta?.opening || "";
  return opening.split("\n").find(Boolean)?.trim() || "互动故事";
});
const overlayTitle = computed(() => {
  if (saving.value) {
    return "正在整理书页";
  }
  if (analyzingEnding.value) {
    return "正在解读你这颗土豆";
  }
  if (submitting.value) {
    return "正在生成剧情";
  }
  return "正在处理";
});
const overlayDescription = computed(() => {
  if (saving.value) {
    return "土豆正在把这段冒险装订成可回顾的故事。";
  }
  if (analyzingEnding.value) {
    return "SecondMe 正在根据你的选择生成一份更贴脸的尾声签语。";
  }
  if (submitting.value) {
    return "土豆正在思考人物动作带来的连锁反应。";
  }
  return "请稍候。";
});
const recommendedUniverses = computed(() => {
  const currentTitle = pageTitle.value;
  const persona = session.value?.state?.persona || {};
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
const personaSummary = computed(() => endingAnalysis.value);

const renderedTranscript = computed(() =>
  transcript.value.map((item, index) => ({
    id: `${item.turn}-${index}`,
    type: item.label?.includes("玩家行动") ? "action" : item.label?.includes("局势提示") ? "note" : "story",
    label: item.label,
    text: item.text || ""
  }))
);

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
    sessionStorage.setItem("potato-novel-story-session", JSON.stringify(result.session));
    if (result.session?.status === "complete") {
      await ensureEndingAnalysis(result.session);
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : "加载互动故事失败";
  } finally {
    loading.value = false;
  }
});

function persistSession(nextSession) {
  session.value = nextSession;
  currentIndex.value = 0;
  sessionStorage.setItem("potato-novel-story-session", JSON.stringify(nextSession));
}

function revealNextParagraph() {
  if (isRevealComplete.value || submitting.value) {
    return;
  }
  currentIndex.value += 1;
}

async function submitAction(action) {
  if (!session.value?.id || !action.trim() || submitting.value) {
    return;
  }

  submitting.value = true;
  error.value = "";
  saveMessage.value = "";
  try {
    const result = await continueStorySession({
      sessionId: session.value.id,
      action: action.trim()
    });
    persistSession(result.session);
    customAction.value = "";
  } catch (err) {
    error.value = err instanceof Error ? err.message : "推进剧情失败";
  } finally {
    submitting.value = false;
  }
}

async function handleSave() {
  if (!session.value?.id || saving.value) {
    return;
  }
  saving.value = true;
  error.value = "";
  saveMessage.value = "";
  try {
    const finalized = finalizedPayload.value || (await finalizeStorySession({ sessionId: session.value.id }));
    finalizedPayload.value = finalized;
    const result = await saveStory({
      story: finalized.story,
      meta: finalized.meta
    });
    persistSession({
      ...session.value,
      status: "complete"
    });
    await ensureEndingAnalysis({
      ...session.value,
      status: "complete"
    });
    saveMessage.value = `已保存，共记录 ${result.story.meta.turnCount || finalized.meta.turnCount || session.value.turnCount} 个回合。`;
  } catch (err) {
    error.value = err instanceof Error ? err.message : "保存失败";
  } finally {
    saving.value = false;
  }
}

async function ensureEndingAnalysis(sessionPayload = session.value) {
  if (!sessionPayload?.id || endingAnalysis.value || analyzingEnding.value) {
    return;
  }

  analyzingEnding.value = true;
  try {
    const result = await analyzeStoryEnding({
      sessionId: sessionPayload.id
    });
    endingAnalysis.value = result.analysis;
  } catch (err) {
    error.value = err instanceof Error ? err.message : "尾声分析生成失败";
  } finally {
    analyzingEnding.value = false;
  }
}

async function launchRecommendedUniverse(opening) {
  submitting.value = true;
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
    submitting.value = false;
  }
}

function handleCustomSubmit() {
  submitAction(customAction.value);
}

function handleFooterAction() {
  if (customAction.value.trim()) {
    handleCustomSubmit();
    return;
  }
  submitAction("我选择主动收束剧情，并推动故事进入结局。");
}
</script>

<template>
  <main class="paper-shell">
    <section class="paper-page relative flex min-h-screen flex-col px-0 pb-0 pt-0">
      <LoadingOverlay
        :visible="submitting || saving || analyzingEnding"
        :title="overlayTitle"
        :description="overlayDescription"
      />

      <header class="glass-panel sticky top-0 z-30 flex items-center justify-between border-b border-paper-200/70 px-6 py-5 safe-pb sm:px-8">
        <button class="active-press text-3xl text-paper-700" @click="router.push('/bookshelf')">←</button>
        <h1 class="mx-4 truncate font-serif text-[1.18rem] font-semibold text-paper-900">{{ pageTitle }}</h1>
        <button
          class="active-press rounded-full px-3 py-1.5 text-lg font-semibold text-accent-500 disabled:text-paper-700/40"
          :disabled="!canSave || saving"
          @click="handleSave"
        >
          {{ saving ? "保存中" : "保存书架" }}
        </button>
      </header>

      <div v-if="loading" class="flex flex-1 items-center justify-center px-8 py-16 text-paper-800">正在恢复故事会话...</div>
      <div v-else-if="!session" class="flex flex-1 items-center justify-center px-8 py-16 text-paper-800">还没有开始互动故事，请先回到书架创建一个开局。</div>
      <div v-else class="relative flex-1">
        <div class="hide-scrollbar h-[calc(100vh-6rem)] overflow-y-auto px-6 pb-64 pt-8 sm:px-8" @click="revealNextParagraph">
          <div class="space-y-8">
            <div
              v-for="item in renderedTranscript"
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
              <p class="text-center font-serif text-[2.1rem] leading-[1.8] text-paper-900">
                {{ session.stageLabel }}
              </p>

              <p
                v-for="(paragraph, index) in visibleParagraphs"
                :key="`${session.turnCount}-${index}`"
                class="story-prose chunk-in"
              >
                {{ paragraph }}
              </p>

              <div v-if="isSessionComplete && personaSummary" class="chunk-in space-y-4 rounded-[30px] border border-paper-200 bg-white/82 px-5 py-5 shadow-[0_2px_12px_rgba(0,0,0,0.04)]">
                <p class="text-center font-serif text-[1.45rem] text-paper-900">尾声签语</p>
                <div class="rounded-[22px] bg-paper-100/80 px-4 py-4">
                  <p class="font-serif text-[1.05rem] font-semibold text-paper-900">{{ personaSummary.title }}</p>
                  <p class="mt-2 text-sm leading-7 text-paper-700/80">{{ personaSummary.romance }}</p>
                  <p class="mt-2 text-sm leading-7 text-paper-700/70">{{ personaSummary.life }}</p>
                </div>

                <div class="space-y-2">
                  <p class="text-sm leading-6 text-paper-700/75">{{ personaSummary.nextUniverseHook }}</p>
                  <p class="text-xs uppercase tracking-[0.24em] text-paper-700/55">推荐下一个宇宙</p>
                  <button
                    v-for="item in recommendedUniverses"
                    :key="item.title"
                    class="active-press w-full rounded-[22px] border border-paper-200 bg-paper-50 px-4 py-4 text-left"
                    :disabled="submitting"
                    @click="launchRecommendedUniverse(item.opening)"
                  >
                    <p class="font-serif text-[1.02rem] text-paper-900">{{ item.title }}</p>
                    <p class="mt-1 line-clamp-2 text-sm leading-6 text-paper-700/70">{{ item.summary }}</p>
                  </button>
                </div>
              </div>

              <div v-if="submitting" class="flex items-center gap-3 rounded-[24px] bg-white/70 px-5 py-4 text-paper-800 shadow-[0_2px_12px_rgba(0,0,0,0.04)]">
                <div class="typing-dots"><span></span><span></span><span></span></div>
                <span>土豆正在编织下一段剧情...</span>
              </div>

              <p
                v-if="!isRevealComplete && !submitting"
                class="rounded-[26px] bg-white/70 px-5 py-4 text-center text-paper-700/70 shadow-[0_2px_12px_rgba(0,0,0,0.04)]"
              >
                轻触页面，继续展开下一段剧情
              </p>

              <p v-if="saveMessage" class="rounded-[24px] bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
                {{ saveMessage }}
              </p>
              <p v-if="error" class="rounded-[24px] bg-red-50 px-4 py-3 text-sm text-red-700">{{ error }}</p>
            </div>
          </div>
        </div>

        <footer
          v-if="isRevealComplete && !isSessionComplete"
          class="glass-panel slide-up absolute bottom-0 inset-x-0 z-20 border-t border-paper-200/70 px-5 pb-5 pt-4 safe-pb sm:px-6"
        >
          <div class="mx-auto max-w-md space-y-3">
            <button
              v-for="choice in choiceList"
              :key="choice.id"
              class="active-press w-full rounded-[24px] border px-5 py-5 text-left shadow-[0_2px_12px_rgba(0,0,0,0.04)]"
              :class="choice.isRecommended ? 'border-accent-500/55 bg-white text-paper-900' : 'border-paper-200 bg-white text-paper-900'"
              :disabled="submitting"
              @click="submitAction(choice.text)"
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

            <div class="flex items-center gap-3 pt-2">
              <input
                v-model="customAction"
                class="min-w-0 flex-1 rounded-[24px] border border-paper-200 bg-white px-5 py-5 text-[1.02rem] text-paper-900 outline-none placeholder:text-paper-700/35"
                :disabled="submitting"
                placeholder="或者自定义你的行动..."
                @keydown.enter.prevent="handleCustomSubmit"
              />
              <button
                class="active-press shrink-0 rounded-[22px] px-7 py-5 text-xl font-semibold text-white"
                :class="customAction.trim() ? 'bg-accent-500' : 'bg-paper-900'"
                :disabled="submitting"
                @click="handleFooterAction"
              >
                {{ customAction.trim() ? "➜" : "进入结局" }}
              </button>
            </div>
          </div>
        </footer>
      </div>
    </section>
  </main>
</template>
