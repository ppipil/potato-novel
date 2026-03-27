const USER_CACHE_KEY = "potato-novel-user-cache-v1";

export function readUserCache() {
  try {
    const raw = localStorage.getItem(USER_CACHE_KEY);
    if (!raw) {
      return null;
    }
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === "object" ? parsed : null;
  } catch {
    return null;
  }
}

export function writeUserCache(user) {
  if (!user || typeof user !== "object") {
    return;
  }
  localStorage.setItem(USER_CACHE_KEY, JSON.stringify(user));
}

export function clearUserCache() {
  localStorage.removeItem(USER_CACHE_KEY);
}
