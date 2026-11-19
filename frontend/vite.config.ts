import { fileURLToPath, URL } from "node:url";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";
import { mockApiPlugin } from "./mock/vitePlugin.ts";

// MOCK_API=1 npm run dev serves a fake /api from memory (see mock/mockApi.ts),
// so the UI can be worked on without the Python server or a GPU.
const useMock = process.env.MOCK_API === "1";

export default defineConfig({
  plugins: [react(), tailwindcss(), ...(useMock ? [mockApiPlugin()] : [])],
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  server: {
    host: "127.0.0.1",
    port: 5173,
    // The product API (src/product/server.py) listens here in development.
    proxy: useMock ? undefined : { "/api": "http://127.0.0.1:8000" },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    css: false,
    restoreMocks: true,
  },
});
