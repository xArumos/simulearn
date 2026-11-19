import { CircleAlert, Eye, EyeOff, LoaderCircle } from "lucide-react";
import { useId, useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router";
import { useLogin, useMe } from "@/auth";
import { Footer } from "@/components/AppShell";
import { FullPageSpinner } from "@/components/FullPageSpinner";
import { ThemeMenu } from "@/components/ThemeMenu";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Wordmark } from "@/components/Wordmark";

/** Only follow redirects to paths inside this app. */
export function safeRedirect(from: unknown): string {
  return typeof from === "string" && from.startsWith("/") && !from.startsWith("//") && from !== "/login" ? from : "/";
}

export function LoginPage() {
  const me = useMe();
  const login = useLogin();
  const navigate = useNavigate();
  const location = useLocation();
  const from = safeRedirect((location.state as { from?: unknown } | null)?.from);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const errorId = useId();

  if (me.isPending) return <FullPageSpinner />;
  if (me.data) return <Navigate to={from} replace />;

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!username.trim() || !password) return;
    login.mutate({ username: username.trim(), password }, { onSuccess: () => navigate(from, { replace: true }) });
  };

  const error = login.error?.message;

  return (
    <div className="flex min-h-dvh flex-col">
      <div className="flex justify-end px-4 pt-3 sm:px-6">
        <ThemeMenu />
      </div>
      <main className="flex flex-1 items-start justify-center px-4 pb-12 pt-6 sm:items-center sm:pt-0">
        <div className="w-full max-w-sm">
          <div className="mb-8 flex flex-col items-center gap-3 text-center">
            <Wordmark size="lg" />
            <p className="text-sm text-muted-foreground">Practice conversations with an AI child, at your own pace.</p>
          </div>

          <form
            onSubmit={onSubmit}
            noValidate
            className="grid gap-5 rounded-xl border bg-surface p-6 shadow-card sm:p-7"
            aria-describedby={error ? errorId : undefined}
          >
            <div className="grid gap-1">
              <h1 className="text-xl font-semibold tracking-tight">Sign in</h1>
              <p className="text-sm text-muted-foreground">Use the account your SimuLearn team gave you.</p>
            </div>

            {error && (
              <div
                id={errorId}
                role="alert"
                className="flex items-start gap-2 rounded-md bg-danger-soft px-3 py-2.5 text-sm text-danger-soft-foreground"
              >
                <CircleAlert className="mt-0.5 size-4 shrink-0" aria-hidden />
                <span>{error}</span>
              </div>
            )}

            <div className="grid gap-2">
              <Label htmlFor="username">Username</Label>
              <Input
                id="username"
                name="username"
                autoComplete="username"
                autoCapitalize="none"
                spellCheck={false}
                required
                autoFocus
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                aria-invalid={error ? true : undefined}
              />
            </div>

            <div className="grid gap-2">
              <Label htmlFor="password">Password</Label>
              <div className="relative">
                <Input
                  id="password"
                  name="password"
                  type={showPassword ? "text" : "password"}
                  autoComplete="current-password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  aria-invalid={error ? true : undefined}
                  className="pr-10"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((s) => !s)}
                  className="absolute inset-y-0 right-0 flex w-10 items-center justify-center rounded-r-md text-muted-foreground hover:text-foreground"
                  aria-label={showPassword ? "Hide password" : "Show password"}
                  aria-pressed={showPassword}
                >
                  {showPassword ? <EyeOff className="size-4" aria-hidden /> : <Eye className="size-4" aria-hidden />}
                </button>
              </div>
            </div>

            <Button type="submit" size="lg" disabled={login.isPending || !username.trim() || !password}>
              {login.isPending && <LoaderCircle className="animate-spin" aria-hidden />}
              {login.isPending ? "Signing in…" : "Sign in"}
            </Button>

            <p className="text-center text-xs text-muted-foreground">
              Accounts are invite-only. Forgot your password? Ask your SimuLearn administrator to reset it.
            </p>
          </form>
        </div>
      </main>
      <Footer showSaving={false} />
    </div>
  );
}
