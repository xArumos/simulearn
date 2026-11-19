import { useQuery } from "@tanstack/react-query";
import { ChevronDown, History, KeyRound, LogOut, MessagesSquare } from "lucide-react";
import { Link, NavLink, Outlet, useNavigate } from "react-router";
import { api, queryKeys } from "@/api";
import { useLogout, useMe } from "@/auth";
import { ThemeMenu } from "@/components/ThemeMenu";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useToast } from "@/components/ui/toast";
import { Wordmark } from "@/components/Wordmark";
import { cn } from "@/lib/utils";

const nav = [
  { to: "/", label: "Practice", Icon: MessagesSquare, end: true },
  { to: "/history", label: "History", Icon: History, end: false },
];

function initials(name: string) {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  return ((parts[0]?.[0] ?? "") + (parts.length > 1 ? parts[parts.length - 1][0] : "")).toUpperCase() || "?";
}

function UserMenu() {
  const me = useMe().data;
  const logout = useLogout();
  const navigate = useNavigate();
  const toast = useToast();
  if (!me) return null;

  const onLogout = () =>
    logout.mutate(undefined, {
      onSettled: (_d, err) => {
        if (err) toast({ tone: "error", title: "Couldn't reach the server", description: "You were signed out on this device." });
        navigate("/login", { replace: true });
      },
    });

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" className="gap-2 px-1.5 sm:px-2" aria-label={`Account menu for ${me.display_name}`}>
          <span className="flex size-7 items-center justify-center rounded-full bg-accent-soft text-xs font-semibold text-accent-soft-foreground">
            {initials(me.display_name || me.username)}
          </span>
          <span className="hidden max-w-[10rem] truncate sm:inline">{me.display_name || me.username}</span>
          <ChevronDown className="hidden text-muted-foreground sm:block" aria-hidden />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuLabel className="grid gap-0.5">
          <span className="truncate text-sm font-medium text-foreground">{me.display_name}</span>
          <span className="truncate">
            @{me.username}
            {me.role === "admin" ? " · admin" : ""}
          </span>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem asChild>
          <Link to="/account">
            <KeyRound aria-hidden />
            Account and password
          </Link>
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={onLogout} disabled={logout.isPending}>
          <LogOut aria-hidden />
          Log out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function TopBar() {
  return (
    <header className="sticky top-0 z-40 border-b bg-surface/85 backdrop-blur supports-[backdrop-filter]:bg-surface/70">
      <div className="mx-auto flex h-14 max-w-6xl items-center gap-2 px-4 sm:gap-4 sm:px-6">
        <Link to="/" className="rounded-md" aria-label="SimuLearn home">
          <Wordmark />
        </Link>
        <nav aria-label="Main" className="ml-1 flex items-center gap-1 sm:ml-4">
          {nav.map(({ to, label, Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                cn(
                  "inline-flex h-9 items-center gap-2 rounded-md px-2.5 text-sm font-medium transition-colors",
                  isActive ? "bg-accent-soft text-accent-soft-foreground" : "text-muted-foreground hover:bg-surface-muted hover:text-foreground",
                )
              }
            >
              <Icon className="size-4" aria-hidden />
              <span className="sr-only sm:not-sr-only">{label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="ml-auto flex items-center gap-1">
          <ThemeMenu />
          <UserMenu />
        </div>
      </div>
    </header>
  );
}

/** Privacy reminder, saving status and the data citation. */
export function Footer({ showSaving = true }: { showSaving?: boolean }) {
  const me = useMe().data;
  const config = useQuery({ queryKey: queryKeys.config, queryFn: api.config, enabled: showSaving && !!me, retry: false });
  const saving = config.data?.saving;

  return (
    <footer className="border-t bg-surface-muted/60">
      <div className="mx-auto grid max-w-6xl gap-2 px-4 py-5 text-xs leading-relaxed text-muted-foreground sm:px-6">
        <p className="font-medium text-foreground">
          Please don't type real names or details about real children. This is a practice tool.
        </p>
        {showSaving && me && (
          <p data-testid="saving-status">
            {saving === undefined
              ? "Checking whether conversations are saved…"
              : saving
                ? "Saving is on: your practice conversations are stored so you can review them in History."
                : "Saving is off: conversations are not stored and disappear when the server restarts."}
          </p>
        )}
        <p>
          The AI child was trained on transcripts from the CHILDES database: MacWhinney, B. (2000).{" "}
          <cite>The CHILDES Project: Tools for Analyzing Talk</cite> (3rd ed.). Lawrence Erlbaum Associates. Data used
          under CC BY-NC-SA.
        </p>
      </div>
    </footer>
  );
}

export function AppShell() {
  return (
    <div className="flex min-h-dvh flex-col">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-3 focus:z-50 focus:rounded-md focus:bg-surface focus:px-3 focus:py-2 focus:shadow-pop"
      >
        Skip to content
      </a>
      <TopBar />
      <main id="main" className="mx-auto w-full max-w-6xl flex-1 px-4 py-8 sm:px-6">
        <Outlet />
      </main>
      <Footer />
    </div>
  );
}
