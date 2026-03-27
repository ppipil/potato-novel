const STORIES_CACHE_KEY = "potato-novel-stories-cache-v1";

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
