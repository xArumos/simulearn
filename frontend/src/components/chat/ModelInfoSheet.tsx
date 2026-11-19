import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { api, queryKeys } from "@/api";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  age: number;
  ageText: string;
  /** Generation seconds of the latest replies, when there are any. */
  lastSecs: { child?: number; untrained?: number };
}

function Row({ term, children }: { term: string; children: ReactNode }) {
  return (
    <div className="grid gap-0.5 border-b py-2.5 last:border-b-0">
      <dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{term}</dt>
      <dd className="break-words text-sm">{children}</dd>
    </div>
  );
}

const fmtSecs = (s?: number) => (s === undefined ? "none yet" : `${s.toFixed(2)} s`);

/** Which model is answering, read from /api/model-info (nothing here is hard-coded). */
export function ModelInfoSheet({ open, onOpenChange, age, ageText, lastSecs }: Props) {
  const info = useQuery({ queryKey: queryKeys.modelInfo, queryFn: api.modelInfo, enabled: open, staleTime: 60_000 });
  const d = info.data;
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent>
        <SheetHeader>
          <SheetTitle>Model info</SheetTitle>
          <SheetDescription>
            The AI child is a base language model plus a small trained add-on (a LoRA adapter) for each age. The
            untrained AI is the same base model without the add-on.
          </SheetDescription>
        </SheetHeader>
        {info.isPending && <p className="text-sm text-muted-foreground">Loading…</p>}
        {info.isError && <p className="text-sm text-danger">Couldn't load model info: {info.error.message}</p>}
        {d && (
          <dl>
            <Row term="Base model">{d.base_model}</Row>
            <Row term={`Adapter for ${ageText}`}>{d.adapters[String(age)] ?? "none for this age"}</Row>
            <Row term="Decoding">
              {Object.keys(d.decoding).length === 0 ? (
                "defaults"
              ) : (
                <ul className="grid gap-0.5">
                  {Object.entries(d.decoding).map(([k, v]) => (
                    <li key={k}>
                      <span className="text-muted-foreground">{k}</span>: {String(v)}
                    </li>
                  ))}
                </ul>
              )}
            </Row>
            <Row term="Context">{d.context_turns} earlier turns</Row>
            <Row term="Device">
              {d.device}
              {d.load_in_4bit ? " (4-bit)" : ""}
            </Row>
            <Row term="Last reply times">
              Child: {fmtSecs(lastSecs.child)}
              <br />
              Untrained AI: {fmtSecs(lastSecs.untrained)}
            </Row>
          </dl>
        )}
      </SheetContent>
    </Sheet>
  );
}
