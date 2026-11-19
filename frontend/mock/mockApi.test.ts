import { describe, expect, it } from "vitest";
import type { FeedbackResult, SessionDetail, SessionSummary } from "@/api";
import { createMockApi } from "./mockApi";

function loggedIn(opts: Parameters<typeof createMockApi>[0] = {}) {
  const api = createMockApi({
    users: [
      { username: "ada", display_name: "Ada", role: "educator", password: "pw-ada-123" },
      { username: "bob", display_name: "Bob", role: "educator", password: "pw-bob-123" },
    ],
    childReplies: ["<SILENCE FOR 3 SECONDS> my dog", "yeah"],
    ...opts,
  });
  const login = (username: string) =>
    api.handle({ method: "POST", path: "/api/auth/login", body: { username, password: `pw-${username}-123` } })
      .setCookie!.value!;
  const as = (token: string) => (method: string, path: string, body?: unknown) => api.handle({ method, path, body, token });
  return { api, ada: as(login("ada")), bob: as(login("bob")) };
}

describe("mock API: feedback, history, reopen, export (#59)", () => {
  it("lists only the user's sessions, newest first, honouring ?limit=", () => {
    const { ada, bob } = loggedIn();
    const first = (ada("POST", "/api/sessions", { age: 4, compare: false, scenario_id: "tower" }).body as { id: string }).id;
    ada("POST", `/api/sessions/${first}/turns`, { adult_line: "hi" });
    const second = (ada("POST", "/api/sessions", { age: 5, compare: true }).body as { id: string }).id;
    bob("POST", "/api/sessions", { age: 5, compare: false });

    const rows = ada("GET", "/api/sessions?limit=50").body as SessionSummary[];
    expect(rows.map((r) => r.id)).toEqual([second, first]);
    expect(rows[1]).toMatchObject({ age: 4, scenario_title: "Building a tower", turns: 1, compare: false });
    expect(ada("GET", "/api/sessions", undefined).body).toHaveLength(2);
    expect(ada("GET", "/api/sessions?limit=1").body).toHaveLength(1);
    expect(ada("GET", "/api/sessions?limit=0").status).toBe(422);
    expect(bob("GET", "/api/sessions").body).toHaveLength(1);
  });

  it("rates a reply, shows it in the reopened session and hides it from others", () => {
    const { ada, bob } = loggedIn();
    const id = (ada("POST", "/api/sessions", { age: 5, compare: true }).body as { id: string }).id;
    ada("POST", `/api/sessions/${id}/turns`, { adult_line: "what's that?" });
    ada("POST", `/api/sessions/${id}/turns/1/untrained`);

    const fb = ada("POST", "/api/feedback", { session_id: id, turn: 1, side: "child", liked: true, note: " nice " });
    expect(fb.body as FeedbackResult).toEqual({ ok: true, saved: false });
    expect(ada("POST", "/api/feedback", { session_id: id, turn: 2, side: "child", liked: true }).status).toBe(404);
    expect(bob("POST", "/api/feedback", { session_id: id, turn: 1, side: "child", liked: true }).status).toBe(404);

    const d = ada("GET", `/api/sessions/${id}`).body as SessionDetail;
    expect(d.models).toEqual({ child: "age5:mock-run-age5", untrained: "example-org/mock-base-model" });
    expect(d.exchanges[0].child).toMatchObject({ pause_s: 3, rating: { liked: true, note: "nice" } });
    expect(d.exchanges[0].untrained?.rating).toBeNull();
    expect(bob("GET", `/api/sessions/${id}`).status).toBe(404);
  });

  it("exports txt and json with a filename", () => {
    const { ada, bob } = loggedIn({ saving: true });
    const id = (ada("POST", "/api/sessions", { age: 5, compare: false, scenario_id: "snack" }).body as { id: string }).id;
    ada("POST", `/api/sessions/${id}/turns`, { adult_line: "what did you bring?" });

    const txt = ada("GET", `/api/sessions/${id}/export?format=txt`);
    expect(txt.headers?.["Content-Disposition"]).toMatch(/^attachment; filename="simulearn-\d{8}-\d{4}-age5-.+\.txt"$/);
    expect(txt.text).toContain("Scenario: Snack time");
    expect(txt.text).toContain("Adult: what did you bring?\nChild: (pauses 3 s) my dog");
    expect(txt.text).not.toContain("Untrained AI:");

    const json = ada("GET", `/api/sessions/${id}/export`, undefined);
    expect(json.headers?.["Content-Type"]).toMatch(/^text\/plain/); // txt is the default
    const asJson = ada("GET", `/api/sessions/${id}/export?format=json`);
    expect(JSON.parse(asJson.text!)).toEqual(ada("GET", `/api/sessions/${id}`).body);
    expect(ada("GET", `/api/sessions/${id}/export?format=pdf`).status).toBe(422);
    expect(bob("GET", `/api/sessions/${id}/export?format=txt`).status).toBe(404);
  });
});
