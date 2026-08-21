import type { GraphResult } from "./types";

// "" (same-origin, relative /api/... paths) in production — vercel.json
// proxies /api/* to the Render backend server-side, so the browser only
// ever talks to this same origin. That's not just tidiness: the session
// cookie is otherwise a cross-site ("third-party") cookie between the
// *.vercel.app and *.onrender.com domains, which Chrome blocks outright
// regardless of SameSite/Secure settings — proxying makes it first-party.
// Local dev has no such proxy, so it still talks to localhost:8000 directly.
const API_URL = import.meta.env.VITE_API_URL ?? (import.meta.env.DEV ? "http://localhost:8000" : "");

// credentials: "include" on every call — the backend authenticates via the
// httpOnly session_id cookie set by /api/auth/github/callback, not a header.
async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, { credentials: "include", ...options });
  if (!res.ok) {
    const detail = await res.json().catch(() => null);
    throw new Error(detail?.detail ?? `Request failed (${res.status})`);
  }
  return res.json();
}

function post<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function analyze(issueUrl: string): Promise<GraphResult> {
  return post<GraphResult>("/api/analyze", { issue_url: issueUrl });
}

export function resume(threadId: string, approved: boolean): Promise<GraphResult> {
  return post<GraphResult>(`/api/resume/${threadId}`, { approved });
}

export interface CurrentUser {
  login: string;
}

// Login/logout are plain navigations, not fetch() calls: GitHub's OAuth
// consent screen needs a real top-level redirect, which login() triggers
// via <a href>, not this module.
export const GITHUB_LOGIN_URL = `${API_URL}/api/auth/github/login`;

export async function getCurrentUser(): Promise<CurrentUser | null> {
  try {
    return await request<CurrentUser>("/api/auth/me");
  } catch {
    return null;
  }
}

export function logout(): Promise<{ status: string }> {
  return post<{ status: string }>("/api/auth/logout", {});
}
