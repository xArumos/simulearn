/**
 * An in-memory stand-in for the product API: the auth routes (issue #55), config, model info,
 * sessions, turns and the untrained-model toggle (#58, src/product/server.py) and feedback (#59).
 * Used by the tests (through a fake `fetch`) and by `MOCK_API=1 npm run dev` (through a Vite
 * middleware), so the frontend can be built and checked without the Python server or a GPU.
 *
 * It follows the server's route shapes and status codes: login sets an httpOnly session cookie;
 * everything else under /api needs that cookie or gets 401; unknown age/scenario or a blank line
 * gives 422; an untrained reply while compare is off gives 409. The account, scenes and replies
 * below are invented for the mock (no CHILDES text).
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
  path: string;
  body?: unknown;
  /** Value of the session cookie, if the client sent one. */
  token?: string | null;
}

export interface MockResponse {
  status: number;
  body?: unknown;
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

interface MockSession {
  id: string;
  owner: string;
  age: number;
  scenario_id: string | null;
  compare: boolean;
  compare_started_turn: number | null;
  child: MockTurn[];
  untrained: MockTurn[];
}

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
  const calls: MockRequest[] = [];

  const publicUser = (u: MockUser) => ({ username: u.username, display_name: u.display_name, role: u.role });
  const current = (token?: string | null) => {
    const name = token ? logins.get(token) : undefined;
    return name ? users.get(name) : undefined;
  };
  const unauthorized: MockResponse = { status: 401, body: { detail: "Not logged in" } };
  const notFound = (detail = "Session not found"): MockResponse => ({ status: 404, body: { detail } });
  const reply = (t: MockTurn) => {
    const m = /^<SILENCE FOR (\d+) SECONDS>/.exec(t.text.trim());
    return { turn: t.turn, text: t.text, rendered: t.text, pause_s: m ? Number(m[1]) : null, secs: t.secs };
  };
  const sessionState = (s: MockSession) => ({
    id: s.id,
    age: s.age,
    scenario_id: s.scenario_id,
    compare: s.compare,
    compare_started_turn: s.compare_started_turn,
  });

  function handle(req: MockRequest): MockResponse {
    calls.push(req);
    const { method, path } = req;
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
          age_labels: { "4": "48-59 months", "5": "60-71 months" },
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
          base_model: "example-org/mock-base-model",
          adapters: { "4": "mock-run-age4", "5": "mock-run-age5" },
          decoding: { temperature: 0.7, top_p: 0.9, max_new_tokens: 60 },
          context_turns: 6,
          load_in_4bit: false,
          device: "cpu",
        },
      };
    }

    if (method === "POST" && path === "/api/sessions") {
      const age = Number(body.age);
      if (age !== 4 && age !== 5) return { status: 422, body: { detail: `No model for age ${String(body.age)}` } };
      const scenario = (body.scenario_id ?? null) as string | null;
      if (scenario !== null && !MOCK_SCENARIOS.some((s) => s.id === scenario)) {
        return { status: 422, body: { detail: `Unknown scenario '${scenario}'` } };
      }
      const compare = Boolean(body.compare);
      const s: MockSession = {
        id: `sess-${++counter}`,
        owner: u.username,
        age,
        scenario_id: scenario,
        compare,
        compare_started_turn: compare ? 1 : null,
        child: [],
        untrained: [],
      };
      practice.set(s.id, s);
      return { status: 200, body: { id: s.id, age, scenario_id: scenario, compare } };
    }

    const m = /^\/api\/sessions\/([^/]+)(\/turns(?:\/(\d+)\/untrained)?)?$/.exec(path);
    if (m) {
      const s = practice.get(decodeURIComponent(m[1]));
      if (!s || s.owner !== u.username) return notFound();

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
        if (!line) return { status: 422, body: { detail: "adult_line is empty" } };
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
      feedback.push(body);
      return { status: 200, body: { ok: true, saved: saving } };
    }

    return { status: 404, body: { detail: "Not found" } };
  }

  return { handle, calls, sessions: logins, practice, feedback };
}

export type MockApi = ReturnType<typeof createMockApi>;
