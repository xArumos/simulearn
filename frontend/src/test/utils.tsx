import { render } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router";
import { vi } from "vitest";
import { createMockApi, type MockApiOptions } from "../../mock/mockApi";
import { AppRoutes, makeQueryClient, Providers } from "@/App";

/**
 * Replace `fetch` with the in-memory mock API. A tiny cookie jar plays the
 * browser's part: it stores the httpOnly session cookie the server sets and
 * sends it back, so app code never touches the token (as in production).
 */
export function installMockApi(opts: MockApiOptions = {}) {
  const api = createMockApi(opts);
  const jar: { token: string | null } = { token: null };
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input), "http://localhost");
    const raw = init?.body;
    const out = api.handle({
      method: (init?.method ?? "GET").toUpperCase(),
      path: url.pathname,
      body: typeof raw === "string" ? JSON.parse(raw) : undefined,
      token: jar.token,
    });
    if (out.setCookie) jar.token = out.setCookie.value;
    return new Response(out.body === undefined ? null : JSON.stringify(out.body), {
      status: out.status,
      headers: { "Content-Type": "application/json" },
    });
  });
  vi.stubGlobal("fetch", fetchMock);
  return { api, jar, fetchMock };
}

export function LocationProbe() {
  const loc = useLocation();
  return <div data-testid="location">{loc.pathname}</div>;
}

export function renderApp(path = "/") {
  const client = makeQueryClient();
  client.setDefaultOptions({ queries: { retry: false, refetchOnWindowFocus: false }, mutations: { retry: false } });
  const utils = render(
    <MemoryRouter initialEntries={[path]}>
      <Providers client={client}>
        <AppRoutes />
        <LocationProbe />
      </Providers>
    </MemoryRouter>,
  );
  return { ...utils, client };
}
