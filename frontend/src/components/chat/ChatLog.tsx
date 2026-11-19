import { ThumbsDown, ThumbsUp } from "lucide-react";
import { useEffect, useRef } from "react";
import type { Rating } from "@/api";
import { cn } from "@/lib/utils";
import { FeedbackButtons } from "./FeedbackButtons";
import { ReplyText, WaitingIndicator } from "./ReplyText";
import { SIDE_LABEL, type ChatTurn, type ReplyState, type Side } from "./types";

interface Props {
  turns: ChatTurn[];
  /** Show the "Untrained AI" column (compare is on). */
  compare: boolean;
  /** Turn numbers before which compare was switched on mid-session. */
  compareStarts: number[];
  sessionId: string | null;
  saving: boolean;
  /** A reopened conversation: no feedback buttons (saved ratings are shown instead), no auto-scroll. */
  readOnly?: boolean;
}

/** A saved rating in a reopened conversation: thumbs up/down and the note, if any. */
function SavedRating({ rating }: { rating: Rating }) {
  const Icon = rating.liked ? ThumbsUp : ThumbsDown;
  return (
    <p className="mt-2 flex items-start gap-1.5 text-xs text-muted-foreground">
      <Icon className="mt-0.5 size-3.5 shrink-0" aria-hidden />
      <span>
        {rating.liked ? "You rated this a good reply" : "You rated this not a good reply"}
        {rating.note && <span className="text-foreground">: {rating.note}</span>}
      </span>
    </p>
  );
}

function ReplyCard({ side, state, turn, sessionId, saving, labelled, readOnly, rating }: {
  side: Side;
  state: ReplyState;
  turn: number;
  sessionId: string | null;
  saving: boolean;
  labelled: boolean;
  readOnly: boolean;
  rating: Rating | null | undefined;
}) {
  return (
    <section
      aria-label={`${SIDE_LABEL[side]} reply`}
      data-side={side}
      className={cn(
        "min-w-0 rounded-xl border px-4 py-3 text-sm leading-relaxed",
        side === "child" ? "border-accent/25 bg-accent-soft/60" : "bg-surface-muted",
      )}
    >
      <p
        className={cn(
          "mb-1 text-xs font-semibold uppercase tracking-wide",
          side === "child" ? "text-accent-soft-foreground" : "text-muted-foreground",
          !labelled && "sr-only",
        )}
      >
        {SIDE_LABEL[side]}
      </p>
      {state.status === "pending" && <WaitingIndicator thinking={false} />}
      {state.status === "thinking" && <WaitingIndicator thinking />}
      {state.status === "error" && <p className="text-danger">{state.message}</p>}
      {state.status === "done" && (
        <>
          <ReplyText text={state.reply.text} />
          {readOnly
            ? rating && <SavedRating rating={rating} />
            : sessionId && <FeedbackButtons sessionId={sessionId} turn={turn} side={side} saving={saving} />}
        </>
      )}
    </section>
  );
}

function CompareDivider() {
  return (
    <div className="flex items-center gap-3 text-xs font-medium text-muted-foreground" role="separator" aria-label="Comparison started here">
      <span className="h-px flex-1 bg-border" />
      Comparison started here
      <span className="h-px flex-1 bg-border" />
    </div>
  );
}

/** The conversation: each educator line with the child's reply (and the untrained model's beside it). */
export function ChatLog({ turns, compare, compareStarts, sessionId, saving, readOnly = false }: Props) {
  const end = useRef<HTMLDivElement>(null);
  const last = turns[turns.length - 1];
  const lastState = last ? `${turns.length}:${last.child.status}:${last.untrained?.status ?? ""}` : "";
  useEffect(() => {
    if (!readOnly) end.current?.scrollIntoView?.({ block: "end", behavior: "smooth" });
  }, [lastState, readOnly]);

  const lastTurnNo = turns.reduce((n, t) => Math.max(n, t.turn), 0);
  const trailingDivider = compare && compareStarts.some((n) => n > lastTurnNo);

  return (
    <div role="log" aria-label="Conversation" aria-live={readOnly ? "off" : "polite"} className="grid gap-5">
      {turns.map((t) => (
        <div key={t.key} className="grid gap-3">
          {compare && t.turn > 1 && compareStarts.includes(t.turn) && <CompareDivider />}
          <div className="flex justify-end">
            <div className="max-w-[85%] rounded-xl bg-accent px-4 py-2.5 text-sm leading-relaxed text-accent-foreground sm:max-w-[70%]">
              <p className="sr-only">You said:</p>
              <p className="whitespace-pre-wrap break-words">{t.adult}</p>
            </div>
          </div>
          <div className={cn("grid gap-3", compare && "md:grid-cols-2")}>
            <ReplyCard
              side="child"
              state={t.child}
              turn={t.turn}
              sessionId={sessionId}
              saving={saving}
              labelled={compare}
              readOnly={readOnly}
              rating={t.ratings?.child}
            />
            {compare &&
              (t.untrained ? (
                <ReplyCard
                  side="untrained"
                  state={t.untrained}
                  turn={t.turn}
                  sessionId={sessionId}
                  saving={saving}
                  labelled
                  readOnly={readOnly}
                  rating={t.ratings?.untrained}
                />
              ) : (
                <p className="hidden self-center text-center text-xs text-muted-foreground md:block">Not compared</p>
              ))}
          </div>
        </div>
      ))}
      {trailingDivider && turns.length > 0 && <CompareDivider />}
      <div ref={end} />
    </div>
  );
}
