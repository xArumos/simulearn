import type { Plugin } from "vite";
import { createMockApi, MOCK_COOKIE } from "./mockApi.ts";

/** Serves the in-memory mock API on the Vite dev server (MOCK_API=1 only). */
export function mockApiPlugin(): Plugin {
  const api = createMockApi();
  return {
    name: "simulearn-mock-api",
    apply: "serve",
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        const url = req.url ?? "";
        if (!url.startsWith("/api/")) return next();
        let raw = "";
        req.on("data", (chunk) => (raw += chunk));
        req.on("end", () => {
          const cookie = req.headers.cookie ?? "";
          const token = new RegExp(`${MOCK_COOKIE}=([^;]+)`).exec(cookie)?.[1] ?? null;
          let body: unknown;
          try {
            body = raw ? JSON.parse(raw) : undefined;
          } catch {
            body = undefined;
          }
          const out = api.handle({ method: req.method ?? "GET", path: url.split("?")[0], body, token });
          if (out.setCookie) {
            const v = out.setCookie.value;
            res.setHeader(
              "Set-Cookie",
              v === null
                ? `${MOCK_COOKIE}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0`
                : `${MOCK_COOKIE}=${v}; Path=/; HttpOnly; SameSite=Lax`,
            );
          }
          res.statusCode = out.status;
          res.setHeader("Content-Type", "application/json");
          res.end(JSON.stringify(out.body ?? null));
        });
      });
    },
  };
}
