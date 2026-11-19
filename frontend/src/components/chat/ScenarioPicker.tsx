import { Check } from "lucide-react";
import type { Scenario } from "@/api";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  scenarios: Scenario[];
  current: string | null;
  /** Picking a scene mid-conversation starts a new one; the dialog says so. */
  startsNew: boolean;
  onPick: (id: string | null) => void;
}

/** The practice scenes from /api/config, plus "Free conversation". */
export function ScenarioPicker({ open, onOpenChange, scenarios, current, startsNew, onPick }: Props) {
  const options = [
    { id: null, title: "Free conversation", scene: "No set scene: start with anything you like." },
    ...scenarios.map((s) => ({ id: s.id as string | null, title: s.title, scene: s.scene })),
  ];
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90dvh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Choose a scene</DialogTitle>
          <DialogDescription>
            A scene sets the situation for you and suggests an opening line. The AI child is not told the scene.
            {startsNew && " Picking one starts a new conversation."}
          </DialogDescription>
        </DialogHeader>
        <ul className="grid gap-2">
          {options.map((o) => {
            const selected = o.id === current;
            return (
              <li key={o.id ?? "free"}>
                <button
                  type="button"
                  aria-pressed={selected}
                  onClick={() => onPick(o.id)}
                  className={cn(
                    "flex w-full items-start gap-3 rounded-lg border px-4 py-3 text-left transition-colors hover:bg-surface-muted",
                    selected && "border-accent bg-accent-soft hover:bg-accent-soft",
                  )}
                >
                  <span className="grid flex-1 gap-0.5">
                    <span className="text-sm font-medium">{o.title}</span>
                    <span className="text-sm text-muted-foreground">{o.scene}</span>
                  </span>
                  {selected && <Check className="mt-0.5 size-4 shrink-0 text-accent" aria-hidden />}
                </button>
              </li>
            );
          })}
        </ul>
      </DialogContent>
    </Dialog>
  );
}
