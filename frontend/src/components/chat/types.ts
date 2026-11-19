import type { Rating, TurnReply } from "@/api";

export type Side = "child" | "untrained";

export const SIDE_LABEL: Record<Side, string> = { child: "Child", untrained: "Untrained AI" };

/** One model reply as it moves from "asked" to "shown". */
export type ReplyState =
  | { status: "pending" }
  /** The reply arrived and starts with a pause: show "thinking…" for a moment first. */
  | { status: "thinking"; reply: TurnReply }
  | { status: "done"; reply: TurnReply }
  | { status: "error"; message: string };

/** One exchange: the educator's line and the replies to it. */
export interface ChatTurn {
  /** Stable React key. */
  key: string;
  /** The turn number (1, 2, ...), as the server numbers the child side. */
  turn: number;
  adult: string;
  child: ReplyState;
  /** null when the untrained model was not asked for this turn. */
  untrained: ReplyState | null;
  /** Saved ratings per side, shown in a read-only (reopened) conversation. */
  ratings?: Partial<Record<Side, Rating | null>>;
}
