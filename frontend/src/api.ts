import type { GraphResult } from "./types";

// Points at the FastAPI backend (app/main.py). Set VITE_API_URL at build
// time for the deployed frontend; falls back to localhost for dev.
const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => null);
    throw new Error(detail?.detail ?? `Request failed (${res.status})`);
  }
  return res.json();
}

export function analyze(issueUrl: string): Promise<GraphResult> {
  return post<GraphResult>("/api/analyze", { issue_url: issueUrl });
}

export function resume(threadId: string, approved: boolean): Promise<GraphResult> {
  return post<GraphResult>(`/api/resume/${threadId}`, { approved });
}
