import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { installMockApi, renderApp } from "@/test/utils";
import { safeRedirect } from "@/pages/Login";

async function signIn(username = "demo", password = "practice-only") {
  const user = userEvent.setup();
  await user.type(await screen.findByLabelText("Username"), username);
  await user.type(screen.getByLabelText("Password"), password);
  await user.click(screen.getByRole("button", { name: "Sign in" }));
  return user;
}

describe("login flow", () => {
  it("redirects a logged-out user to /login", async () => {
    installMockApi();
    renderApp("/");
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
    expect(screen.getByTestId("location")).toHaveTextContent("/login");
  });

  it("protects every app route", async () => {
    for (const path of ["/history", "/account"]) {
      installMockApi();
      const { unmount } = renderApp(path);
      await screen.findByRole("heading", { name: "Sign in" });
      expect(screen.getByTestId("location")).toHaveTextContent("/login");
      unmount();
    }
  });

  it("signs in, sends the right body, and shows the app shell", async () => {
    const { fetchMock, jar } = installMockApi();
    renderApp("/");
    await signIn();
    expect(await screen.findByRole("heading", { name: "Welcome, Demo" })).toBeInTheDocument();
    expect(screen.getByTestId("location")).toHaveTextContent(/^\/$/);
    expect(jar.token).toBeTruthy();

    const loginCall = fetchMock.mock.calls.find(([u]) => String(u) === "/api/auth/login");
    expect(loginCall?.[1]?.method).toBe("POST");
    expect(JSON.parse(String(loginCall?.[1]?.body))).toEqual({ username: "demo", password: "practice-only" });

    // Top bar: wordmark link, nav, user menu.
    expect(screen.getByRole("link", { name: "SimuLearn home" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "History" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Account menu for Demo Educator/ })).toBeInTheDocument();
  });

  it("returns to the page the user first asked for", async () => {
    installMockApi();
    renderApp("/history");
    await signIn();
    expect(await screen.findByRole("heading", { name: "History" })).toBeInTheDocument();
    expect(screen.getByTestId("location")).toHaveTextContent("/history");
  });

  it("shows the server's error for a wrong password and stays on /login", async () => {
    installMockApi();
    renderApp("/login");
    await signIn("demo", "wrong-password");
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Incorrect username or password");
    expect(screen.getByLabelText("Password")).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByTestId("location")).toHaveTextContent("/login");
  });

  it("explains rate limiting (429) in plain words", async () => {
    const { fetchMock } = installMockApi();
    fetchMock.mockImplementationOnce(async () => new Response(JSON.stringify({ detail: "Not logged in" }), { status: 401 }));
    fetchMock.mockImplementationOnce(async () => new Response("", { status: 429 }));
    renderApp("/login");
    await signIn();
    expect(await screen.findByRole("alert")).toHaveTextContent(/Too many attempts/);
  });

  it("skips the login page when already signed in", async () => {
    const { api, jar } = installMockApi();
    jar.token = (api.handle({ method: "POST", path: "/api/auth/login", body: { username: "demo", password: "practice-only" } })
      .setCookie?.value ?? null);
    renderApp("/login");
    expect(await screen.findByRole("heading", { name: "Welcome, Demo" })).toBeInTheDocument();
  });

  it("logs out: calls the API, clears the cookie, and returns to /login", async () => {
    const { fetchMock, jar, api } = installMockApi();
    renderApp("/");
    const user = await signIn();
    const token = jar.token;
    await user.click(await screen.findByRole("button", { name: /Account menu/ }));
    await user.click(await screen.findByRole("menuitem", { name: "Log out" }));

    await screen.findByRole("heading", { name: "Sign in" });
    expect(screen.getByTestId("location")).toHaveTextContent("/login");
    expect(fetchMock.mock.calls.some(([u, init]) => String(u) === "/api/auth/logout" && init?.method === "POST")).toBe(true);
    expect(jar.token).toBeNull();
    expect(api.sessions.has(String(token))).toBe(false);
  });
});

describe("footer", () => {
  it("shows the privacy reminder, saving status and the CHILDES citation", async () => {
    installMockApi({ saving: true });
    renderApp("/");
    await signIn();
    const footer = await screen.findByRole("contentinfo");
    expect(within(footer).getByText(/don't type real names or details about real children/)).toBeInTheDocument();
    expect(within(footer).getByText(/MacWhinney/)).toBeInTheDocument();
    await waitFor(() => expect(within(footer).getByTestId("saving-status")).toHaveTextContent("Saving is on"));
  });

  it("says when saving is off", async () => {
    installMockApi({ saving: false });
    renderApp("/");
    await signIn();
    await waitFor(() => expect(screen.getByTestId("saving-status")).toHaveTextContent("Saving is off"));
  });
});

describe("safeRedirect", () => {
  it("only allows in-app paths", () => {
    expect(safeRedirect("/history")).toBe("/history");
    expect(safeRedirect("//evil.example")).toBe("/");
    expect(safeRedirect("https://evil.example")).toBe("/");
    expect(safeRedirect("/login")).toBe("/");
    expect(safeRedirect(undefined)).toBe("/");
  });
});
