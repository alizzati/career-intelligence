import type { AnalysisResponse } from "../types/api";

const BASE = "/api"; // Vite dev proxy -> http://127.0.0.1:8000

/** network = request never completed; http = backend answered with an error status. */
export class ApiRequestError extends Error {
  constructor(public kind: "network" | "http", message: string, public status?: number,
              public code?: string, public stage?: string) { super(message); }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try { res = await fetch(BASE + path, init); }
  catch { throw new ApiRequestError("network", "Cannot reach the backend. Is it running on 127.0.0.1:8000?"); }
  let body: unknown = null;
  try { body = await res.json(); } catch { /* non-JSON body (e.g. proxy error) */ }
  if (!res.ok) {
    const e = (body as { error?: { code?: string; message?: string; stage?: string } } | null)?.error;
    throw new ApiRequestError("http", e?.message ?? `Request failed (HTTP ${res.status}).`, res.status, e?.code, e?.stage);
  }
  return body as T;
}

const json = (data: unknown): RequestInit => ({
  method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data),
});

export const health = () => request<{ status: "ok" }>("/health");
// Requires the POST /analysis/users addition (backend/app/api/routes/users.py).
export const createUser = (email: string, full_name: string) =>
  request<{ user_id: number }>("/analysis/users", json({ email, full_name }));
/** HTTP 200 with verified=false is a normal resolved value; callers must inspect final_status. */
export const analyzeProfile = (user_id: number, target_career_id?: string) =>
  request<AnalysisResponse>("/analysis/profile", json({ user_id, ...(target_career_id ? { target_career_id } : {}) }));
export function analyzeCv(user_id: number, file: File, target_career_id?: string) {
  const form = new FormData();
  form.append("user_id", String(user_id));
  form.append("file", file);
  if (target_career_id) form.append("target_career_id", target_career_id);
  return request<AnalysisResponse>("/analysis/cv", { method: "POST", body: form });
}
