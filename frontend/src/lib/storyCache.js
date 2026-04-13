const STORIES_CACHE_KEY = "potato-novel-stories-cache-v1";
const LIBRARY_SESSION_CACHE_KEY = "potato-novel-library-session-cache-v1";
const LIBRARY_STORIES_CACHE_KEY = "potato-novel-library-stories";
const CUSTOM_PACKAGES_CACHE_KEY = "potato-novel-custom-packages-cache-v1";

function readCacheMap() {
  try {
    const raw = localStorage.getItem(STORIES_CACHE_KEY);
    if (!raw) {
      return {};
    }
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    return {};
  }
}

function writeCacheMap(cacheMap) {
  localStorage.setItem(STORIES_CACHE_KEY, JSON.stringify(cacheMap));
}

function readCustomPackagesMap() {
  try {
    const raw = localStorage.getItem(CUSTOM_PACKAGES_CACHE_KEY);
    if (!raw) {
      return {};
    }
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    return {};
  }
}

function writeCustomPackagesMap(cacheMap) {
  localStorage.setItem(CUSTOM_PACKAGES_CACHE_KEY, JSON.stringify(cacheMap));
}

function customPackageEntryId(row) {
  return String(
    row?.id ||
    row?.session?.meta?.shelfEntryId ||
    row?.session?.meta?.replayOf ||
    row?.session?.id ||
    ""
  );
}

function customPackageUpdatedAt(row) {
  return Number(row?.updatedAt || row?.session?.updatedAt || row?.session?.createdAt || 0);
}

function dedupeCustomPackageRows(rows) {
  const deduped = [];
  const seen = new Map();

  for (const row of Array.isArray(rows) ? rows : []) {
    const entryId = customPackageEntryId(row);
    if (!entryId) {
      continue;
    }
    const previousIndex = seen.get(entryId);
    if (previousIndex === undefined) {
      seen.set(entryId, deduped.length);
      deduped.push({
        ...row,
        id: entryId,
      });
      continue;
    }
    const current = deduped[previousIndex];
    if (customPackageUpdatedAt(row) > customPackageUpdatedAt(current)) {
      deduped[previousIndex] = {
        ...row,
        id: entryId,
      };
    }
  }

  return deduped.sort((left, right) => customPackageUpdatedAt(right) - customPackageUpdatedAt(left));
}

export function readStoriesCache(userId) {
  if (!userId) {
    return [];
  }
  const cacheMap = readCacheMap();
  const stories = cacheMap[userId];
  return Array.isArray(stories) ? stories : [];
}

export function writeStoriesCache(userId, stories) {
  if (!userId) {
    return;
  }
  const cacheMap = readCacheMap();
  cacheMap[userId] = Array.isArray(stories) ? stories : [];
  writeCacheMap(cacheMap);
}

export function upsertStoryCache(userId, story) {
  if (!userId || !story?.id) {
    return;
  }
  const existing = readStoriesCache(userId);
  const sessionId = String(story?.meta?.sessionId || "");
  const nextStories = [
    story,
    ...existing.filter((item) => {
      if (item?.id === story.id) {
        return false;
      }
      if (!sessionId) {
        return true;
      }
      return String(item?.meta?.sessionId || "") !== sessionId;
    })
  ];
  writeStoriesCache(userId, nextStories);
}

export function clearStoriesCache(userId) {
  if (!userId) {
    return;
  }
  const cacheMap = readCacheMap();
  delete cacheMap[userId];
  writeCacheMap(cacheMap);
}

export function readCustomPackagesCache(userId) {
  if (!userId) {
    return [];
  }
  const cacheMap = readCustomPackagesMap();
  const rows = Array.isArray(cacheMap[userId]) ? cacheMap[userId] : [];
  const dedupedRows = dedupeCustomPackageRows(rows);
  if (dedupedRows.length !== rows.length) {
    cacheMap[userId] = dedupedRows;
    writeCustomPackagesMap(cacheMap);
  }
  return dedupedRows;
}

export function upsertCustomPackageCache(userId, sessionPayload) {
  if (!userId || !sessionPayload?.id) {
    return;
  }
  const sourceType = String(sessionPayload?.sourceType || sessionPayload?.meta?.sourceType || "").toLowerCase();
  if (sourceType !== "custom") {
    return;
  }
  const cacheMap = readCustomPackagesMap();
  const rows = dedupeCustomPackageRows(Array.isArray(cacheMap[userId]) ? cacheMap[userId] : []);
  const shelfEntryId = String(
    sessionPayload?.meta?.shelfEntryId ||
    sessionPayload?.meta?.replayOf ||
    sessionPayload.id
  );
  const row = {
    id: shelfEntryId,
    updatedAt: Date.now(),
    opening: sessionPayload?.meta?.opening || "",
    title: sessionPayload?.package?.title || "",
    sourceType: "custom",
    session: sessionPayload,
  };
  cacheMap[userId] = [row, ...rows.filter((item) => customPackageEntryId(item) !== row.id)];
  writeCustomPackagesMap(cacheMap);
}

export function deleteCustomPackageCache(userId, packageId) {
  if (!userId || !packageId) {
    return;
  }
  const cacheMap = readCustomPackagesMap();
  const rows = dedupeCustomPackageRows(Array.isArray(cacheMap[userId]) ? cacheMap[userId] : []);
  cacheMap[userId] = rows.filter((item) => customPackageEntryId(item) !== String(packageId));
  writeCustomPackagesMap(cacheMap);
}

export function readLibraryStoriesCache() {
  try {
    const raw = localStorage.getItem(LIBRARY_STORIES_CACHE_KEY);
    if (!raw) {
      return { rows: [], updatedAt: 0 };
    }
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") {
      return { rows: [], updatedAt: 0 };
    }
    if (Array.isArray(parsed.rows)) {
      return {
        rows: parsed.rows,
        updatedAt: Number(parsed.updatedAt || 0)
      };
    }
    if (parsed.data && typeof parsed.data === "object") {
      return {
        rows: Object.values(parsed.data),
        updatedAt: Number(parsed.updatedAt || 0)
      };
    }
    if (Array.isArray(parsed)) {
      return { rows: parsed, updatedAt: 0 };
    }
    return { rows: [], updatedAt: 0 };
  } catch {
    return { rows: [], updatedAt: 0 };
  }
}

export function writeLibraryStoriesCache(rows) {
  try {
    localStorage.setItem(LIBRARY_STORIES_CACHE_KEY, JSON.stringify({
      rows: Array.isArray(rows) ? rows : [],
      updatedAt: Date.now()
    }));
  } catch {
    // ignore cache persistence failures
  }
}

function readLibrarySessionCacheMap() {
  try {
    const raw = localStorage.getItem(LIBRARY_SESSION_CACHE_KEY);
    if (!raw) {
      return {};
    }
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    return {};
  }
}

function writeLibrarySessionCacheMap(cacheMap) {
  localStorage.setItem(LIBRARY_SESSION_CACHE_KEY, JSON.stringify(cacheMap));
}

export function readLibrarySessionCache(openingId) {
  if (!openingId) {
    return null;
  }
  const cacheMap = readLibrarySessionCacheMap();
  return cacheMap[openingId] || null;
}

export function writeLibrarySessionCache(openingId, sessionPayload, metadata = {}) {
  if (!openingId || !sessionPayload) {
    return;
  }
  const cacheMap = readLibrarySessionCacheMap();
  cacheMap[openingId] = {
    session: sessionPayload,
    updatedAt: Date.now(),
    seedUpdatedAt: Number(metadata.seedUpdatedAt || 0),
  };
  writeLibrarySessionCacheMap(cacheMap);
}
