<script setup>
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import {
  continueStorySession,
  finalizeStorySession,
  getStorySession,
  saveStory
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

const canSave = computed(() => Boolean(session.value?.id) && (session.value?.turnCount || 0) >= 2);
const transcript = computed(() => session.value?.transcript || []);
const choiceList = computed(() => session.value?.choices || []);
const paragraphs = computed(() => session.value?.paragraphs || []);
const visibleParagraphs = computed(() => paragraphs.value.slice(0, currentIndex.value + 1));
const isRevealComplete = computed(() => {
  return paragraphs.value.length === 0 || currentIndex.value >= paragraphs.value.length - 1;
});
const pageTitle = computed(() => {
  const opening = session.value?.meta?.opening || "";
  return opening.split("\n").find(Boolean)?.trim() || "互动故事";
});

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
    saveMessage.value = `已保存，共记录 ${result.story.meta.turnCount || finalized.meta.turnCount || session.value.turnCount} 个回合。`;
  } catch (err) {
    error.value = err instanceof Error ? err.message : "保存失败";
  } finally {
    saving.value = false;
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
          v-if="isRevealComplete"
          class="glass-panel slide-up absolute bottom-0 inset-x-0 z-20 border-t border-paper-200/70 px-5 pb-5 pt-4 safe-pb sm:px-6"
        >
          <div class="mx-auto max-w-md space-y-3">
            <button
              v-for="choice in choiceList"
              :key="choice.id"
              class="active-press w-full rounded-[24px] border px-5 py-5 text-left shadow-[0_2px_12px_rgba(0,0,0,0.04)]"
              :class="choice.isRecommended ? 'border-accent-500/55 bg-white text-paper-900' : 'border-paper-200 bg-white text-paper-900'"
              :disabled="submitting || session.status === 'complete'"
              @click="submitAction(choice.id)"
            >
              <div class="flex items-start gap-3">
                <span class="mt-2 h-1.5 w-1.5 rounded-full bg-accent-400"></span>
                <div class="space-y-1">
                  <p class="text-[1.08rem] leading-8">{{ choice.text }}</p>
                  <p class="text-sm text-paper-700/55">
                    {{ choice.style }}
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
                :disabled="submitting || session.status === 'complete'"
                placeholder="或者自定义你的行动..."
                @keydown.enter.prevent="handleCustomSubmit"
              />
              <button
                class="active-press shrink-0 rounded-[22px] px-7 py-5 text-xl font-semibold text-white"
                :class="customAction.trim() ? 'bg-accent-500' : 'bg-paper-900'"
                :disabled="submitting || session.status === 'complete'"
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
