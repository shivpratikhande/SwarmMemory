"use client";

import { CheckIcon, Loader2Icon, PlayIcon, XIcon } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { AgentGlyph, StatusBadge } from "@/components/bits";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { post, type ScenarioRun } from "@/lib/api";
import { timeAgo } from "@/lib/format";
import { useLive } from "@/lib/hooks";
import { cn } from "@/lib/utils";

const PLAN = [
  { title: "Agent A tests API X and publishes a Memory Capsule", agent_id: "agent-a-researcher" },
  { title: "Agent B independently verifies the memory", agent_id: "agent-b-verifier" },
  { title: "Agent C searches memory, purchases access and picks an API", agent_id: "agent-c-developer" },
];

/** Strip the "1-2 · " step-number prefix the backend puts on titles. */
const cleanTitle = (t: string) => t.replace(/^[\d-]+\s*·\s*/, "");

function StepNode({ status, agentId }: { status: string; agentId?: string }) {
  if (status === "succeeded")
    return (
      <span className="grid size-9 place-items-center rounded-full bg-ok text-white ring-4 ring-card">
        <CheckIcon className="size-4" strokeWidth={3} />
      </span>
    );
  if (status === "failed")
    return (
      <span className="grid size-9 place-items-center rounded-full bg-bad text-white ring-4 ring-card">
        <XIcon className="size-4" strokeWidth={3} />
      </span>
    );
  if (status === "running")
    return (
      <span className="grid size-9 place-items-center rounded-full bg-warn/15 text-warn ring-4 ring-card">
        <Loader2Icon className="size-4 animate-spin" />
      </span>
    );
  return agentId ? (
    <span className="opacity-60">
      <AgentGlyph id={agentId} />
    </span>
  ) : (
    <span className="size-9 rounded-full border-2 border-dashed bg-card" />
  );
}

export function ScenarioRunner() {
  const { data: runs, mutate } = useLive<ScenarioRun[]>("/scenario/runs", 1500);
  const [inject, setInject] = useState(true);
  const [starting, setStarting] = useState(false);
  const run = runs?.[0];
  const running = run?.status === "running";

  async function start() {
    setStarting(true);
    try {
      await post("/scenario/run", { inject_misleading: inject });
      await mutate();
      toast.success("Scenario started");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not start scenario");
    } finally {
      setStarting(false);
    }
  }

  const steps = run?.steps?.length ? run.steps : PLAN.map((p) => ({ ...p, status: "idle" }));
  const s = run?.summary as Record<string, unknown> | null | undefined;

  return (
    <Card className="gap-5">
      <CardHeader className="gap-4">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="space-y-1.5">
            <div className="text-xs font-semibold tracking-[0.14em] text-primary uppercase">Live demo</div>
            <CardTitle className="text-lg">One discovery, three agents, zero wasted work</CardTitle>
          </div>
          <Button onClick={start} disabled={starting || running} className="rounded-full px-4">
            {running || starting ? <Loader2Icon className="animate-spin" /> : <PlayIcon />}
            {running ? "Running…" : run ? "Run again" : "Run scenario"}
          </Button>
        </div>
        <p className="text-[13.5px] leading-relaxed text-muted-foreground">
          Agent A finds that API X is unreliable and publishes it. Agent B re-tests it independently. Agent C buys the verified memory and goes straight to
          API Y without repeating the experiment. The test environment is controlled: API X fails 8 of 20 requests, API Y fails 1 of 20.
        </p>
        <div className="flex items-center gap-3 rounded-xl bg-surface px-3.5 py-2.5 ring-1 ring-border">
          <Switch id="inject" checked={inject} onCheckedChange={setInject} disabled={running} />
          <Label htmlFor="inject" className="block flex-1 cursor-pointer text-[13px] leading-snug font-normal">
            <span className="font-medium">Inject a misleading claim</span>
            <span className="text-muted-foreground"> · Agent A also publishes a hasty claim about API Y, which verification should dispute</span>
          </Label>
        </div>
      </CardHeader>

      <CardContent className="space-y-5">
        <ol className="relative">
          {steps.map((st, i) => {
            const r = (st as { result?: Record<string, unknown> }).result;
            const err = (st as { error?: string }).error;
            const last = i === steps.length - 1;
            return (
              <li key={i} className="relative flex gap-4 pb-5 last:pb-0">
                {!last && <span className={cn("absolute top-10 bottom-1 left-[17px] w-0.5 rounded-full", st.status === "succeeded" ? "bg-ok/40" : "bg-border")} />}
                <StepNode status={st.status} agentId={st.agent_id} />
                <div className={cn("min-w-0 flex-1 rounded-xl px-4 py-3 ring-1 ring-border transition-colors", st.status === "running" ? "bg-warn/6 ring-warn/30" : "bg-surface/70")}>
                  <div className="flex flex-col-reverse items-start gap-2 sm:flex-row sm:gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        {st.agent_id && st.status !== "idle" && (
                          <span className="hidden sm:inline-flex">
                            <AgentGlyph id={st.agent_id} size="sm" />
                          </span>
                        )}
                        <span className="text-[14px] font-medium">{cleanTitle(st.title)}</span>
                      </div>
                      {r && <StepResult r={r} />}
                      {err && <div className="mt-1 text-xs text-bad">{err}</div>}
                    </div>
                    {st.status !== "idle" && <StatusBadge status={st.status} />}
                  </div>
                </div>
              </li>
            );
          })}
        </ol>

        {run && run.status !== "running" && (
          <div className={cn("animate-rise overflow-hidden rounded-2xl ring-1", run.status === "succeeded" ? "bg-ok/6 ring-ok/25" : "bg-bad/6 ring-bad/25")}>
            {run.status === "succeeded" && s ? (
              <div className="grid grid-cols-2 divide-border sm:grid-cols-4 sm:divide-x">
                <Outcome label="Agent C chose" value={String(s.chosen_api ?? "—").toUpperCase()} tone="text-ok" />
                <Outcome label="Skipped without re-testing" value={Object.keys((s.avoided_apis as object) ?? {}).join(", ").toUpperCase() || "—"} tone="text-bad" />
                <Outcome label="Requests saved" value={`${s.requests_saved} of ${s.baseline_requests}`} />
                <Outcome label="Agent A earned" value={`${s.agent_a_claimable_near} Ⓝ`} tone="text-chain" />
              </div>
            ) : (
              <div className="p-4 text-sm text-bad">Scenario failed: {run.error}</div>
            )}
            <div className="border-t border-border/60 px-4 py-2.5 text-[11.5px] text-muted-foreground">
              Run <span className="font-mono">{run.id}</span> · {run.network} · finished {timeAgo(run.finished_at)}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function Outcome({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="px-4 py-4">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className={cn("mt-1 font-[family-name:var(--font-display)] text-xl font-semibold tabular-nums", tone)}>{value}</div>
    </div>
  );
}

function StepResult({ r }: { r: Record<string, unknown> }) {
  const bits: string[] = [];
  const findings = r.findings as { api: string; failure_rate: number; requests: number }[] | undefined;
  findings?.forEach((f) => bits.push(`${f.api}: ${Math.round(f.failure_rate * 100)}% failures over ${f.requests} requests`));
  const pub = r.published_memories as string[] | undefined;
  if (pub?.length) bits.push(`published ${pub.join(", ")}`);
  const ver = r.verified as { memory_id: string; result?: string; measured?: number }[] | undefined;
  ver?.forEach((v) => v.result && bits.push(`${v.memory_id}: ${v.result.toLowerCase()} (measured ${Math.round((v.measured ?? 0) * 100)}%)`));
  if (r.chosen_api) bits.push(`chose ${r.chosen_api} · ${r.requests_made} requests instead of ${r.baseline_requests}`);
  if (!bits.length) return null;
  return <div className="mt-1 text-[12.5px] leading-relaxed text-muted-foreground">{bits.join(" · ")}</div>;
}
