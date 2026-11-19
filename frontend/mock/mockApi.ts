/**
 * An in-memory stand-in for the product API's auth routes (issue #55) and
 * `/api/config` (issue #58). Used by the tests (through a fake `fetch`) and by
 * `MOCK_API=1 npm run dev` (through a Vite middleware), so the frontend can be
 * built and checked without the Python server.
 *
 * It follows the route shapes in #55: login sets an httpOnly session cookie and
 * returns the user; everything else under /api needs that cookie or gets 401.
 * The account below is invented and only exists in this mock.
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
}

export const DEFAULT_MOCK_USERS: MockUser[] = [
  { username: "demo", display_name: "Demo Educator", role: "educator", password: "practice-only" },
];

export function createMockApi(opts: MockApiOptions = {}) {
  const users = new Map((opts.users ?? DEFAULT_MOCK_USERS).map((u) => [u.username, { ...u }]));
  const sessions = new Map<string, string>(); // token -> username
  let counter = 0;
  const calls: MockRequest[] = [];

  const publicUser = (u: MockUser) => ({ username: u.username, display_name: u.display_name, role: u.role });
  const current = (token?: string | null) => {
    const name = token ? sessions.get(token) : undefined;
    return name ? users.get(name) : undefined;
  };
  const unauthorized: MockResponse = { status: 401, body: { detail: "Not logged in" } };

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
      sessions.set(token, u.username);
      return { status: 200, body: publicUser(u), setCookie: { value: token } };
    }

    if (method === "POST" && path === "/api/auth/logout") {
      if (req.token) sessions.delete(req.token);
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
          age_labels: { "4": "4 years old", "5": "5 years old" },
          scenarios: [],
          saving: opts.saving ?? false,
          compare_default: false,
        },
      };
    }

    return { status: 404, body: { detail: "Not found" } };
  }

  return { handle, calls, sessions };
}

export type MockApi = ReturnType<typeof createMockApi>;
