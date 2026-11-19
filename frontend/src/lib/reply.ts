/**
 * Helpers for showing the model's replies.
 *
 * The child model learned CHILDES-style pauses as plain text tags, `<SILENCE FOR X SECONDS>`
 * (CLAUDE.md §7.3). The app never shows the raw tag: a pause becomes a small "(pauses X s)" chip,
 * and a pause at the start of a reply also shows a short "thinking…" indicator first, like the
 * Gradio demo (src/demo/chat_demo.py: at most 5 seconds).
 */

const SILENCE = /<SILENCE FOR (\d+) SECONDS>/g;

/** The longest "thinking…" wait before a reply that starts with a pause, in seconds. */
export const MAX_THINKING_S = 5;

export type ReplyPart = { kind: "text"; text: string } | { kind: "pause"; seconds: number };

/** Split a raw reply into text and pause parts, in order. Whitespace-only text between parts is dropped. */
export function replyParts(text: string): ReplyPart[] {
  const parts: ReplyPart[] = [];
  let last = 0;
  for (const m of text.matchAll(SILENCE)) {
    const before = text.slice(last, m.index).trim();
    if (before) parts.push({ kind: "text", text: before });
    parts.push({ kind: "pause", seconds: Number(m[1]) });
    last = (m.index ?? 0) + m[0].length;
  }
  const rest = text.slice(last).trim();
  if (rest) parts.push({ kind: "text", text: rest });
  return parts;
}

/** True when the reply has no words (empty, or only pauses). */
export function isSilentReply(text: string): boolean {
  return !replyParts(text).some((p) => p.kind === "text");
}

/** How long to show "thinking…" before a reply with a leading pause of `pauseS` seconds. */
export function thinkingDelayMs(pauseS: number | null | undefined): number {
  if (!pauseS || pauseS <= 0) return 0;
  return Math.min(pauseS, MAX_THINKING_S) * 1000;
}

export function wait(ms: number): Promise<void> {
  return ms > 0 ? new Promise((resolve) => setTimeout(resolve, ms)) : Promise.resolve();
}

/** "5 years (60-71 months)" from age 5 and the config label "60-71 months"; "5 years" without a label. */
export function ageLabel(age: number, label?: string | null): string {
  const years = `${age} ${age === 1 ? "year" : "years"}`;
  const extra = label?.trim();
  return extra ? `${years} (${extra})` : years;
}
