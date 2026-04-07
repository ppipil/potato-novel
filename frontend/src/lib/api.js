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

function isStoryDebugEnabled() {
  try {
    return localStorage.getItem("potato-story-debug") === "1";
  } catch {
    return false;
  }
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
  const mergedHeaders = {
    ...(options.headers || {}),
    ...(isStoryDebugEnabled() ? { "X-Story-Debug": "1" } : {})
  };
  const requestInfo = {
    url: `${API_BASE_URL}${path}`,
    method: options.method || "GET",
    body: options.body ? JSON.parse(options.body) : undefined
  };
  debugLog("request", requestInfo);

  const response = await fetch(requestInfo.url, {
    credentials: "include",
    ...options,
    headers: mergedHeaders
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

async function postJson(path, payload, fallbackMessage, requestOptions = {}) {
  return fetchJson(path, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify(payload),
    ...requestOptions
  }, fallbackMessage);
}

export async function listLibraryStories(requestOptions = {}) {
  return fetchJson("/api/library-stories", requestOptions, "Library story list failed");
}

export async function generateLibraryStorySeed(storyId, payload = {}, requestOptions = {}) {
  return postJson(`/api/library-stories/${storyId}/generate-seed`, payload, "Library seed generation failed", requestOptions);
}

export async function startLibraryStoryFromSeed(storyId, payload, requestOptions = {}) {
  return postJson(`/api/library-stories/${storyId}/start-from-seed`, payload, "Library story start from seed failed", requestOptions);
}

export async function generateCustomStorySession(payload, requestOptions = {}) {
  return postJson("/api/custom-stories/generate", payload, "Custom story generation failed", requestOptions);
}

export async function analyzeStoryEnding(payload, requestOptions = {}) {
  return postJson("/api/story/analyze-ending", payload, "Story ending analysis failed", requestOptions);
}

export async function saveStory(payload, requestOptions = {}) {
  return postJson("/api/story/save", payload, "Story save failed", requestOptions);
}

export async function listStories() {
  return fetchJson("/api/stories", {}, "Story list failed");
}

export async function getStory(storyId) {
  return fetchJson(`/api/stories/${storyId}`, {}, "Story fetch failed");
}

export async function deleteStory(storyId) {
  return fetchJson(`/api/stories/${storyId}`, { method: "DELETE" }, "Story delete failed");
}

export async function cacheStoryEndingAnalysis(storyId, payload) {
  return postJson(`/api/stories/${storyId}/ending-analysis`, payload, "Story ending analysis cache failed");
}

export function getLoginUrl() {
  return `${API_BASE_URL}/api/auth/login`;
}
