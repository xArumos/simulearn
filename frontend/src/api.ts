/**
 * Typed client for the SimuLearn product API (src/product/server.py).
 *
 * Auth routes follow issue #55; the rest follow #58 (sessions, turns, config)
 * and #59 (feedback, history, export). The session cookie is httpOnly, so this
 * code never sees it: `fetch` sends it automatically on same-origin requests.
 */

export type Role = "admin" | "educator";

export interface Me {
  username: string;
  display_name: string;
  role: Role;
}

export interface Scenario {
  id: string;
  title: string;
  scene: string;
  opening_line: string;
}

export interface AppConfig {
  ages: number[];
  age_labels?: Record<string, string>;
  scenarios: Scenario[];
  /** Whether conversations are stored (MongoDB configured on the server). */
  saving: boolean;
  compare_default: boolean;
}

export interface ModelInfo {
  base_model: string;
  adapters: Record<string, string>;
  decoding: Record<string, number | string>;
  device: string;
}

export interface SessionCreated {
  id: string;
  age: number;
  scenario_id: string | null;
  compare: boolean;
}

export interface TurnReply {
  turn: number;
  text: string;
  rendered: string;
  pause_s: number | null;
  secs: number;
}

export interface SessionSummary {
  id: string;
  created_at: string;
  age: number;
  scenario_title: string | null;
  turns: number;
  compare: boolean;
}

export interface FeedbackIn {
  session_id: string;
  turn: number;
  side: "child" | "untrained";
  liked: boolean;
  note?: string;
}

/** An HTTP error from the API, with the server's message when it sent one. */
export class ApiError extends Error {
  readonly status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

/** Pull a readable message out of a FastAPI error body (`{detail: ...}`). */
export function errorMessage(body: unknown, status: number): string {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string" && detail) return detail;
  if (Array.isArray(detail) && detail.length > 0) {
    const first = detail[0] as { msg?: unknown };
    if (typeof first?.msg === "string") return first.msg;
  }
  if (status === 401) return "Please sign in.";
  if (status === 429) return "Too many attempts. Please wait a few minutes and try again.";
  if (status >= 500) return "The server had a problem. Please try again.";
  return `Request failed (${status}).`;
}

export async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, {
      method,
      credentials: "same-origin",
      headers: body === undefined ? { Accept: "application/json" } : { Accept: "application/json", "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, "Can't reach the SimuLearn server. Check your connection and try again.");
  }
  const text = await res.text();
  let data: unknown = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = text;
    }
  }
  if (!res.ok) throw new ApiError(res.status, errorMessage(data, res.status));
  return data as T;
}

export const api = {
  login: (username: string, password: string) => request<Me>("POST", "/api/auth/login", { username, password }),
  logout: () => request<unknown>("POST", "/api/auth/logout"),
  /** The logged-in user, or `null` when not logged in (401). */
  me: async (): Promise<Me | null> => {
    try {
      return await request<Me>("GET", "/api/me");
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) return null;
      throw e;
    }
  },
  changePassword: (current_password: string, new_password: string) =>
    request<unknown>("POST", "/api/me/password", { current_password, new_password }),

  // #58
  config: () => request<AppConfig>("GET", "/api/config"),
  modelInfo: () => request<ModelInfo>("GET", "/api/model-info"),
  startSession: (age: number, compare: boolean, scenario_id?: string) =>
    request<SessionCreated>("POST", "/api/sessions", { age, compare, scenario_id }),
  sendTurn: (sessionId: string, adult_line: string) =>
    request<TurnReply>("POST", `/api/sessions/${encodeURIComponent(sessionId)}/turns`, { adult_line }),
  untrainedReply: (sessionId: string, turn: number) =>
    request<TurnReply>("POST", `/api/sessions/${encodeURIComponent(sessionId)}/turns/${turn}/untrained`),
  setCompare: (sessionId: string, compare: boolean) =>
    request<unknown>("PATCH", `/api/sessions/${encodeURIComponent(sessionId)}`, { compare }),

  // #59
  feedback: (f: FeedbackIn) => request<unknown>("POST", "/api/feedback", f),
  sessions: (limit = 50) => request<SessionSummary[]>("GET", `/api/sessions?limit=${limit}`),
  session: (sessionId: string) => request<unknown>("GET", `/api/sessions/${encodeURIComponent(sessionId)}`),
  exportUrl: (sessionId: string, format: "txt" | "json") =>
    `/api/sessions/${encodeURIComponent(sessionId)}/export?format=${format}`,
};

export const queryKeys = {
  me: ["me"] as const,
  config: ["config"] as const,
};
