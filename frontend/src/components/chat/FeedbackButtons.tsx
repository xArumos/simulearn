import { useMutation } from "@tanstack/react-query";
import { ThumbsDown, ThumbsUp } from "lucide-react";
import { useId, useState } from "react";
import { api } from "@/api";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Popover, PopoverAnchor, PopoverContent } from "@/components/ui/popover";
import { Textarea } from "@/components/ui/textarea";
import { useToast } from "@/components/ui/toast";
import { cn } from "@/lib/utils";
import { SIDE_LABEL, type Side } from "./types";

interface Props {
  sessionId: string;
  turn: number;
  side: Side;
  /** From /api/config: when false, feedback is acknowledged but not stored. */
  saving: boolean;
}

/** 👍/👎 for one reply. Picking one opens a small form with an optional note; Send posts it. */
export function FeedbackButtons({ sessionId, turn, side, saving }: Props) {
  const toast = useToast();
  const noteId = useId();
  const [open, setOpen] = useState(false);
  const [liked, setLiked] = useState<boolean | null>(null);
  const [note, setNote] = useState("");
  const [sent, setSent] = useState<{ liked: boolean; saved: boolean } | null>(null);

  const send = useMutation({
    mutationFn: (l: boolean) => api.feedback({ session_id: sessionId, turn, side, liked: l, ...(note.trim() ? { note: note.trim() } : {}) }),
    onSuccess: (res, l) => {
      setSent({ liked: l, saved: saving && res?.saved !== false });
      setOpen(false);
      setNote("");
    },
    onError: (e: Error) => toast({ tone: "error", title: "Feedback not sent", description: e.message }),
  });

  const pick = (l: boolean) => {
    setLiked(l);
    setOpen(true);
  };
  const who = `${SIDE_LABEL[side]} reply, turn ${turn}`;

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverAnchor asChild>
        <div className="mt-2 flex flex-wrap items-center gap-1" role="group" aria-label={`Rate the ${who}`}>
          {[true, false].map((l) => {
            const Icon = l ? ThumbsUp : ThumbsDown;
            const chosen = (open ? liked : sent?.liked) === l;
            return (
              <Button
                key={String(l)}
                variant="ghost"
                size="icon"
                className={cn("size-7 text-muted-foreground", chosen && "bg-accent-soft text-accent-soft-foreground")}
                aria-label={l ? "Good reply" : "Not a good reply"}
                aria-pressed={chosen}
                onClick={() => pick(l)}
              >
                <Icon aria-hidden />
              </Button>
            );
          })}
          {sent && (
            <span className="text-xs text-muted-foreground" role="status">
              Thanks, feedback sent{sent.saved ? "" : " (not saved: saving is off)"}
            </span>
          )}
        </div>
      </PopoverAnchor>
      <PopoverContent aria-label={`Feedback on the ${who}`}>
        <form
          className="grid gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (liked !== null) send.mutate(liked);
          }}
        >
          <p className="text-sm font-medium">{liked ? "Good reply" : "Not a good reply"}</p>
          <Label htmlFor={noteId} className="text-xs text-muted-foreground">
            Note (optional)
          </Label>
          <Textarea
            id={noteId}
            rows={3}
            maxLength={1000}
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="What made it feel right or wrong?"
          />
          <div className="flex justify-end gap-2">
            <Button variant="ghost" size="sm" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" size="sm" disabled={send.isPending}>
              Send feedback
            </Button>
          </div>
        </form>
      </PopoverContent>
    </Popover>
  );
}
