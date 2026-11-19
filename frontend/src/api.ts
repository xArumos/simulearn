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
  /** Ages (in years) that have a trained model, sorted. */
  ages: number[];
  /** The config's label per age, keyed by the age as a string, e.g. {"5": "60-71 months"}. May be "". */
  age_labels: Record<string, string>;
  /** The age to start with; null only when no age has a model. */
  default_age: number | null;
  scenarios: Scenario[];
  /** Whether conversations are stored (MongoDB configured on the server). */
  saving: boolean;
  compare_default: boolean;
}

export interface ModelInfo {
  base_model: string;
  /** Adapter run name per age, keyed by the age as a string. */
  adapters: Record<string, string>;
  decoding: Record<string, number | string | boolean>;
  /** How many earlier turns the model sees (trimmed like in training). */
  context_turns: number;
  load_in_4bit: boolean;
  device: string;
}

export interface SessionCreated {
  id: string;
  age: number;
  scenario_id: string | null;
  compare: boolean;
}

/** PATCH /api/sessions/{id}: the session after switching compare on or off. */
export interface SessionState extends SessionCreated {
  /** The first turn the untrained model answers (since compare was last switched on); null = never on. */
  compare_started_turn: number | null;
}

export interface TurnReply {
  turn: number;
  /** The raw reply; may contain <SILENCE FOR X SECONDS> tags. */
  text: string;
  /** The server's Markdown rendering for the Gradio demo. This app renders `text` itself (src/lib/reply.ts). */
  rendered: string;
  /** Seconds of a leading silence tag (the child pauses before answering), else null. */
  pause_s: number | null;
  /** Generation time in seconds. */
  secs: number;
}

/**
 * POST /api/feedback answer (#59). `saved: false` with `ok: true` means saving is off: the rating is kept
 * by this server process only (it shows in the reopened session until a restart). `ok: false` means saving
 * is on but the write failed.
 */
export interface FeedbackResult {
  ok: boolean;
  saved: boolean;
}

/** One row of GET /api/sessions?limit= (the user's own sessions, newest first). */
export interface SessionSummary {
  id: string;
  /** ISO 8601 in UTC, e.g. "2026-11-19T14:03:00.123Z". */
  created_at: string;
  age: number;
  /** null = free practice (no scenario), or a scenario no longer in the config. */
  scenario_title: string | null;
  /** Number of turns (adult line + child reply). */
  turns: number;
  /** Whether the untrained side is on (as the session was left). */
  compare: boolean;
}

/** The user's latest rating of one reply. */
export interface Rating {
  liked: boolean;
  /** "" when no note was given. */
  note: string;
}

/** One side's reply in a reopened session. */
export interface SessionReply {
  /** The raw reply; may contain <SILENCE FOR X SECONDS> tags; "" = the model said nothing. */
  text: string;
  /** Seconds of a leading silence tag, else null. */
  pause_s: number | null;
  /** Generation time in seconds (null if unknown). */
  secs: number | null;
  rating: Rating | null;
}

export interface SessionExchange {
  turn: number;
  adult: string;
  child: SessionReply;
  /** null when compare was off at this turn. */
  untrained: SessionReply | null;
}

/** GET /api/sessions/{id}: the full session for a read-only reopen. Also the JSON export. */
export interface SessionDetail extends SessionSummary {
  /** The config's label for the age, e.g. "60-71 months"; may be "". */
  age_label: string;
  scenario_id: string | null;
  compare_started_turn: number | null;
  /** What produced each side: the child model ("age5:<adapter run>") and the base model; null = none. */
  models: { child: string | null; untrained: string | null };
  /** In turn order. */
  exchanges: SessionExchange[];
}

export type ExportFormat = "txt" | "json";

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
    request<SessionState>("PATCH", `/api/sessions/${encodeURIComponent(sessionId)}`, { compare }),

  // #59
  feedback: (f: FeedbackIn) => request<FeedbackResult>("POST", "/api/feedback", f),
  /** The user's own sessions, newest first (limit 1-200). With saving off: only this server process's. */
  sessions: (limit = 50) => request<SessionSummary[]>("GET", `/api/sessions?limit=${limit}`),
  session: (sessionId: string) => request<SessionDetail>("GET", `/api/sessions/${encodeURIComponent(sessionId)}`),
  /** A download link (the server sends Content-Disposition with a filename); use it as an <a href>. */
  exportUrl: (sessionId: string, format: ExportFormat) =>
    `/api/sessions/${encodeURIComponent(sessionId)}/export?format=${format}`,
};

export const queryKeys = {
  me: ["me"] as const,
  config: ["config"] as const,
  modelInfo: ["model-info"] as const,
};
