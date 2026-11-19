import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { MockApiOptions } from "../../mock/mockApi";
import { installMockApi, renderApp } from "@/test/utils";

// Invented replies (no CHILDES text).
const CHILD = ["i want the big one", "<SILENCE FOR 3 SECONDS> yeah", "no thank you"];
const UNTRAINED = ["What a lovely question! I'd be happy to help.", "Certainly! Here is my answer."];

function setup(opts: MockApiOptions = {}) {
  const mock = installMockApi({ childReplies: CHILD, untrainedReplies: UNTRAINED, ...opts });
  const token =
    mock.api.handle({ method: "POST", path: "/api/auth/login", body: { username: "demo", password: "practice-only" } }).setCookie
      ?.value ?? null;
  mock.jar.token = token;
  const call = (method: string, path: string, body?: unknown) => mock.api.handle({ method, path, body, token });
  /** Make a session straight on the mock API: `lines` adult lines, compare switched on before turn `compareFrom`. */
  const seed = (o: { age?: number; scenario_id?: string; lines?: string[]; compareFrom?: number } = {}) => {
    const compareAtStart = o.compareFrom === 1;
    const id = (call("POST", "/api/sessions", { age: o.age ?? 5, compare: compareAtStart, scenario_id: o.scenario_id }).body as {
      id: string;
    }).id;
    (o.lines ?? []).forEach((line, i) => {
      const turn = i + 1;
      if (o.compareFrom === turn && !compareAtStart) call("PATCH", `/api/sessions/${id}`, { compare: true });
      call("POST", `/api/sessions/${id}/turns`, { adult_line: line });
      if (o.compareFrom !== undefined && turn >= o.compareFrom) call("POST", `/api/sessions/${id}/turns/${turn}/untrained`);
    });
    return id;
  };
  return { ...mock, call, seed, user: userEvent.setup() };
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("history list", () => {
  it("shows an empty state with a way to start practicing", async () => {
    const { user } = setup();
    renderApp("/history");
    expect(await screen.findByText("Nothing here yet")).toBeInTheDocument();
    await user.click(screen.getByRole("link", { name: "Start practicing" }));
    expect(screen.getByTestId("location")).toHaveTextContent(/^\/$/);
  });

  it("shows a loading state, then lists sessions newest first with age, scenario, turns and a compare badge", async () => {
    const { seed, api } = setup();
    seed({ age: 4, scenario_id: "tower", lines: ["How tall is it?"] });
    seed({ age: 5, lines: ["Hi", "What's that?"], compareFrom: 1 });

    renderApp("/history");
    expect(screen.getByRole("status", { name: "Loading" })).toBeInTheDocument();
    const list = await screen.findByRole("list", { name: "Past sessions" });
    const rows = within(list).getAllByRole("listitem");
    expect(rows).toHaveLength(2);

    expect(rows[0]).toHaveTextContent("Free conversation");
    expect(rows[0]).toHaveTextContent("Age 5 years (60-71 months)");
    expect(rows[0]).toHaveTextContent("2 turns");
    expect(within(rows[0]).getByText("Compared")).toBeInTheDocument();

    expect(rows[1]).toHaveTextContent("Building a tower");
    expect(rows[1]).toHaveTextContent("Age 4 years (48-59 months)");
    expect(rows[1]).toHaveTextContent("1 turn");
    expect(within(rows[1]).queryByText("Compared")).not.toBeInTheDocument();

    // The limit reaches the (mock) server as a query string, not dropped on the way.
    expect(api.calls.some((c) => c.method === "GET" && c.path === "/api/sessions?limit=100")).toBe(true);
    // With saving off, the page says the list only covers this server run.
    expect(screen.getByRole("note")).toHaveTextContent("Saving is off");
  });

  it("shows an error with a retry when the list fails", async () => {
    const { fetchMock, user, seed } = setup();
    seed({ lines: ["Hello"] });
    const real = fetchMock.getMockImplementation()!;
    let failures = 1;
    fetchMock.mockImplementation(async (input, init) =>
      String(input).startsWith("/api/sessions?") && failures-- > 0
        ? new Response(JSON.stringify({ detail: "Database is down" }), { status: 503 })
        : real(input, init),
    );
    renderApp("/history");
    expect(await screen.findByText("Couldn't load your history")).toBeInTheDocument();
    expect(screen.getByText("Database is down")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("list", { name: "Past sessions" })).toBeInTheDocument();
  });
});

describe("reopened session", () => {
  it("opens from the list read-only: both columns, the comparison divider and the saved ratings", async () => {
    const { seed, call, user } = setup();
    const id = seed({ scenario_id: "snack", lines: ["What's for snack?", "Do you like it?", "Want some more?"], compareFrom: 2 });
    call("POST", "/api/feedback", { session_id: id, turn: 1, side: "child", liked: true, note: "Sounds like a real kid" });
    call("POST", "/api/feedback", { session_id: id, turn: 2, side: "untrained", liked: false });

    renderApp("/history");
    await user.click(await screen.findByRole("link", { name: /^Snack time,/ }));
    expect(screen.getByTestId("location")).toHaveTextContent(`/history/${id}`);

    expect(await screen.findByRole("heading", { name: "Snack time" })).toBeInTheDocument();
    const log = screen.getByRole("log", { name: "Conversation" });
    expect(within(log).getAllByRole("region", { name: "Child reply" })).toHaveLength(3);
    expect(within(log).getAllByRole("region", { name: "Untrained AI reply" })).toHaveLength(2);
    expect(within(log).getByRole("separator", { name: "Comparison started here" })).toBeInTheDocument();
    expect(within(log).getByText("(pauses 3 s)")).toBeInTheDocument();
    expect(within(log).getByText(UNTRAINED[0])).toBeInTheDocument();

    // Ratings are shown, not editable.
    expect(within(log).getByText(/You rated this a good reply/)).toHaveTextContent("Sounds like a real kid");
    expect(within(log).getByText("You rated this not a good reply")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Good reply" })).not.toBeInTheDocument();

    // Read-only: no input, no send.
    expect(screen.queryByLabelText("What you say to the child")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /send/i })).not.toBeInTheDocument();
    expect(screen.getByText(/This conversation has ended/)).toBeInTheDocument();
  });

  it("shows one column and no divider when compare was never on", async () => {
    const { seed } = setup();
    const id = seed({ lines: ["Hello"] });
    renderApp(`/history/${id}`);
    expect(await screen.findByRole("heading", { name: "Free conversation" })).toBeInTheDocument();
    expect(screen.getAllByRole("region", { name: "Child reply" })).toHaveLength(1);
    expect(screen.queryByRole("region", { name: "Untrained AI reply" })).not.toBeInTheDocument();
    expect(screen.queryByRole("separator")).not.toBeInTheDocument();
  });

  it("says when a session is not found", async () => {
    setup();
    renderApp("/history/sess-nope");
    expect(await screen.findByText("Session not found")).toBeInTheDocument();
  });

  it.each([
    ["txt", "text/plain", (text: string) => expect(text).toContain("SimuLearn practice session")],
    ["json", "application/json", (text: string) => expect(JSON.parse(text).exchanges).toHaveLength(1)],
  ] as const)("downloads the .%s export with the server's file name", async (format, type, check) => {
    const { seed, user, api } = setup();
    const id = seed({ lines: ["Hello"] });
    const saved: { name: string; blob: Blob }[] = [];
    const blobs = new Map<string, Blob>();
    vi.stubGlobal("URL", Object.assign(URL, {
      createObjectURL: (b: Blob) => {
        const u = `blob:mock/${blobs.size}`;
        blobs.set(u, b);
        return u;
      },
      revokeObjectURL: () => {},
    }));
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
      saved.push({ name: this.download, blob: blobs.get(this.getAttribute("href") ?? "")! });
    });

    renderApp(`/history/${id}`);
    await user.click(await screen.findByRole("button", { name: `Download as .${format}` }));
    await waitFor(() => expect(saved).toHaveLength(1));

    expect(saved[0].name).toMatch(new RegExp(`^simulearn-\\d{8}-\\d{4}-age5-.+\\.${format}$`));
    expect(saved[0].blob.type).toContain(type);
    check(await saved[0].blob.text());
    expect(api.calls.some((c) => c.path === `/api/sessions/${id}/export?format=${format}`)).toBe(true);
  });

  it("'Practice again with this scenario' opens Practice with the same age and scene", async () => {
    const { seed, user } = setup();
    const id = seed({ age: 4, scenario_id: "tower", lines: ["Hi"] });
    renderApp(`/history/${id}`);
    await user.click(await screen.findByRole("button", { name: "Practice again with this scenario" }));

    expect(screen.getByTestId("location")).toHaveTextContent(/^\/$/);
    const input = await screen.findByLabelText("What you say to the child");
    expect(input).toHaveValue("Wow, how tall is your tower going to be?");
    expect(screen.getByRole("note", { name: "Current scene" })).toHaveTextContent("Building a tower");
    expect(screen.getByRole("combobox", { name: "Child's age" })).toHaveTextContent("4 years (48-59 months)");
  });
});
