const STORY_SESSION_CACHE_KEY = "potato-novel-session-cache-v1";

function readCacheMap() {
  try {
    const raw = localStorage.getItem(STORY_SESSION_CACHE_KEY);
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
  localStorage.setItem(STORY_SESSION_CACHE_KEY, JSON.stringify(cacheMap));
}

export function readStorySessionCache(sessionId) {
  if (!sessionId) {
    return null;
  }
  const cacheMap = readCacheMap();
  const session = cacheMap[sessionId];
  return session && typeof session === "object" ? session : null;
}

export function writeStorySessionCache(session) {
  if (!session?.id) {
    return;
  }
  const cacheMap = readCacheMap();
  cacheMap[session.id] = session;
  writeCacheMap(cacheMap);
}

export function removeStorySessionCache(sessionId) {
  if (!sessionId) {
    return;
  }
  const cacheMap = readCacheMap();
  delete cacheMap[sessionId];
  writeCacheMap(cacheMap);
}
