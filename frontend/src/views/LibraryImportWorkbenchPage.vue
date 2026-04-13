<script setup>
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { deleteImportedLibraryStory, importLibraryStoryPackage } from "../lib/api";
import { readLibraryStoriesCache, writeLibraryStoriesCache } from "../lib/storyCache";

const router = useRouter();
const FORCE_REFRESH_LIBRARY_KEY = "potato-novel-force-refresh-library";
const importing = ref(false);
const deleting = ref(false);
const loadingRows = ref(false);
const libraryRows = ref([]);
const error = ref("");
const success = ref("");
const deleteReceipt = ref(null);

const form = ref({
  storyId: "",
  title: "",
  opening: "",
  summary: "",
  sortOrder: "",
  packageText: `{
  "title": "大晋权谋录：红裙下的修罗场",
  "rootNodeId": "N1",
  "nodes": []
}`
});

function parseSortOrder(value) {
  const trimmed = String(value || "").trim();
  if (!trimmed) {
    return undefined;
  }
  const num = Number(trimmed);
  return Number.isFinite(num) ? Math.floor(num) : undefined;
}

async function withRequestTimeout(requestFactory, timeoutMs = 12000, timeoutMessage = "请求超时，请稍后重试") {
  const controller = new AbortController();
  let timedOut = false;
  const timer = window.setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeoutMs);
  try {
    return await requestFactory({ signal: controller.signal });
  } catch (err) {
    if (timedOut && err?.name === "AbortError") {
      throw new Error(timeoutMessage);
    }
    throw err;
  } finally {
    window.clearTimeout(timer);
  }
}

async function refreshImportedRows() {
  loadingRows.value = true;
  const cache = readLibraryStoriesCache();
  const rows = Array.isArray(cache?.rows) ? cache.rows : [];
  libraryRows.value = rows;
  loadingRows.value = false;
}

function upsertLibraryStoryCacheRow(row) {
  const cache = readLibraryStoriesCache();
  const rows = Array.isArray(cache?.rows) ? cache.rows : [];
  const nextRows = [row, ...rows.filter((item) => item?.id !== row.id)];
  writeLibraryStoriesCache(nextRows);
}

function removeLibraryStoryCacheRow(storyId) {
  const cache = readLibraryStoriesCache();
  const rows = Array.isArray(cache?.rows) ? cache.rows : [];
  writeLibraryStoriesCache(rows.filter((item) => item?.id !== storyId));
}

async function handleImport() {
  importing.value = true;
  error.value = "";
  success.value = "";
  try {
    const parsedPackage = JSON.parse(form.value.packageText || "{}");
    const payload = {
      storyId: form.value.storyId.trim() || undefined,
      title: form.value.title.trim() || undefined,
      opening: form.value.opening.trim() || undefined,
      summary: form.value.summary.trim() || undefined,
      sortOrder: parseSortOrder(form.value.sortOrder),
      package: parsedPackage
    };
    const result = await importLibraryStoryPackage(payload);
    success.value = `导入成功：${result.title}（ID: ${result.storyId}）`;
    sessionStorage.setItem(FORCE_REFRESH_LIBRARY_KEY, "1");
    upsertLibraryStoryCacheRow({
      id: result.storyId,
      title: result.title,
      summary: result.summary,
      opening: result.opening,
      seedReady: true,
      seedGenerating: false,
      seedUpdatedAt: Math.floor(Date.now() / 1000),
      seedSessionId: result.seedSessionId || `seed-${result.storyId}`
    });
    await refreshImportedRows();
  } catch (err) {
    error.value = err instanceof Error ? err.message : "导入失败";
  } finally {
    importing.value = false;
  }
}

async function deleteByStoryId(storyId) {
  if (!storyId) {
    error.value = "请先填要删除的故事 ID。";
    return;
  }
  deleting.value = true;
  error.value = "";
  success.value = "";
  deleteReceipt.value = null;
  const startedAt = performance.now();
  try {
    const result = await withRequestTimeout(
      (requestOptions) => deleteImportedLibraryStory(storyId, requestOptions),
      12000,
      "删除请求超时（12s），请检查后端是否卡住。"
    );
    if (!result?.storyDeleted) {
      throw new Error("服务端未删除书市主记录，请重试。");
    }
    const elapsedMs = Math.round(performance.now() - startedAt);
    deleteReceipt.value = {
      mode: "single",
      storyId: result.storyId,
      storyDeleted: Boolean(result.storyDeleted),
      seedDeleted: Boolean(result.seedDeleted),
      elapsedMs,
      at: new Date().toLocaleString()
    };
    success.value = `已删除：${result.storyId}（${elapsedMs}ms）`;
    sessionStorage.setItem(FORCE_REFRESH_LIBRARY_KEY, "1");
    removeLibraryStoryCacheRow(result.storyId);
    await refreshImportedRows();
  } catch (err) {
    error.value = err instanceof Error ? err.message : "删除失败";
  } finally {
    deleting.value = false;
  }
}

async function handleDeleteImported() {
  const storyId = String(form.value.storyId || "").trim();
  await deleteByStoryId(storyId);
}

async function deleteAllByTitle(title) {
  const normalizedTitle = String(title || "").trim();
  if (!normalizedTitle) {
    return;
  }
  const targets = libraryRows.value.filter((item) =>
    String(item?.title || "").trim() === normalizedTitle && String(item?.id || "").startsWith("library-import-")
  );
  if (!targets.length) {
    return;
  }
  deleting.value = true;
  error.value = "";
  success.value = "";
  deleteReceipt.value = null;
  const startedAt = performance.now();
  try {
    const settled = await Promise.allSettled(
      targets.map((item) =>
        withRequestTimeout(
          (requestOptions) => deleteImportedLibraryStory(item.id, requestOptions),
          12000,
          `删除超时：${item.id}`
        )
      )
    );
    const failed = [];
    let deletedCount = 0;
    let seedDeletedCount = 0;
    for (const item of settled) {
      if (item.status !== "fulfilled" || !item.value?.storyDeleted) {
        failed.push(item.status === "fulfilled" ? item.value?.storyId || "unknown" : "request_failed");
        continue;
      }
      deletedCount += 1;
      if (item.value.seedDeleted) {
        seedDeletedCount += 1;
      }
      removeLibraryStoryCacheRow(item.value.storyId);
    }
    const elapsedMs = Math.round(performance.now() - startedAt);
    deleteReceipt.value = {
      mode: "batch",
      title: normalizedTitle,
      requested: targets.length,
      deletedCount,
      seedDeletedCount,
      failedCount: failed.length,
      elapsedMs,
      at: new Date().toLocaleString()
    };
    if (failed.length) {
      throw new Error(`批量删除部分失败：成功 ${deletedCount}/${targets.length}`);
    }
    success.value = `已删除同名故事 ${deletedCount} 条（${elapsedMs}ms）：${normalizedTitle}`;
    sessionStorage.setItem(FORCE_REFRESH_LIBRARY_KEY, "1");
    await refreshImportedRows();
  } catch (err) {
    error.value = err instanceof Error ? err.message : "批量删除失败";
  } finally {
    deleting.value = false;
  }
}

function backToMarket() {
  sessionStorage.setItem(FORCE_REFRESH_LIBRARY_KEY, "1");
  router.push("/bookshelf?tab=public");
}

onMounted(() => {
  void refreshImportedRows();
});
</script>

<template>
  <main class="paper-shell">
    <section class="paper-page min-h-screen px-6 py-6 sm:px-8">
      <div class="mx-auto max-w-[36rem] space-y-5">
        <header class="space-y-2">
          <p class="text-xs uppercase tracking-[0.18em] text-paper-700/55">Library Workbench</p>
          <h1 class="font-serif text-3xl font-semibold text-paper-900">书市故事包导入台</h1>
          <p class="text-sm text-paper-700/70">把完整 story package JSON 粘贴进来，一键写入数据库并展示到逛书市。</p>
        </header>

        <div class="space-y-3 rounded-2xl border border-paper-200 bg-white/88 p-4">
          <input v-model="form.storyId" class="w-full rounded-xl border border-paper-200 bg-paper-50 px-3 py-2 text-sm" placeholder="故事 ID（可空，自动生成）" />
          <input v-model="form.title" class="w-full rounded-xl border border-paper-200 bg-paper-50 px-3 py-2 text-sm" placeholder="书市标题（可空，默认取 package.title）" />
          <input v-model="form.opening" class="w-full rounded-xl border border-paper-200 bg-paper-50 px-3 py-2 text-sm" placeholder="opening（可空，默认用标题）" />
          <input v-model="form.summary" class="w-full rounded-xl border border-paper-200 bg-paper-50 px-3 py-2 text-sm" placeholder="书市摘要（可空）" />
          <input v-model="form.sortOrder" class="w-full rounded-xl border border-paper-200 bg-paper-50 px-3 py-2 text-sm" placeholder="排序值（可空）" />
          <textarea
            v-model="form.packageText"
            class="min-h-[19rem] w-full resize-y rounded-2xl border border-paper-200 bg-paper-50 px-4 py-3 font-mono text-xs leading-6 text-paper-900"
            placeholder="粘贴完整 story package JSON"
          />
        </div>

        <div class="flex gap-3">
          <button class="active-press rounded-xl bg-paper-900 px-4 py-2 text-sm font-semibold text-paper-50 disabled:opacity-55" :disabled="importing" @click="handleImport">
            {{ importing ? "导入中..." : "导入到书市" }}
          </button>
          <button class="active-press rounded-xl border border-red-300 bg-white px-4 py-2 text-sm font-semibold text-red-700 disabled:opacity-55" :disabled="deleting" @click="handleDeleteImported">
            {{ deleting ? "删除中..." : "删除导入故事" }}
          </button>
          <button class="active-press rounded-xl border border-paper-300 bg-white px-4 py-2 text-sm font-semibold text-paper-800" @click="backToMarket">
            返回逛书市
          </button>
        </div>

        <p v-if="success" class="rounded-xl bg-emerald-50 px-3 py-2 text-sm text-emerald-700">{{ success }}</p>
        <p v-if="error" class="rounded-xl bg-red-50 px-3 py-2 text-sm text-red-700">{{ error }}</p>
        <section v-if="deleteReceipt" class="space-y-1 rounded-xl border border-paper-200 bg-paper-50 px-3 py-2">
          <p class="text-xs font-semibold tracking-[0.08em] text-paper-700/70">删除回执</p>
          <pre class="whitespace-pre-wrap break-all text-[0.7rem] leading-5 text-paper-800">{{ JSON.stringify(deleteReceipt, null, 2) }}</pre>
        </section>

        <section class="space-y-2 rounded-2xl border border-paper-200 bg-white/88 p-4">
          <div class="flex items-center justify-between">
            <h2 class="font-serif text-lg font-semibold text-paper-900">书市列表（含 ID）</h2>
            <button class="active-press rounded-lg border border-paper-300 bg-white px-3 py-1 text-xs font-semibold text-paper-700" @click="refreshImportedRows">
              刷新
            </button>
          </div>
          <p v-if="loadingRows" class="text-xs text-paper-700/65">正在加载...</p>
          <div v-else-if="libraryRows.length" class="space-y-2">
            <div v-for="row in libraryRows" :key="row.id" class="rounded-xl border border-paper-200 bg-paper-50 px-3 py-2">
              <p class="text-sm font-semibold text-paper-900">{{ row.title || "未命名" }}</p>
              <p class="mt-1 break-all font-mono text-xs text-paper-700/75">{{ row.id }}</p>
              <p class="mt-1 text-[0.68rem] text-paper-700/60">
                {{ String(row.id || "").startsWith("library-import-") ? "导入条目" : "系统条目（只读）" }}
              </p>
              <div v-if="String(row.id || '').startsWith('library-import-')" class="mt-2 flex gap-2">
                <button class="active-press rounded-lg border border-red-300 bg-white px-2 py-1 text-xs font-semibold text-red-700" :disabled="deleting" @click="deleteByStoryId(row.id)">
                  删除这条
                </button>
                <button class="active-press rounded-lg border border-rose-300 bg-white px-2 py-1 text-xs font-semibold text-rose-700" :disabled="deleting" @click="deleteAllByTitle(row.title)">
                  删除同名全部
                </button>
              </div>
            </div>
          </div>
          <p v-else class="text-xs text-paper-700/65">暂无书市缓存数据</p>
        </section>
      </div>
    </section>
  </main>
</template>
