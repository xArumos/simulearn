import { useMutation, useQuery } from "@tanstack/react-query";
import { ArrowLeft, Download, History, Lock, RotateCcw } from "lucide-react";
import { Link, useNavigate, useParams } from "react-router";
import { api, ApiError, queryKeys, type ExportFormat, type SessionDetail, type SessionReply } from "@/api";
import { ChatLog } from "@/components/chat/ChatLog";
import type { ChatTurn, ReplyState } from "@/components/chat/types";
import { FullPageSpinner } from "@/components/FullPageSpinner";
import { EmptyState, PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import { saveFile } from "@/lib/download";
import { ageLabel } from "@/lib/reply";
import { formatWhen, turnsText } from "@/pages/History";
import type { PracticeStart } from "@/pages/Practice";

const done = (r: SessionReply, turn: number): ReplyState => ({
  status: "done",
  reply: { turn, text: r.text, rendered: r.text, pause_s: r.pause_s, secs: r.secs ?? 0 },
});

/** A reopened session as chat turns, plus the turns where the comparison (re)started. */
export function sessionTurns(d: SessionDetail): { turns: ChatTurn[]; compare: boolean; compareStarts: number[] } {
  const turns: ChatTurn[] = d.exchanges.map((ex) => ({
    key: `t${ex.turn}`,
    turn: ex.turn,
    adult: ex.adult,
    child: done(ex.child, ex.turn),
    untrained: ex.untrained ? done(ex.untrained, ex.turn) : null,
    ratings: { child: ex.child.rating, untrained: ex.untrained?.rating ?? null },
  }));
  // A comparison starts at each compared turn that follows an uncompared one (or opens the session).
  const compareStarts = d.exchanges
    .filter((ex, i) => ex.untrained && (i === 0 || !d.exchanges[i - 1].untrained))
    .map((ex) => ex.turn);
  return { turns, compare: compareStarts.length > 0, compareStarts };
}

/** A past session (route `/history/:sessionId`): read-only, with its ratings, exports and "practice again". */
export function SessionViewPage() {
  const { sessionId = "" } = useParams();
  const session = useQuery({ queryKey: queryKeys.session(sessionId), queryFn: () => api.session(sessionId) });
  const config = useQuery({ queryKey: queryKeys.config, queryFn: api.config });

  return (
    <>
      <Button asChild variant="link" size="sm" className="mb-2 h-auto px-0">
        <Link to="/history">
          <ArrowLeft aria-hidden />
          All sessions
        </Link>
      </Button>
      {session.isPending && <FullPageSpinner />}
      {session.isError && (
        <EmptyState
          icon={<History aria-hidden />}
          title={session.error instanceof ApiError && session.error.status === 404 ? "Session not found" : "Couldn't load this session"}
        >
          <p>
            {session.error instanceof ApiError && session.error.status === 404
              ? "It may belong to another account, or the server lost it on a restart (when saving is off)."
              : session.error.message}
          </p>
          {!(session.error instanceof ApiError && session.error.status === 404) && (
            <Button variant="secondary" className="mt-3" onClick={() => session.refetch()}>
              Try again
            </Button>
          )}
        </EmptyState>
      )}
      {session.data && <SessionView d={session.data} saving={config.data?.saving ?? false} />}
    </>
  );
}

function SessionView({ d, saving }: { d: SessionDetail; saving: boolean }) {
  const navigate = useNavigate();
  const toast = useToast();
  const { turns, compare, compareStarts } = sessionTurns(d);
  const title = d.scenario_title ?? "Free conversation";

  const download = useMutation({
    mutationFn: (format: ExportFormat) => api.exportSession(d.id, format),
    onSuccess: (f) => saveFile(f.blob, f.filename),
    onError: (e: Error) => toast({ tone: "error", title: "Download failed", description: e.message }),
  });

  const practiceAgain = () => {
    const state: PracticeStart = { age: d.age, scenarioId: d.scenario_id };
    navigate("/", { state });
  };

  return (
    <>
      <PageHeader
        title={title}
        description={
          <>
            <time dateTime={d.created_at}>{formatWhen(d.created_at)}</time> · Age {ageLabel(d.age, d.age_label)} ·{" "}
            {turnsText(d.turns)}
            {compare && " · Compared with the untrained AI"}
          </>
        }
        actions={
          <div className="flex flex-wrap gap-2">
            {(["txt", "json"] as const).map((f) => (
              <Button
                key={f}
                variant="secondary"
                disabled={download.isPending}
                onClick={() => download.mutate(f)}
                aria-label={`Download as .${f}`}
              >
                <Download aria-hidden />.{f}
              </Button>
            ))}
            <Button onClick={practiceAgain}>
              <RotateCcw aria-hidden />
              {d.scenario_id ? "Practice again with this scenario" : "Practice again at this age"}
            </Button>
          </div>
        }
      />
      <div className="grid gap-4 rounded-xl border bg-surface p-3 shadow-card sm:p-5">
        <p className="flex items-center gap-2 text-sm text-muted-foreground" role="note">
          <Lock className="size-4 shrink-0" aria-hidden />
          This conversation has ended. You can read it and download it, but not continue it.
        </p>
        {turns.length === 0 ? (
          <p className="py-8 text-center text-sm text-muted-foreground">Nothing was said in this session.</p>
        ) : (
          <ChatLog turns={turns} compare={compare} compareStarts={compareStarts} sessionId={d.id} saving={saving} readOnly />
        )}
      </div>
    </>
  );
}
