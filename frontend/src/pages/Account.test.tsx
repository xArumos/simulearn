import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { installMockApi, renderApp } from "@/test/utils";

async function signedInAt(path: string) {
  const mock = installMockApi();
  mock.jar.token =
    mock.api.handle({ method: "POST", path: "/api/auth/login", body: { username: "demo", password: "practice-only" } }).setCookie
      ?.value ?? null;
  renderApp(path);
  await screen.findByRole("heading", { name: "Account" });
  return { ...mock, user: userEvent.setup() };
}

describe("account page", () => {
  it("changes the password through POST /api/me/password", async () => {
    const { user, fetchMock, api } = await signedInAt("/account");
    await user.type(screen.getByLabelText("Current password"), "practice-only");
    await user.type(screen.getByLabelText("New password"), "a-new-passphrase");
    await user.type(screen.getByLabelText("Confirm new password"), "a-new-passphrase");
    await user.click(screen.getByRole("button", { name: "Update password" }));

    expect(await screen.findByText("Password changed")).toBeInTheDocument();
    const call = fetchMock.mock.calls.find(([u]) => String(u) === "/api/me/password");
    expect(JSON.parse(String(call?.[1]?.body))).toEqual({
      current_password: "practice-only",
      new_password: "a-new-passphrase",
    });
    // The mock now accepts the new password.
    expect(api.handle({ method: "POST", path: "/api/auth/login", body: { username: "demo", password: "a-new-passphrase" } }).status).toBe(200);
    expect(screen.getByLabelText("Current password")).toHaveValue("");
  });

  it("catches mismatched new passwords before calling the server", async () => {
    const { user, fetchMock } = await signedInAt("/account");
    await user.type(screen.getByLabelText("Current password"), "practice-only");
    await user.type(screen.getByLabelText("New password"), "one-passphrase");
    await user.type(screen.getByLabelText("Confirm new password"), "another-passphrase");
    await user.click(screen.getByRole("button", { name: "Update password" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("don't match");
    expect(fetchMock.mock.calls.some(([u]) => String(u) === "/api/me/password")).toBe(false);
  });

  it("shows the server's message for a wrong current password", async () => {
    const { user } = await signedInAt("/account");
    await user.type(screen.getByLabelText("Current password"), "not-it");
    await user.type(screen.getByLabelText("New password"), "a-new-passphrase");
    await user.type(screen.getByLabelText("Confirm new password"), "a-new-passphrase");
    await user.click(screen.getByRole("button", { name: "Update password" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Current password is incorrect");
  });
});
