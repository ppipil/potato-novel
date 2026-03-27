const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || window.location.origin;
const FRONTEND_DEBUG_KEY = "potato-novel-debug-frontend";

function isFrontendDebugEnabled() {
  try {
    return localStorage.getItem(FRONTEND_DEBUG_KEY) === "1";
  } catch {
    return false;
  }
}

function debugLog(event, payload) {
  if (!isFrontendDebugEnabled()) {
    return;
  }
  console.log(`[potato-frontend] ${event}`, payload);
}

async function parseJsonResponse(response) {
  const text = await response.text();
  if (!text) {
    return {};
  }
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

async function fetchJson(path, options = {}, fallbackMessage = "Request failed") {
  const startedAt = performance.now();
  const requestInfo = {
    url: `${API_BASE_URL}${path}`,
    method: options.method || "GET",
    body: options.body ? JSON.parse(options.body) : undefined
  };
  debugLog("request", requestInfo);

  const response = await fetch(requestInfo.url, {
    credentials: "include",
    ...options
  });
  const elapsedMs = Math.round(performance.now() - startedAt);
  const payload = await parseJsonResponse(response);

  if (!response.ok) {
    debugLog("response-error", {
      ...requestInfo,
      status: response.status,
      elapsedMs,
      payload
    });
    const errorMessage =
      typeof payload === "string"
        ? payload
        : payload?.detail?.message || payload?.detail || payload?.message || fallbackMessage;
    throw new Error(errorMessage || fallbackMessage);
  }

  debugLog("response", {
    ...requestInfo,
    status: response.status,
    elapsedMs,
    payload
  });
  return payload;
}

export async function getCurrentUser() {
  return fetchJson("/api/me");
}

export async function exchangeCode(payload) {
  return fetchJson("/api/auth/exchange", {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify(payload)
  }, "OAuth exchange failed");
}

export async function logout() {
  await fetchJson("/api/auth/logout", {
    method: "POST",
  });
}

async function postJson(path, payload, fallbackMessage) {
  return fetchJson(path, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify(payload)
  }, fallbackMessage);
}

export async function startStorySession(payload) {
  return postJson("/api/story/start", payload, "Story start failed");
}

export async function preloadStoryPackage(payload) {
  return postJson("/api/story/preload", payload, "Story preload failed");
}

export async function regenerateStoryPackage(payload) {
  return postJson("/api/story/regenerate", payload, "Story regenerate failed");
}

export async function continueStorySession(payload) {
  return postJson("/api/story/continue", payload, "Story continuation failed");
}

export async function finalizeStorySession(payload) {
  return postJson("/api/story/finalize", payload, "Story finalization failed");
}

export async function analyzeStoryEnding(payload) {
  return postJson("/api/story/analyze-ending", payload, "Story ending analysis failed");
}

export async function generateStory(payload) {
  return startStorySession(payload);
}

export async function saveStory(payload) {
  return postJson("/api/story/save", payload, "Story save failed");
}

export async function getStorySession(sessionId) {
  return fetchJson(`/api/story/sessions/${sessionId}`, {}, "Story session fetch failed");
}

export async function hydrateStorySession(sessionId, payload = {}) {
  return postJson(`/api/story/sessions/${sessionId}/hydrate`, payload, "Story session hydrate failed");
}

export async function listStories() {
  return fetchJson("/api/stories", {}, "Story list failed");
}

export async function getStory(storyId) {
  return fetchJson(`/api/stories/${storyId}`, {}, "Story fetch failed");
}

export async function cacheStoryEndingAnalysis(storyId, payload) {
  return postJson(`/api/stories/${storyId}/ending-analysis`, payload, "Story ending analysis cache failed");
}

export function getLoginUrl() {
  return `${API_BASE_URL}/api/auth/login`;
}
