import type { GraphResult } from "./types";

// Points at the FastAPI backend (app/main.py). Set VITE_API_URL at build
// time for the deployed frontend; falls back to localhost for dev.
const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

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
