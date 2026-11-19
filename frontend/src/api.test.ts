import { describe, expect, it, vi } from "vitest";
import { api, ApiError, errorMessage, filenameFromDisposition } from "@/api";

describe("filenameFromDisposition", () => {
  it("reads quoted, bare and RFC 5987 file names", () => {
    expect(filenameFromDisposition('attachment; filename="simulearn-20261119-1403-age5-abc.txt"')).toBe(
      "simulearn-20261119-1403-age5-abc.txt",
    );
    expect(filenameFromDisposition("attachment; filename=session.json")).toBe("session.json");
    expect(filenameFromDisposition("attachment; filename*=UTF-8''s%C3%A9ance.txt")).toBe("séance.txt");
  });
  it("returns null without a name", () => {
    expect(filenameFromDisposition(null)).toBeNull();
    expect(filenameFromDisposition("attachment")).toBeNull();
  });
});

describe("errorMessage", () => {
  it("uses FastAPI's string detail", () => {
    expect(errorMessage({ detail: "Nope" }, 400)).toBe("Nope");
  });
  it("uses the first validation message", () => {
    expect(errorMessage({ detail: [{ msg: "field required" }] }, 422)).toBe("field required");
  });
  it("falls back to a plain sentence", () => {
    expect(errorMessage(null, 500)).toMatch(/server had a problem/);
    expect(errorMessage("", 404)).toBe("Request failed (404).");
  });
});

describe("api client", () => {
  it("returns null from me() on 401", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ detail: "x" }), { status: 401 })));
    await expect(api.me()).resolves.toBeNull();
  });

  it("throws ApiError with status for other failures", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ detail: "boom" }), { status: 500 })));
    const err = await api.me().catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).status).toBe(500);
    expect((err as ApiError).message).toBe("boom");
  });

  it("reports a network failure in plain words", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => Promise.reject(new TypeError("Failed to fetch"))));
    await expect(api.login("a", "b")).rejects.toMatchObject({ status: 0, message: expect.stringMatching(/Can't reach/) });
  });

  it("only talks to same-origin /api paths", async () => {
    const f = vi.fn(async () => new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", f);
    await api.login("a", "b");
    await api.logout();
    await api.changePassword("a", "b");
    await api.config();
    for (const [url, init] of f.mock.calls as unknown as [string, RequestInit][]) {
      expect(url.startsWith("/api/")).toBe(true);
      expect(init.credentials).toBe("same-origin");
    }
  });
});
