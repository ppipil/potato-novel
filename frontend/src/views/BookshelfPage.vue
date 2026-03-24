<script setup>
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { getOpeningSummary, getOpeningTitle, presetOpenings } from "../data/openings";
import { generateStory, getCurrentUser, logout } from "../lib/api";

const router = useRouter();
const user = ref(null);
const openingMode = ref("preset");
const selectedOpening = ref(presetOpenings[0] || "");
const customOpening = ref("");
const selectedRole = ref("NPC");

const roles = ["男主", "女主", "NPC", "反派", "旁白代理人"];
const generating = ref(false);
const error = ref("");

onMounted(async () => {
  const data = await getCurrentUser();
  if (!data.authenticated) {
    router.replace("/");
    return;
  }
  user.value = data.user;
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
      error.value = "请先选择一个推荐开头，或输入自定义开头。";
      generating.value = false;
      return;
    }
    const result = await generateStory({
      opening: openingToUse,
      role: selectedRole.value
    });
    sessionStorage.setItem("potato-novel-story", JSON.stringify(result));
    router.push("/story/result");
  } catch (err) {
    error.value = err instanceof Error ? err.message : "生成失败";
  } finally {
    generating.value = false;
  }
}
</script>

<template>
  <main class="page">
    <section class="topbar">
      <div>
        <p class="status">已连接 SecondMe</p>
        <h1>土豆小说书架</h1>
      </div>
      <div class="topbar-actions">
        <p>{{ user?.name || user?.nickname || user?.sub || "SecondMe 用户" }}</p>
        <button class="ghost" @click="router.push('/stories')">查看已保存小说</button>
        <button class="ghost" @click="handleLogout">退出</button>
      </div>
    </section>

    <section class="grid">
      <article class="card">
        <h2>选择小说开头</h2>
        <div class="mode-switch">
          <button
            class="choice compact"
            :class="{ active: openingMode === 'preset' }"
            @click="openingMode = 'preset'"
          >
            推荐开头
          </button>
          <button
            class="choice compact"
            :class="{ active: openingMode === 'custom' }"
            @click="openingMode = 'custom'"
          >
            自定义开头
          </button>
        </div>
        <div class="stack">
          <template v-if="openingMode === 'preset'">
            <button
              v-for="opening in presetOpenings"
              :key="opening"
              class="choice"
              :class="{ active: opening === selectedOpening }"
              @click="selectedOpening = opening"
            >
              <strong class="opening-title">{{ getOpeningTitle(opening) }}</strong>
              <span class="opening-summary">{{ getOpeningSummary(opening) }}</span>
            </button>
          </template>
          <template v-else>
            <textarea
              v-model="customOpening"
              class="story-input"
              rows="7"
              placeholder="输入你自己的小说开头，比如人物登场、世界观设定、冲突起点，后续会基于这个开头继续共创。"
            />
            <p class="hint">
              现在支持推荐开头和自定义开头并存。后续也可以把推荐开头改成从外部小说网站的热门内容动态更新。
            </p>
          </template>
        </div>
      </article>

      <article class="card">
        <h2>选择角色身份</h2>
        <div class="stack roles">
          <button
            v-for="role in roles"
            :key="role"
            class="choice"
            :class="{ active: role === selectedRole }"
            @click="selectedRole = role"
          >
            {{ role }}
          </button>
        </div>
      </article>
    </section>

    <section class="card story-preview">
      <p class="status">Demo 流程预览</p>
      <p>小说开头：{{ openingMode === "custom" ? (customOpening || "尚未填写自定义开头") : selectedOpening }}</p>
      <p>角色身份：{{ selectedRole }}</p>
      <p>
        下一步你可以把这里接到真正的剧情生成 API，让 SecondMe 登录用户进入共创流程，并产出几千字以内的短篇小说结果页。
      </p>
      <button class="primary" :disabled="generating" @click="handleGenerate">
        {{ generating ? "正在调用 SecondMe 生成..." : "开始共创" }}
      </button>
      <p v-if="error" class="error">{{ error }}</p>
    </section>
  </main>
</template>
