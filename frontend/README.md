# SimuLearn product frontend

The educator-facing web app: React + Vite + TypeScript, Tailwind CSS, Radix UI primitives and TanStack Query.
It talks only to the product API under `/api` (`src/product/server.py`). Fonts are bundled
(`@fontsource-variable/inter`), so the built app loads nothing from other hosts.

Needs Node.js 26 (issue #56). In a non-interactive shell, load nvm first:
`export NVM_DIR="$HOME/.nvm"; source "$NVM_DIR/nvm.sh"`.

| Command (inside `frontend/`) | What it does |
|---|---|
| `npm ci` | Install the exact versions in `package-lock.json` |
| `npm run dev` | Dev server on http://127.0.0.1:5173, proxying `/api` to the product server on `127.0.0.1:8000` |
| `MOCK_API=1 npm run dev` | Dev server with an in-memory fake API (`mock/mockApi.ts`); sign in as `demo` / `practice-only` |
| `npm test` | Unit and component tests (Vitest + Testing Library, mocked API) |
| `npm run typecheck` | TypeScript check |
| `npm run build` | Production build into `frontend/dist` (git-ignored) |
| `npm run check:dist` | Fail if the build references any other host |

`bash scripts/build_frontend.sh` (from the repo root) runs install, build and the host check in one go.

## Layout

- `src/api.ts`: typed API client (auth routes from #55, sessions from #58, feedback/history from #59).
- `src/auth.tsx`: `useMe`, `useLogin`, `useLogout` and the `RequireAuth` route guard.
- `src/components/ui/`: shadcn-style components on Radix (button, input, label, select, switch, dialog,
  sheet, dropdown menu, toast, tooltip). Copy-and-own: edit them here.
- `src/index.css`: design tokens. Colours are CSS variables on `:root` and `:root[data-theme="dark"]`;
  components use the Tailwind names (`bg-surface`, `text-muted-foreground`, `bg-accent`...), never raw colours.
- `src/lib/theme.tsx`: light/dark theme that follows the OS, with a manual override saved in the browser.
- `src/pages/`: Login, Practice (#61), History (#62), Account (change password).
