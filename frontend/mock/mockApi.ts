/**
 * An in-memory stand-in for the product API: the auth routes (issue #55), config, model info,
 * sessions, turns and the untrained-model toggle (#58, src/product/server.py) and feedback,
 * history, reopen and export (#59).
 * Used by the tests (through a fake `fetch`) and by `MOCK_API=1 npm run dev` (through a Vite
 * middleware), so the frontend can be built and checked without the Python server or a GPU.
 *
 * It follows the server's route shapes and status codes: login sets an httpOnly session cookie;
 * everything else under /api needs that cookie or gets 401; unknown age/scenario or a blank line
 * gives 422; an untrained reply while compare is off gives 409; someone else's session gives 404.
 * The account, scenes and replies below are invented for the mock (no CHILDES text).
 *
 * Query strings (`?limit=`, `?format=`) are read from `path` when the caller leaves them on, or from
 * `query`. The export route answers with `text` (the raw file) and `headers` (Content-Type and
 * Content-Disposition) instead of a JSON `body`.
 */

export const MOCK_COOKIE = "simulearn_session";

export interface MockUser {
  username: string;
  display_name: string;
  role: "admin" | "educator";
  password: string;
}

export interface MockRequest {
  method: string;
  /** May include a query string. */
  path: string;
  /** Query parameters, if the caller split them off `path`. */
  query?: Record<string, string>;
  body?: unknown;
  /** Value of the session cookie, if the client sent one. */
  token?: string | null;
}

export interface MockResponse {
  status: number;
  body?: unknown;
  /** A raw (non-JSON) response body, e.g. a .txt export; send it as is, with `headers`. */
  text?: string;
  headers?: Record<string, string>;
  /** A Set-Cookie value; `null` value means "clear the cookie". */
  setCookie?: { value: string | null };
}

export interface MockApiOptions {
  users?: MockUser[];
  saving?: boolean;
  /** Replies of the child model, used in turn (cycled). */
  childReplies?: string[];
  /** Replies of the untrained model, used in turn (cycled). */
  untrainedReplies?: string[];
}

export const DEFAULT_MOCK_USERS: MockUser[] = [
  { username: "demo", display_name: "Demo Educator", role: "educator", password: "practice-only" },
];

export const MOCK_SCENARIOS = [
  {
    id: "tower",
    title: "Building a tower",
    scene: "The child is stacking cardboard boxes in the reading corner.",
    opening_line: "Wow, how tall is your tower going to be?",
  },
  {
    id: "snack",
    title: "Snack time",
    scene: "The class is sitting down for an afternoon snack.",
    opening_line: "What did you bring for snack today?",
  },
];

const MOCK_BASE_MODEL = "example-org/mock-base-model";
const MOCK_ADAPTERS: Record<string, string> = { "4": "mock-run-age4", "5": "mock-run-age5" };
const MOCK_AGE_LABELS: Record<string, string> = { "4": "48-59 months", "5": "60-71 months" };

const DEFAULT_CHILD_REPLIES = [
  "my tower is gonna be super tall",
  "<SILENCE FOR 3 SECONDS> um the blue one",
  "yeah and then it falled down",
  "no",
];
const DEFAULT_UNTRAINED_REPLIES = [
  "That sounds like a wonderful idea! I would love to build a tall tower together.",
  "Great question! I think the blue block would be the best choice for the top.",
];

interface MockTurn {
  turn: number;
  adult: string;
  text: string;
  secs: number;
}

type Side = "child" | "untrained";

interface MockSession {
  id: string;
  owner: string;
  created_at: string;
  age: number;
  scenario_id: string | null;
  compare: boolean;
  compare_started_turn: number | null;
  child: MockTurn[];
  untrained: MockTurn[];
  /** Latest rating per "side:turn". */
  ratings: Map<string, { liked: boolean; note: string }>;
}

const SILENCE = /<SILENCE FOR (\d+) SECONDS>/g;
const pauseOf = (text: string) => {
  const m = /^<SILENCE FOR (\d+) SECONDS>/.exec(text.trim());
  return m ? Number(m[1]) : null;
};
const oneLine = (text: string) => text.split(/\s+/).filter(Boolean).join(" ");
const plainReply = (text: string) => oneLine(text.replace(SILENCE, "(pauses $1 s)")) || "(no reply)";

export function createMockApi(opts: MockApiOptions = {}) {
  const users = new Map((opts.users ?? DEFAULT_MOCK_USERS).map((u) => [u.username, { ...u }]));
  const logins = new Map<string, string>(); // token -> username
  const practice = new Map<string, MockSession>();
  const feedback: unknown[] = [];
  const childReplies = opts.childReplies ?? DEFAULT_CHILD_REPLIES;
  const untrainedReplies = opts.untrainedReplies ?? DEFAULT_UNTRAINED_REPLIES;
  const saving = opts.saving ?? false;
  let counter = 0;
  let childCount = 0;
  let untrainedCount = 0;
  // Sessions get increasing timestamps so "newest first" is well defined even within one millisecond.
  let clock = Date.parse("2026-01-05T09:00:00Z");
  const calls: MockRequest[] = [];

  const publicUser = (u: MockUser) => ({ username: u.username, display_name: u.display_name, role: u.role });
  const current = (token?: string | null) => {
    const name = token ? logins.get(token) : undefined;
    return name ? users.get(name) : undefined;
  };
  const unauthorized: MockResponse = { status: 401, body: { detail: "Not logged in" } };
  const notFound = (detail = "Session not found"): MockResponse => ({ status: 404, body: { detail } });
  const unprocessable = (detail: string): MockResponse => ({ status: 422, body: { detail } });
  const reply = (t: MockTurn) => ({ turn: t.turn, text: t.text, rendered: t.text, pause_s: pauseOf(t.text), secs: t.secs });
  const sessionState = (s: MockSession) => ({
    id: s.id,
    age: s.age,
    scenario_id: s.scenario_id,
    compare: s.compare,
    compare_started_turn: s.compare_started_turn,
  });
  const scenarioTitle = (s: MockSession) => MOCK_SCENARIOS.find((x) => x.id === s.scenario_id)?.title ?? null;
  const summary = (s: MockSession) => ({
    id: s.id,
    created_at: s.created_at,
    age: s.age,
    scenario_title: scenarioTitle(s),
    turns: s.child.length,
    compare: s.compare,
  });
  const sessionReply = (s: MockSession, side: Side, t: MockTurn) => ({
    text: t.text,
    pause_s: pauseOf(t.text),
    secs: t.secs,
    rating: s.ratings.get(`${side}:${t.turn}`) ?? null,
  });
  const detail = (s: MockSession) => ({
    ...summary(s),
    age_label: MOCK_AGE_LABELS[String(s.age)] ?? "",
    scenario_id: s.scenario_id,
    compare_started_turn: s.compare_started_turn,
    models: {
      child: s.child.length ? `age${s.age}:${MOCK_ADAPTERS[String(s.age)]}` : null,
      untrained: s.compare_started_turn !== null ? MOCK_BASE_MODEL : null,
    },
    exchanges: s.child.map((t) => {
      const u = s.untrained.find((x) => x.turn === t.turn);
      return { turn: t.turn, adult: t.adult, child: sessionReply(s, "child", t), untrained: u ? sessionReply(s, "untrained", u) : null };
    }),
  });
  const exportTxt = (s: MockSession) => {
    const d = detail(s);
    const lines = [
      "SimuLearn practice session",
      `Date: ${d.created_at.slice(0, 16).replace("T", " ")} UTC`,
      `Child age: ${d.age}${d.age_label ? ` (${d.age_label})` : ""}`,
      `Scenario: ${d.scenario_title ?? "free practice (no scenario)"}`,
      `Session: ${d.id}`,
      `Model for "Child": fine-tuned child model (${d.models.child ?? "none yet"})`,
      ...(d.models.untrained ? [`Model for "Untrained AI": the same base model without fine-tuning (${d.models.untrained})`] : []),
      `Turns: ${d.turns}`,
      "",
    ];
    for (const ex of d.exchanges) {
      lines.push(`Adult: ${oneLine(ex.adult)}`, `Child: ${plainReply(ex.child.text)}`);
      if (ex.untrained) lines.push(`Untrained AI: ${plainReply(ex.untrained.text)}`);
      lines.push("");
    }
    return lines.join("\n");
  };

  function handle(req: MockRequest): MockResponse {
    calls.push(req);
    const { method } = req;
    const [path, search = ""] = req.path.split("?", 2);
    const query = { ...Object.fromEntries(new URLSearchParams(search)), ...(req.query ?? {}) };
    const body = (req.body ?? {}) as Record<string, unknown>;

    if (method === "POST" && path === "/api/auth/login") {
      const u = users.get(String(body.username ?? ""));
      if (!u || u.password !== body.password) {
        // Same answer for unknown user and wrong password, as in #55.
        return { status: 401, body: { detail: "Incorrect username or password" } };
      }
      const token = `mock-${++counter}`;
      logins.set(token, u.username);
      return { status: 200, body: publicUser(u), setCookie: { value: token } };
    }

    if (method === "POST" && path === "/api/auth/logout") {
      if (req.token) logins.delete(req.token);
      return { status: 200, body: { ok: true }, setCookie: { value: null } };
    }

    const u = current(req.token);
    if (!u) return unauthorized;

    if (method === "GET" && path === "/api/me") return { status: 200, body: publicUser(u) };

    if (method === "POST" && path === "/api/me/password") {
      if (body.current_password !== u.password) {
        return { status: 400, body: { detail: "Current password is incorrect" } };
      }
      const next = String(body.new_password ?? "");
      if (next.length < 8) {
        return { status: 400, body: { detail: "New password must be at least 8 characters" } };
      }
      u.password = next;
      return { status: 200, body: { ok: true } };
    }

    if (method === "GET" && path === "/api/config") {
      return {
        status: 200,
        body: {
          ages: [4, 5],
          age_labels: MOCK_AGE_LABELS,
          default_age: 5,
          scenarios: MOCK_SCENARIOS,
          saving,
          compare_default: false,
        },
      };
    }

    if (method === "GET" && path === "/api/model-info") {
      return {
        status: 200,
        body: {
          base_model: MOCK_BASE_MODEL,
          adapters: MOCK_ADAPTERS,
          decoding: { temperature: 0.7, top_p: 0.9, max_new_tokens: 60 },
          context_turns: 6,
          load_in_4bit: false,
          device: "cpu",
        },
      };
    }

    if (method === "GET" && path === "/api/sessions") {
      const limit = query.limit === undefined ? 50 : Number(query.limit);
      if (!Number.isInteger(limit) || limit < 1 || limit > 200) return unprocessable("limit must be 1-200");
      const mine = [...practice.values()].filter((s) => s.owner === u.username).reverse();
      mine.sort((a, b) => b.created_at.localeCompare(a.created_at));
      return { status: 200, body: mine.slice(0, limit).map(summary) };
    }

    if (method === "POST" && path === "/api/sessions") {
      const age = Number(body.age);
      if (age !== 4 && age !== 5) return unprocessable(`No model for age ${String(body.age)}`);
      const scenario = (body.scenario_id ?? null) as string | null;
      if (scenario !== null && !MOCK_SCENARIOS.some((s) => s.id === scenario)) {
        return unprocessable(`Unknown scenario '${scenario}'`);
      }
      const compare = Boolean(body.compare);
      clock += 60_000;
      const s: MockSession = {
        id: `sess-${++counter}`,
        owner: u.username,
        created_at: new Date(clock).toISOString().replace(".000Z", "Z"),
        age,
        scenario_id: scenario,
        compare,
        compare_started_turn: compare ? 1 : null,
        child: [],
        untrained: [],
        ratings: new Map(),
      };
      practice.set(s.id, s);
      return { status: 200, body: { id: s.id, age, scenario_id: scenario, compare } };
    }

    const ex = /^\/api\/sessions\/([^/]+)\/export$/.exec(path);
    if (ex && method === "GET") {
      const s = practice.get(decodeURIComponent(ex[1]));
      if (!s || s.owner !== u.username) return notFound();
      const format = query.format ?? "txt";
      if (format !== "txt" && format !== "json") return unprocessable("format must be txt or json");
      const stamp = s.created_at.slice(0, 16).replace(/[-:]/g, "").replace("T", "-");
      const filename = `simulearn-${stamp}-age${s.age}-${s.id.replace(/[^A-Za-z0-9]/g, "").slice(0, 8)}.${format}`;
      return {
        status: 200,
        text: format === "txt" ? exportTxt(s) : `${JSON.stringify(detail(s), null, 2)}\n`,
        headers: {
          "Content-Type": format === "txt" ? "text/plain; charset=utf-8" : "application/json",
          "Content-Disposition": `attachment; filename="${filename}"`,
        },
      };
    }

    const m = /^\/api\/sessions\/([^/]+)(\/turns(?:\/(\d+)\/untrained)?)?$/.exec(path);
    if (m) {
      const s = practice.get(decodeURIComponent(m[1]));
      if (!s || s.owner !== u.username) return notFound();

      if (method === "GET" && !m[2]) return { status: 200, body: detail(s) };

      if (method === "PATCH" && !m[2]) {
        if (body.compare && !s.compare) {
          s.compare = true;
          s.compare_started_turn = s.child.length + 1;
        } else if (!body.compare && s.compare) {
          s.compare = false;
        }
        return { status: 200, body: sessionState(s) };
      }

      if (method === "POST" && m[2] && !m[3]) {
        const line = String(body.adult_line ?? "").trim();
        if (!line) return unprocessable("adult_line is empty");
        const t = { turn: s.child.length + 1, adult: line, text: childReplies[childCount++ % childReplies.length], secs: 0.42 };
        s.child.push(t);
        return { status: 200, body: reply(t) };
      }

      if (method === "POST" && m[3]) {
        if (!s.compare) return { status: 409, body: { detail: "Compare is off for this session" } };
        const n = Number(m[3]);
        const child = s.child.find((t) => t.turn === n);
        if (!child) return notFound(`Turn ${n} not found`);
        if (n < (s.compare_started_turn ?? Infinity)) return { status: 409, body: { detail: `Compare was off at turn ${n}` } };
        const done = s.untrained.find((t) => t.turn === n);
        if (done) return { status: 200, body: reply(done) };
        const t = { turn: n, adult: child.adult, text: untrainedReplies[untrainedCount++ % untrainedReplies.length], secs: 0.61 };
        s.untrained.push(t);
        return { status: 200, body: reply(t) };
      }
    }

    if (method === "POST" && path === "/api/feedback") {
      const s = practice.get(String(body.session_id ?? ""));
      if (!s || s.owner !== u.username) return notFound();
      const side = body.side;
      if (side !== "child" && side !== "untrained") return unprocessable("side must be child or untrained");
      const turn = Number(body.turn);
      if (!s[side].some((t) => t.turn === turn)) return notFound(`No ${side} reply at turn ${turn}`);
      s.ratings.set(`${side}:${turn}`, { liked: Boolean(body.liked), note: String(body.note ?? "").trim() });
      feedback.push(body);
      return { status: 200, body: { ok: true, saved: saving } };
    }

    return { status: 404, body: { detail: "Not found" } };
  }

  return { handle, calls, sessions: logins, practice, feedback };
}

export type MockApi = ReturnType<typeof createMockApi>;
