import { useQuery } from "@tanstack/react-query";
import { ChevronRight, History, MessagesSquare } from "lucide-react";
import { Link } from "react-router";
import { api, queryKeys, type SessionSummary } from "@/api";
import { FullPageSpinner } from "@/components/FullPageSpinner";
import { EmptyState, PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/button";
import { ageLabel } from "@/lib/reply";

/** How many past sessions the list asks for (the server allows 1-200). */
export const HISTORY_LIMIT = 100;

/** "Nov 19, 2026, 2:03 PM" in the viewer's locale and time zone. */
export function formatWhen(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

export const turnsText = (n: number) => `${n} ${n === 1 ? "turn" : "turns"}`;

/** The History screen (route `/history`): the user's past practice sessions, newest first. */
export function HistoryPage() {
  const sessions = useQuery({ queryKey: queryKeys.sessions, queryFn: () => api.sessions(HISTORY_LIMIT) });
  // Only for the age labels and the "saving is off" note; the list does not wait for it.
  const config = useQuery({ queryKey: queryKeys.config, queryFn: api.config });
  const labels = config.data?.age_labels ?? {};

  return (
    <>
      <PageHeader title="History" description="Your past practice conversations. Open one to read it again or download it." />
      {config.data && !config.data.saving && (
        <p className="mb-4 rounded-lg border border-dashed bg-surface-muted/60 px-4 py-3 text-sm text-muted-foreground" role="note">
          Saving is off on this server, so only conversations since it last started are listed, and they are lost when it
          restarts.
        </p>
      )}
      {sessions.isPending && <FullPageSpinner />}
      {sessions.isError && (
        <EmptyState icon={<History aria-hidden />} title="Couldn't load your history">
          <p>{sessions.error.message}</p>
          <Button variant="secondary" className="mt-3" onClick={() => sessions.refetch()}>
            Try again
          </Button>
        </EmptyState>
      )}
      {sessions.data &&
        (sessions.data.length === 0 ? (
          <EmptyState icon={<History aria-hidden />} title="Nothing here yet">
            <p>Your practice conversations will appear here, ready to reopen or download.</p>
            <Button asChild className="mt-3">
              <Link to="/">
                <MessagesSquare aria-hidden />
                Start practicing
              </Link>
            </Button>
          </EmptyState>
        ) : (
          <ul className="grid gap-2" aria-label="Past sessions">
            {sessions.data.map((s) => (
              <SessionRow key={s.id} s={s} ageText={ageLabel(s.age, labels[String(s.age)])} />
            ))}
          </ul>
        ))}
    </>
  );
}

function SessionRow({ s, ageText }: { s: SessionSummary; ageText: string }) {
  const title = s.scenario_title ?? "Free conversation";
  return (
    <li>
      <Link
        to={`/history/${encodeURIComponent(s.id)}`}
        aria-label={`${title}, ${formatWhen(s.created_at)}`}
        className="flex items-center gap-4 rounded-xl border bg-surface px-4 py-3 shadow-card transition-colors hover:bg-surface-muted focus-visible:outline-2 focus-visible:outline-accent"
      >
        <div className="grid min-w-0 flex-1 gap-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="truncate font-medium">{title}</span>
            {s.compare && (
              <span className="rounded-full bg-accent-soft px-2 py-0.5 text-xs font-medium text-accent-soft-foreground">
                Compared
              </span>
            )}
          </div>
          <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-sm text-muted-foreground">
            <time dateTime={s.created_at}>{formatWhen(s.created_at)}</time>
            <span>Age {ageText}</span>
            <span>{turnsText(s.turns)}</span>
          </div>
        </div>
        <ChevronRight className="size-4 shrink-0 text-muted-foreground" aria-hidden />
      </Link>
    </li>
  );
}
