const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

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

export async function generateStory(payload) {
  const response = await fetch(`${API_BASE_URL}/api/story/generate`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    credentials: "include",
    body: JSON.stringify(payload)
  });
  if (!response.ok) {
    const error = await response.text();
    throw new Error(error || "Story generation failed");
  }
  return response.json();
}

export async function saveStory(payload) {
  const response = await fetch(`${API_BASE_URL}/api/story/save`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    credentials: "include",
    body: JSON.stringify(payload)
  });
  if (!response.ok) {
    const error = await response.text();
    throw new Error(error || "Story save failed");
  }
  return response.json();
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

export function getLoginUrl() {
  return `${API_BASE_URL}/api/auth/login`;
}
