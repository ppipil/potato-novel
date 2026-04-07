const STORIES_CACHE_KEY = "potato-novel-stories-cache-v1";
const LIBRARY_SESSION_CACHE_KEY = "potato-novel-library-session-cache-v1";
const LIBRARY_STORIES_CACHE_KEY = "potato-novel-library-stories";

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
  const nextStories = [
    story,
    ...existing.filter((item) => item?.id !== story.id)
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

export function writeLibrarySessionCache(openingId, sessionPayload) {
  if (!openingId || !sessionPayload) {
    return;
  }
  const cacheMap = readLibrarySessionCacheMap();
  cacheMap[openingId] = {
    session: sessionPayload,
    updatedAt: Date.now()
  };
  writeLibrarySessionCacheMap(cacheMap);
}
