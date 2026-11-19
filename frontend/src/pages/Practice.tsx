import { useQuery } from "@tanstack/react-query";
import { BookOpen, Info, MessagesSquare, RotateCcw } from "lucide-react";
import { useId, useRef, useState } from "react";
import { useLocation } from "react-router";
import { api, queryKeys, type AppConfig, type SessionCreated, type TurnReply } from "@/api";
import { useMe } from "@/auth";
import { ChatLog } from "@/components/chat/ChatLog";
import { Composer } from "@/components/chat/Composer";
import { ModelInfoSheet } from "@/components/chat/ModelInfoSheet";
import { ScenarioPicker } from "@/components/chat/ScenarioPicker";
import type { ChatTurn, ReplyState, Side } from "@/components/chat/types";
import { FullPageSpinner } from "@/components/FullPageSpinner";
import { EmptyState, PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { useToast } from "@/components/ui/toast";
import { Tooltip } from "@/components/ui/tooltip";
import { ageLabel, thinkingDelayMs, wait } from "@/lib/reply";

/**
 * Router state for opening Practice with a set age and scene, e.g. from "Practice again with this
 * scenario" on a reopened session (src/pages/SessionView.tsx).
 */
export interface PracticeStart {
  age?: number;
  scenarioId?: string | null;
}

/** The practice screen (route `/`): talk with the AI child, optionally beside the untrained model. */
export function PracticePage() {
  const me = useMe().data;
  const start = (useLocation().state ?? null) as PracticeStart | null;
  const first = me?.display_name?.split(/\s+/)[0];
  const config = useQuery({ queryKey: queryKeys.config, queryFn: api.config });

  return (
    <>
      <PageHeader
        title={first ? `Welcome, ${first}` : "Practice"}
        description="Talk with an AI child and try out your questions and prompts."
      />
      {config.isPending && <FullPageSpinner />}
      {config.isError && (
        <EmptyState icon={<MessagesSquare aria-hidden />} title="Couldn't load the practice settings">
          <p>{config.error.message}</p>
          <Button variant="secondary" className="mt-3" onClick={() => config.refetch()}>
            Try again
          </Button>
        </EmptyState>
      )}
      {config.data &&
        (config.data.ages.length === 0 ? (
          <EmptyState icon={<MessagesSquare aria-hidden />} title="No child model is available">
            The server has no trained model for any age yet.
          </EmptyState>
        ) : (
          <PracticeChat config={config.data} start={start} />
        ))}
    </>
  );
}

function PracticeChat({ config, start }: { config: AppConfig; start: PracticeStart | null }) {
  const toast = useToast();
  const ageId = useId();
  const compareId = useId();

  // A start age or scene the server no longer offers falls back to the defaults.
  const startAge = start?.age !== undefined && config.ages.includes(start.age) ? start.age : null;
  const startScenario = config.scenarios.find((s) => s.id === start?.scenarioId) ?? null;
  const [age, setAge] = useState<number>(startAge ?? config.default_age ?? config.ages[0]);
  const [compare, setCompareState] = useState(config.compare_default);
  const [scenarioId, setScenarioId] = useState<string | null>(startScenario?.id ?? null);
  const [session, setSession] = useState<SessionCreated | null>(null);
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [compareStarts, setCompareStarts] = useState<number[]>([]);
  const [draft, setDraft] = useState(startScenario?.opening_line ?? "");
  const [busy, setBusy] = useState(false);
  const [lastSecs, setLastSecs] = useState<{ child?: number; untrained?: number }>({});
  const [pickerOpen, setPickerOpen] = useState(false);
  const [infoOpen, setInfoOpen] = useState(false);
  const [pendingAge, setPendingAge] = useState<number | null>(null);
  const [togglingCompare, setTogglingCompare] = useState(false);

  // Refs hold what the async send loop must read at the moment it runs, not when it started.
  const sessionRef = useRef<SessionCreated | null>(null);
  const compareRef = useRef(compare);
  /** The first turn the server will answer on the untrained side. */
  const compareSinceRef = useRef<number>(Infinity);
  /** Bumped on every reset, so replies to an abandoned conversation are ignored. */
  const epochRef = useRef(0);
  const keyRef = useRef(0);

  const scenario = config.scenarios.find((s) => s.id === scenarioId) ?? null;
  const ageText = (a: number) => ageLabel(a, config.age_labels[String(a)]);

  const setCompare = (on: boolean) => {
    compareRef.current = on;
    setCompareState(on);
  };

  /** Start over: a fresh conversation (the server session is created on the first line). */
  const reset = (nextScenarioId: string | null = scenarioId) => {
    epochRef.current += 1;
    sessionRef.current = null;
    compareSinceRef.current = Infinity;
    setSession(null);
    setTurns([]);
    setCompareStarts([]);
    setBusy(false);
    setLastSecs({});
    setDraft(config.scenarios.find((s) => s.id === nextScenarioId)?.opening_line ?? "");
  };

  const updateTurn = (key: string, side: Side, state: ReplyState, turnNo?: number) =>
    setTurns((prev) =>
      prev.map((t) => (t.key === key ? { ...t, [side]: state, ...(turnNo !== undefined ? { turn: turnNo } : {}) } : t)),
    );

  /** Show a reply; one that starts with a pause shows "thinking…" first (at most 5 s). */
  const reveal = async (key: string, side: Side, reply: TurnReply, epoch: number) => {
    const ms = thinkingDelayMs(reply.pause_s);
    if (ms > 0) {
      updateTurn(key, side, { status: "thinking", reply }, side === "child" ? reply.turn : undefined);
      await wait(ms);
      if (epoch !== epochRef.current) return;
    }
    updateTurn(key, side, { status: "done", reply }, side === "child" ? reply.turn : undefined);
    setLastSecs((p) => ({ ...p, [side]: reply.secs }));
  };

  const send = async () => {
    const line = draft.trim();
    if (!line || busy) return;
    const epoch = epochRef.current;
    const stale = () => epoch !== epochRef.current;
    setBusy(true);
    try {
      let s = sessionRef.current;
      if (!s) {
        try {
          s = await api.startSession(age, compareRef.current, scenarioId ?? undefined);
        } catch (e) {
          if (!stale()) toast({ tone: "error", title: "Couldn't start the conversation", description: (e as Error).message });
          return;
        }
        if (stale()) return;
        sessionRef.current = s;
        compareSinceRef.current = s.compare ? 1 : Infinity;
        setSession(s);
      }

      const key = `t${++keyRef.current}`;
      const turnNo = turns.length + 1;
      setTurns((prev) => [...prev, { key, turn: turnNo, adult: line, child: { status: "pending" }, untrained: null }]);
      setDraft("");

      let child: TurnReply;
      try {
        child = await api.sendTurn(s.id, line);
      } catch (e) {
        if (stale()) return;
        // Nothing was stored for this line: take it back out and return it to the input.
        setTurns((prev) => prev.filter((t) => t.key !== key));
        setDraft(line);
        toast({ tone: "error", title: "The child didn't answer", description: (e as Error).message });
        return;
      }
      if (stale()) return;
      await reveal(key, "child", child, epoch);
      if (stale()) return;

      // The untrained reply comes second, and only while compare is on (checked now, not when sending).
      if (!compareRef.current || child.turn < compareSinceRef.current) return;
      setTurns((prev) => prev.map((t) => (t.key === key ? { ...t, untrained: { status: "pending" } } : t)));
      try {
        const u = await api.untrainedReply(s.id, child.turn);
        if (stale()) return;
        await reveal(key, "untrained", u, epoch);
      } catch (e) {
        if (stale()) return;
        const message = (e as Error).message;
        updateTurn(key, "untrained", { status: "error", message: "No reply from the untrained AI." });
        toast({ tone: "error", title: "The untrained AI didn't answer", description: message });
      }
    } finally {
      if (!stale()) setBusy(false);
    }
  };

  const toggleCompare = async (on: boolean) => {
    const s = sessionRef.current;
    if (!s) {
      setCompare(on);
      return;
    }
    setTogglingCompare(true);
    setCompare(on);
    try {
      const state = await api.setCompare(s.id, on);
      if (sessionRef.current?.id !== s.id) return;
      setCompare(state.compare);
      if (state.compare && state.compare_started_turn !== null) {
        compareSinceRef.current = state.compare_started_turn;
        const started = state.compare_started_turn;
        if (started > 1) setCompareStarts((prev) => (prev.includes(started) ? prev : [...prev, started]));
      }
    } catch (e) {
      if (sessionRef.current?.id === s.id) setCompare(!on);
      toast({ tone: "error", title: "Couldn't switch the comparison", description: (e as Error).message });
    } finally {
      setTogglingCompare(false);
    }
  };

  const changeAge = (value: string) => {
    const next = Number(value);
    if (next === age) return;
    if (turns.length > 0) {
      setPendingAge(next);
      return;
    }
    setAge(next);
    if (sessionRef.current) reset();
  };

  const pickScenario = (id: string | null) => {
    setPickerOpen(false);
    if (id === scenarioId && turns.length === 0) return;
    setScenarioId(id);
    if (turns.length > 0 || sessionRef.current) {
      reset(id);
    } else {
      setDraft(config.scenarios.find((s) => s.id === id)?.opening_line ?? "");
    }
  };

  return (
    <div className="grid gap-4">
      <div className="flex flex-wrap items-end gap-x-5 gap-y-3 rounded-xl border bg-surface p-3 shadow-card sm:p-4">
        <div className="grid w-full gap-1.5 sm:w-60">
          <Label htmlFor={ageId}>Child's age</Label>
          <Select value={String(age)} onValueChange={changeAge}>
            <SelectTrigger id={ageId}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {config.ages.map((a) => (
                <SelectItem key={a} value={String(a)}>
                  {ageText(a)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="flex h-10 items-center gap-2.5">
          <Switch id={compareId} checked={compare} onCheckedChange={toggleCompare} disabled={togglingCompare} />
          <Label htmlFor={compareId} className="cursor-pointer">
            Compare with untrained AI
          </Label>
        </div>
        <div className="ml-auto flex flex-wrap items-center gap-2">
          <Button variant="secondary" onClick={() => setPickerOpen(true)}>
            <BookOpen aria-hidden />
            Scene
          </Button>
          <Tooltip content="Model info">
            <Button variant="secondary" size="icon" aria-label="Model info" onClick={() => setInfoOpen(true)}>
              <Info aria-hidden />
            </Button>
          </Tooltip>
          <Button variant="secondary" onClick={() => reset()} disabled={turns.length === 0 && !busy}>
            <RotateCcw aria-hidden />
            New session
          </Button>
        </div>
      </div>

      <div
        className="flex flex-wrap items-start justify-between gap-2 rounded-lg border border-dashed bg-surface-muted/60 px-4 py-3 text-sm"
        aria-label="Current scene"
        role="note"
      >
        <div className="grid min-w-0 gap-0.5">
          <span className="font-medium">{scenario ? scenario.title : "Free conversation"}</span>
          <span className="text-muted-foreground">
            {scenario ? scenario.scene : "No set scene. Pick one for a situation and a suggested opening line."}
          </span>
        </div>
        <Button variant="link" size="sm" className="h-auto px-0" onClick={() => setPickerOpen(true)}>
          Change scene
        </Button>
      </div>

      <div className="grid gap-4 rounded-xl border bg-surface p-3 shadow-card sm:p-5">
        {turns.length === 0 ? (
          <p className="py-8 text-center text-sm text-muted-foreground">
            You are talking with an AI child aged {ageText(age)}. Type your first line below.
            {compare && " The untrained AI will answer beside the child."}
          </p>
        ) : (
          <ChatLog
            turns={turns}
            compare={compare}
            compareStarts={compareStarts}
            sessionId={session?.id ?? null}
            saving={config.saving}
          />
        )}
        <Composer value={draft} onChange={setDraft} onSend={send} busy={busy} />
      </div>

      <ScenarioPicker
        open={pickerOpen}
        onOpenChange={setPickerOpen}
        scenarios={config.scenarios}
        current={scenarioId}
        startsNew={turns.length > 0}
        onPick={pickScenario}
      />
      <ModelInfoSheet open={infoOpen} onOpenChange={setInfoOpen} age={age} ageText={ageText(age)} lastSecs={lastSecs} />
      <Dialog open={pendingAge !== null} onOpenChange={(o) => !o && setPendingAge(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Start a new session?</DialogTitle>
            <DialogDescription>
              Changing the age to {pendingAge !== null ? ageText(pendingAge) : ""} starts a new conversation. This one
              {config.saving ? " stays in your History." : " is not saved."}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="secondary" onClick={() => setPendingAge(null)}>
              Keep this conversation
            </Button>
            <Button
              onClick={() => {
                if (pendingAge !== null) setAge(pendingAge);
                setPendingAge(null);
                reset();
              }}
            >
              Start new session
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
