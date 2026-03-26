<script setup>
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { getOpeningSummary, getOpeningTitle, presetOpenings } from "../data/openings";
import { getCurrentUser, listStories, logout, startStorySession } from "../lib/api";

const router = useRouter();
const user = ref(null);
const openingMode = ref("custom");
const selectedOpening = ref(presetOpenings[0] || "");
const customOpening = ref("");
const selectedRole = ref("NPC");
const stories = ref([]);
const generating = ref(false);
const error = ref("");

const roles = ["男主", "女主", "NPC", "反派", "旁白代理人"];
const templateTags = ["悬疑惊悚", "都市言情", "无限流", "命运反转"];
const coverTints = [
  "bg-slate-800/22",
  "bg-rose-300/30",
  "bg-amber-700/18",
  "bg-emerald-700/16"
];

const shelfBooks = computed(() => {
  if (stories.value.length) {
    return stories.value.slice(0, 6).map((item, index) => ({
      id: item.id,
      title: getOpeningTitle(item.meta?.opening || "未命名作品"),
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

onMounted(async () => {
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

async function handleLogout() {
  await logout();
  router.replace("/");
}

async function handleGenerate() {
  generating.value = true;
  error.value = "";
  try {
    const openingToUse = openingMode.value === "custom" ? customOpening.value.trim() : selectedOpening.value;
    if (!openingToUse) {
      error.value = "先写一个故事开局，或者选择一个模板。";
      generating.value = false;
      return;
    }
    const result = await startStorySession({
      opening: openingToUse,
      role: selectedRole.value
    });
    sessionStorage.setItem("potato-novel-story-session", JSON.stringify(result.session));
    router.push("/story/result");
  } catch (err) {
    error.value = err instanceof Error ? err.message : "进入故事失败";
  } finally {
    generating.value = false;
  }
}

function selectTemplate(opening) {
  selectedOpening.value = opening;
  openingMode.value = "preset";
}
</script>

<template>
  <main class="paper-shell">
    <section class="paper-page">
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
              <div class="absolute inset-x-0 bottom-0 z-10 px-4 pb-5 text-xl font-serif text-white">
                {{ book.title }}
              </div>
            </button>
          </div>
        </div>

        <div class="space-y-4">
          <h2 class="font-serif text-[2.3rem] font-semibold text-paper-900">开启新篇章</h2>
          <p class="text-[1.08rem] text-paper-700/55">选择一个开局，或者自己写一个</p>

          <article class="paper-card relative overflow-hidden px-6 py-7">
            <div class="absolute right-6 top-6 h-16 w-16 rounded-full bg-accent-400/20 blur-2xl"></div>
            <div class="space-y-6">
              <div class="flex items-center gap-3 text-accent-500">
                <span class="text-3xl">✎</span>
                <h3 class="text-[1.85rem] font-semibold">自由创作</h3>
              </div>

              <textarea
                v-model="customOpening"
                class="shadow-inner-soft min-h-40 w-full resize-none rounded-[28px] border border-paper-100 bg-paper-50 px-6 py-6 font-serif text-[1.05rem] leading-9 text-paper-900 placeholder:text-paper-700/28"
                placeholder="描述你的故事开局和你的身份，例如：我是一个刚入职的实习生，第一天上班就撞破了霸总的秘密..."
                @focus="openingMode = 'custom'"
              />

              <div class="space-y-4">
                <div class="flex flex-wrap gap-2">
                  <button
                    v-for="role in roles"
                    :key="role"
                    class="active-press rounded-full border px-4 py-2 text-sm"
                    :class="role === selectedRole ? 'border-accent-500 bg-accent-500 text-white' : 'border-paper-200 bg-paper-50 text-paper-800'"
                    @click="selectedRole = role"
                  >
                    {{ role }}
                  </button>
                </div>

                <div class="flex justify-end">
                  <button
                    class="active-press rounded-[18px] bg-stone-400 px-6 py-4 text-2xl font-semibold text-white disabled:opacity-60"
                    :disabled="generating"
                    @click="handleGenerate"
                  >
                    {{ generating ? "生成中..." : "进入故事" }}
                  </button>
                </div>
              </div>
            </div>
          </article>

          <div class="space-y-5 pt-2">
            <button
              v-for="(opening, index) in presetOpenings"
              :key="opening"
              class="paper-card active-press grid grid-cols-[1fr_10rem] overflow-hidden text-left"
              @click="selectTemplate(opening)"
            >
              <div class="space-y-4 px-6 py-6">
                <span class="inline-flex rounded-xl bg-paper-100 px-4 py-2 text-sm font-semibold text-paper-800">
                  {{ templateTags[index % templateTags.length] }}
                </span>
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
              </div>
            </button>
          </div>

          <p v-if="selectedOpening && openingMode === 'preset'" class="rounded-2xl bg-paper-100/80 px-4 py-3 text-sm text-paper-800">
            当前模板：{{ getOpeningTitle(selectedOpening) }}
          </p>
          <p v-if="error" class="rounded-2xl bg-red-50 px-4 py-3 text-sm text-red-700">{{ error }}</p>
        </div>
      </section>
    </section>
  </main>
</template>
