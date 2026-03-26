const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || window.location.origin;

export async function getCurrentUser() {
  const response = await fetch(`${API_BASE_URL}/api/me`, {
    credentials: "include"
  });
  return response.json();
}

export async function exchangeCode(payload) {
  const response = await fetch(`${API_BASE_URL}/api/auth/exchange`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    credentials: "include",
    body: JSON.stringify(payload)
  });
  if (!response.ok) {
    const error = await response.text();
    throw new Error(error || "OAuth exchange failed");
  }
  return response.json();
}

export async function logout() {
  await fetch(`${API_BASE_URL}/api/auth/logout`, {
    method: "POST",
    credentials: "include"
  });
}

async function postJson(path, payload, fallbackMessage) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    credentials: "include",
    body: JSON.stringify(payload)
  });
  if (!response.ok) {
    const error = await response.text();
    throw new Error(error || fallbackMessage);
  }
  return response.json();
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
  const response = await fetch(`${API_BASE_URL}/api/story/sessions/${sessionId}`, {
    credentials: "include"
  });
  if (!response.ok) {
    const error = await response.text();
    throw new Error(error || "Story session fetch failed");
  }
  return response.json();
}

export async function hydrateStorySession(sessionId) {
  return postJson(`/api/story/sessions/${sessionId}/hydrate`, {}, "Story session hydrate failed");
}

export async function listStories() {
  const response = await fetch(`${API_BASE_URL}/api/stories`, {
    credentials: "include"
  });
  if (!response.ok) {
    const error = await response.text();
    throw new Error(error || "Story list failed");
  }
  return response.json();
}

export async function getStory(storyId) {
  const response = await fetch(`${API_BASE_URL}/api/stories/${storyId}`, {
    credentials: "include"
  });
  if (!response.ok) {
    const error = await response.text();
    throw new Error(error || "Story fetch failed");
  }
  return response.json();
}

export async function cacheStoryEndingAnalysis(storyId, payload) {
  return postJson(`/api/stories/${storyId}/ending-analysis`, payload, "Story ending analysis cache failed");
}

export function getLoginUrl() {
  return `${API_BASE_URL}/api/auth/login`;
}
