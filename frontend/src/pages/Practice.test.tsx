import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { MockApiOptions } from "../../mock/mockApi";
import { installMockApi, renderApp } from "@/test/utils";

// Invented replies (no CHILDES text).
const PLAIN = ["i want the big one", "yeah", "no thank you", "it's a dinosaur"];
const UNTRAINED = ["What a lovely question! I'd be happy to help.", "Certainly! Here is my answer."];

async function openPractice(opts: MockApiOptions = {}, userOpts: Parameters<typeof userEvent.setup>[0] = {}) {
  const mock = installMockApi({ childReplies: PLAIN, untrainedReplies: UNTRAINED, ...opts });
  mock.jar.token =
    mock.api.handle({ method: "POST", path: "/api/auth/login", body: { username: "demo", password: "practice-only" } }).setCookie
      ?.value ?? null;
  renderApp("/");
  await screen.findByLabelText("What you say to the child");
  const user = userEvent.setup(userOpts);
  return { ...mock, user };
}

const paths = (fetchMock: ReturnType<typeof installMockApi>["fetchMock"]) =>
  fetchMock.mock.calls.map(([u, init]) => `${init?.method ?? "GET"} ${String(u)}`);

const input = () => screen.getByLabelText("What you say to the child");
const childReplies = () => screen.queryAllByRole("region", { name: "Child reply" });
const untrainedReplies = () => screen.queryAllByRole("region", { name: "Untrained AI reply" });

async function say(user: ReturnType<typeof userEvent.setup>, line: string) {
  await user.type(input(), line);
  await user.keyboard("{Enter}");
}

afterEach(() => {
  vi.useRealTimers();
});

describe("practice view", () => {
  it("shows ages with their labels and starts at the server's default age", async () => {
    await openPractice();
    expect(screen.getByRole("combobox", { name: "Child's age" })).toHaveTextContent("5 years (60-71 months)");
  });

  it("with compare off, asks only the child model and never calls /untrained", async () => {
    const { user, fetchMock } = await openPractice();
    await say(user, "What are you building?");
    expect(await screen.findByText("i want the big one")).toBeInTheDocument();
    await say(user, "Can I help?");
    expect(await screen.findByText("yeah")).toBeInTheDocument();

    const calls = paths(fetchMock);
    expect(calls.filter((c) => c.startsWith("POST /api/sessions/") && c.endsWith("/turns"))).toHaveLength(2);
    expect(calls.some((c) => c.includes("/untrained"))).toBe(false);
    expect(untrainedReplies()).toHaveLength(0);
    expect(screen.queryByText("Untrained AI")).not.toBeInTheDocument();
    const start = fetchMock.mock.calls.find(([u, init]) => String(u) === "/api/sessions" && init?.method === "POST");
    expect(JSON.parse(String(start?.[1]?.body))).toMatchObject({ age: 5, compare: false });
  });

  it("with compare on, asks the child first and the untrained model after it", async () => {
    const { user, fetchMock } = await openPractice();
    await user.click(screen.getByRole("switch", { name: "Compare with untrained AI" }));
    await say(user, "Hi there!");
    expect(await screen.findByText(UNTRAINED[0])).toBeInTheDocument();
    expect(screen.getByText("i want the big one")).toBeInTheDocument();

    const calls = paths(fetchMock).filter((c) => c.startsWith("POST /api/sessions"));
    expect(calls).toEqual(["POST /api/sessions", expect.stringMatching(/\/turns$/), expect.stringMatching(/\/turns\/1\/untrained$/)]);
    expect(untrainedReplies()).toHaveLength(1);
    expect(screen.queryByText("Comparison started here")).not.toBeInTheDocument();
  });

  it("switching compare on mid-session marks where the comparison started; off hides it and stops the calls", async () => {
    const { user, fetchMock } = await openPractice();
    await say(user, "Good morning");
    await screen.findByText("i want the big one");

    await user.click(screen.getByRole("switch", { name: "Compare with untrained AI" }));
    await waitFor(() => expect(paths(fetchMock).some((c) => c.startsWith("PATCH /api/sessions/"))).toBe(true));
    expect(screen.getByRole("separator", { name: "Comparison started here" })).toBeInTheDocument();

    await say(user, "What's that?");
    expect(await screen.findByText(UNTRAINED[0])).toBeInTheDocument();
    expect(paths(fetchMock).filter((c) => c.includes("/untrained"))).toEqual([expect.stringMatching(/\/turns\/2\/untrained$/)]);
    // The divider sits between turn 1 and turn 2.
    const log = screen.getByRole("log", { name: "Conversation" });
    const text = log.textContent ?? "";
    expect(text.indexOf("i want the big one")).toBeLessThan(text.indexOf("Comparison started here"));
    expect(text.indexOf("Comparison started here")).toBeLessThan(text.indexOf("What's that?"));

    await user.click(screen.getByRole("switch", { name: "Compare with untrained AI" }));
    await waitFor(() => expect(untrainedReplies()).toHaveLength(0));
    await say(user, "Bye!");
    expect(await screen.findByText("no thank you")).toBeInTheDocument();
    expect(paths(fetchMock).filter((c) => c.includes("/untrained"))).toHaveLength(1);
  });

  it("shows 'thinking…' for a reply that starts with a pause, then the reply with a pause chip", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const { user } = await openPractice(
      { childReplies: ["<SILENCE FOR 3 SECONDS> um the blue one"] },
      { advanceTimers: vi.advanceTimersByTime },
    );
    await say(user, "Which one do you want?");
    expect(await screen.findByText("thinking…")).toBeInTheDocument();
    expect(screen.queryByText(/um the blue one/)).not.toBeInTheDocument();
    expect(input()).toBeDisabled();

    await act(() => vi.advanceTimersByTimeAsync(2500));
    expect(screen.getByText("thinking…")).toBeInTheDocument();

    await act(() => vi.advanceTimersByTimeAsync(600));
    const reply = await screen.findByText(/um the blue one/);
    expect(reply).toBeInTheDocument();
    expect(screen.getByText("(pauses 3 s)")).toBeInTheDocument();
    expect(screen.queryByText(/SILENCE/)).not.toBeInTheDocument();
    expect(screen.queryByText("thinking…")).not.toBeInTheDocument();
    await waitFor(() => expect(input()).toBeEnabled());
  });

  it("caps the thinking delay at 5 seconds", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const { user } = await openPractice(
      { childReplies: ["<SILENCE FOR 9 SECONDS> maybe"] },
      { advanceTimers: vi.advanceTimersByTime },
    );
    await say(user, "Are you sure?");
    expect(await screen.findByText("thinking…")).toBeInTheDocument();
    await act(() => vi.advanceTimersByTimeAsync(5100));
    expect(await screen.findByText(/maybe/)).toBeInTheDocument();
    expect(screen.getByText("(pauses 9 s)")).toBeInTheDocument();
  });

  it("sends on Enter, makes a new line on Shift+Enter and keeps the input disabled while waiting", async () => {
    const { user, fetchMock } = await openPractice();
    await user.type(input(), "First line");
    await user.keyboard("{Shift>}{Enter}{/Shift}");
    await user.type(input(), "second line");
    expect(input()).toHaveValue("First line\nsecond line");
    expect(paths(fetchMock).some((c) => c.endsWith("/turns"))).toBe(false);

    await user.keyboard("{Enter}");
    await waitFor(() => expect(input()).toHaveValue(""));
    await screen.findByText("i want the big one");
    const turn = fetchMock.mock.calls.find(([u]) => String(u).endsWith("/turns"));
    expect(JSON.parse(String(turn?.[1]?.body))).toEqual({ adult_line: "First line\nsecond line" });
    await waitFor(() => expect(input()).toBeEnabled());
  });

  it("shows a toast and gives the line back when the server rejects it", async () => {
    const { user, fetchMock } = await openPractice();
    const real = fetchMock.getMockImplementation()!;
    fetchMock.mockImplementation(async (url, init) =>
      String(url).endsWith("/turns")
        ? new Response(JSON.stringify({ detail: "adult_line is empty" }), { status: 422 })
        : real(url, init),
    );
    await say(user, "Hello?");
    expect(await screen.findByText("The child didn't answer")).toBeInTheDocument();
    expect(screen.getByText("adult_line is empty")).toBeInTheDocument();
    expect(input()).toHaveValue("Hello?");
    expect(childReplies()).toHaveLength(0);
  });

  it("sends 👍/👎 with an optional note and says when it was not saved", async () => {
    const { user, fetchMock, api } = await openPractice({ saving: false });
    await say(user, "Do you like apples?");
    await screen.findByText("i want the big one");

    const reply = childReplies()[0];
    await user.click(within(reply).getByRole("button", { name: "Not a good reply" }));
    await user.type(await screen.findByLabelText("Note (optional)"), "too short");
    await user.click(screen.getByRole("button", { name: "Send feedback" }));

    expect(await within(reply).findByText(/feedback sent/)).toHaveTextContent("not saved");
    const call = fetchMock.mock.calls.find(([u]) => String(u) === "/api/feedback");
    expect(JSON.parse(String(call?.[1]?.body))).toEqual({
      session_id: expect.any(String),
      turn: 1,
      side: "child",
      liked: false,
      note: "too short",
    });
    expect(api.feedback).toHaveLength(1);
  });

  it("does not say 'not saved' when saving is on", async () => {
    const { user } = await openPractice({ saving: true });
    await say(user, "Hello");
    await screen.findByText("i want the big one");
    const reply = childReplies()[0];
    await user.click(within(reply).getByRole("button", { name: "Good reply" }));
    await user.click(await screen.findByRole("button", { name: "Send feedback" }));
    expect(await within(reply).findByText(/feedback sent/)).not.toHaveTextContent("not saved");
  });

  it("picks a scene: banner, pre-filled editable opening line, and the scenario sent with the session", async () => {
    const { user, fetchMock } = await openPractice();
    await user.click(screen.getByRole("button", { name: "Scene" }));
    await user.click(await screen.findByRole("button", { name: /Building a tower/ }));

    expect(screen.getByRole("note", { name: "Current scene" })).toHaveTextContent("Building a tower");
    expect(input()).toHaveValue("Wow, how tall is your tower going to be?");
    await user.clear(input());
    await say(user, "How tall will it be?");
    await screen.findByText("i want the big one");
    const start = fetchMock.mock.calls.find(([u, init]) => String(u) === "/api/sessions" && init?.method === "POST");
    expect(JSON.parse(String(start?.[1]?.body))).toMatchObject({ scenario_id: "tower" });
  });

  it("asks before changing the age mid-conversation, then starts a new session", async () => {
    const { user, fetchMock } = await openPractice();
    await say(user, "Hello");
    await screen.findByText("i want the big one");

    await user.click(screen.getByRole("combobox", { name: "Child's age" }));
    await user.click(await screen.findByRole("option", { name: "4 years (48-59 months)" }));
    const dialog = await screen.findByRole("dialog", { name: "Start a new session?" });
    await user.click(within(dialog).getByRole("button", { name: "Start new session" }));

    expect(childReplies()).toHaveLength(0);
    await say(user, "Hi again");
    await screen.findByText("yeah");
    const starts = fetchMock.mock.calls.filter(([u, init]) => String(u) === "/api/sessions" && init?.method === "POST");
    expect(starts.map(([, init]) => JSON.parse(String(init?.body)).age)).toEqual([5, 4]);
  });

  it("shows model info from /api/model-info", async () => {
    const { user } = await openPractice();
    await say(user, "Hello");
    await screen.findByText("i want the big one");
    await user.click(screen.getByRole("button", { name: "Model info" }));
    const sheet = await screen.findByRole("dialog", { name: "Model info" });
    expect(await within(sheet).findByText("example-org/mock-base-model")).toBeInTheDocument();
    expect(within(sheet).getByText("mock-run-age5")).toBeInTheDocument();
    expect(within(sheet).getByText(/Adapter for 5 years \(60-71 months\)/)).toBeInTheDocument();
    expect(within(sheet).getByText("cpu")).toBeInTheDocument();
    expect(within(sheet).getByText(/Child: 0\.42 s/)).toBeInTheDocument();
  });
});
