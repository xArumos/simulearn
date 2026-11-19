import { Fragment } from "react";
import { replyParts } from "@/lib/reply";

/** A pause in a reply, shown as a subtle chip instead of the raw <SILENCE ...> tag. */
export function PauseChip({ seconds }: { seconds: number }) {
  return (
    <span className="mx-0.5 inline-flex items-center rounded-full border border-dashed px-2 py-0.5 align-baseline text-xs text-muted-foreground">
      (pauses {seconds} s)
    </span>
  );
}

/** A model reply with its pauses as chips. An empty reply reads "(no reply)". */
export function ReplyText({ text }: { text: string }) {
  const parts = replyParts(text);
  const hasWords = parts.some((p) => p.kind === "text");
  return (
    <p className="whitespace-pre-wrap break-words">
      {parts.map((p, i) => (
        <Fragment key={i}>
          {i > 0 && " "}
          {p.kind === "pause" ? <PauseChip seconds={p.seconds} /> : p.text}
        </Fragment>
      ))}
      {!hasWords && <span className="italic text-muted-foreground">(no reply)</span>}
    </p>
  );
}

/** "thinking…" (the child pauses before answering) or the waiting dots while the model works. */
export function WaitingIndicator({ thinking }: { thinking: boolean }) {
  return (
    <p className="flex items-center gap-2 text-muted-foreground" role="status">
      <span className="flex gap-1" aria-hidden>
        <span className="size-1.5 animate-pulse rounded-full bg-current" />
        <span className="size-1.5 animate-pulse rounded-full bg-current [animation-delay:150ms]" />
        <span className="size-1.5 animate-pulse rounded-full bg-current [animation-delay:300ms]" />
      </span>
      <span className="text-sm italic">{thinking ? "thinking…" : "Waiting for a reply…"}</span>
    </p>
  );
}
