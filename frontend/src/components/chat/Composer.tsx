import { SendHorizontal } from "lucide-react";
import { useEffect, useRef, type KeyboardEvent } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

/** The server rejects longer lines (src/product/server.py MAX_LINE). */
export const MAX_LINE = 2000;

interface Props {
  value: string;
  onChange: (v: string) => void;
  onSend: () => void;
  /** Replies are pending: the input is disabled. */
  busy: boolean;
}

/** The educator's input. Enter sends; Shift+Enter makes a new line. */
export function Composer({ value, onChange, onSend, busy }: Props) {
  const ref = useRef<HTMLTextAreaElement>(null);
  const wasBusy = useRef(false);
  useEffect(() => {
    // Put the cursor back in the box once the replies are in (the disabled box lost focus).
    if (wasBusy.current && !busy) ref.current?.focus();
    wasBusy.current = busy;
  }, [busy]);

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      if (value.trim() && !busy) onSend();
    }
  };

  return (
    <form
      className="flex items-end gap-2"
      onSubmit={(e) => {
        e.preventDefault();
        if (value.trim() && !busy) onSend();
      }}
    >
      <label htmlFor="practice-input" className="sr-only">
        What you say to the child
      </label>
      <Textarea
        ref={ref}
        id="practice-input"
        rows={2}
        maxLength={MAX_LINE}
        value={value}
        disabled={busy}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={onKeyDown}
        placeholder={busy ? "Waiting for the reply…" : "Say something to the child…"}
        aria-describedby="practice-input-hint"
        className="min-h-[2.75rem]"
      />
      <Button type="submit" size="lg" disabled={busy || !value.trim()} aria-label="Send">
        <SendHorizontal aria-hidden />
        <span className="hidden sm:inline">Send</span>
      </Button>
      <p id="practice-input-hint" className="sr-only">
        Press Enter to send, Shift+Enter for a new line.
      </p>
    </form>
  );
}
