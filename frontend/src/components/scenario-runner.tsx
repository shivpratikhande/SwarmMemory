"use client";

import { CheckCircle2Icon, CircleDashedIcon, Loader2Icon, PlayIcon, XCircleIcon } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { AgentGlyph, StatusBadge } from "@/components/bits";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { post, type ScenarioRun } from "@/lib/api";
import { timeAgo } from "@/lib/format";
import { useLive } from "@/lib/hooks";
import { cn } from "@/lib/utils";

const PLAN = [
  "1-2 · Agent A tests API X and publishes a Memory Capsule",
  "3 · Agent B independently verifies the memory",
  "4-7 · Agent C searches memory, purchases access and picks an API",
];

function StepIcon({ status }: { status: string }) {
  if (status === "succeeded") return <CheckCircle2Icon className="size-4 text-ok" />;
  if (status === "failed") return <XCircleIcon className="size-4 text-bad" />;
  if (status === "running") return <Loader2Icon className="size-4 animate-spin text-warn" />;
  return <CircleDashedIcon className="size-4 text-muted-foreground" />;
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

  const steps = run?.steps ?? [];
  const s = run?.summary as Record<string, unknown> | null | undefined;

  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-start justify-between gap-4">
        <div className="space-y-1.5">
          <CardTitle>End-to-end demonstration</CardTitle>
          <CardDescription className="max-w-xl">
            Agent A discovers API X is unreliable and publishes it, Agent B independently re-tests it, and Agent C buys the verified memory and picks API Y
            without repeating the experiment. Controlled environment: API X fails 8/20 requests, API Y 1/20.
          </CardDescription>
        </div>
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <Switch id="inject" checked={inject} onCheckedChange={setInject} disabled={running} />
            <Label htmlFor="inject" className="text-xs text-muted-foreground" title="Agent A also publishes a hasty 5-request claim about API Y, which verification should dispute">
              Inject misleading claim
            </Label>
          </div>
          <Button onClick={start} disabled={starting || running}>
            {running || starting ? <Loader2Icon className="animate-spin" /> : <PlayIcon />}
            {running ? "Running…" : "Run scenario"}
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-5">
        <ol className="space-y-2">
          {(steps.length ? steps : PLAN.map((title) => ({ title, status: "idle", agent_id: "" }))).map((st, i) => {
            const r = (st as { result?: Record<string, unknown> }).result;
            return (
              <li key={i} className={cn("flex items-start gap-3 rounded-md border px-3 py-2.5", st.status === "running" && "border-warn/30 bg-warn/5")}>
                <span className="pt-0.5">
                  <StepIcon status={st.status} />
                </span>
                {st.agent_id && <AgentGlyph id={st.agent_id} size="sm" />}
                <div className="min-w-0 flex-1">
                  <div className="text-sm">{st.title}</div>
                  {r && <StepResult r={r} />}
                  {(st as { error?: string }).error && <div className="mt-1 text-xs text-bad">{(st as { error?: string }).error}</div>}
                </div>
                {st.status !== "idle" && <StatusBadge status={st.status} />}
              </li>
            );
          })}
        </ol>

        {run && run.status !== "running" && (
          <div className={cn("rounded-lg border p-4", run.status === "succeeded" ? "border-ok/25 bg-ok/5" : "border-bad/25 bg-bad/5")}>
            {run.status === "succeeded" && s ? (
              <div className="grid gap-4 sm:grid-cols-4">
                <Outcome label="Agent C chose" value={String(s.chosen_api ?? "—").toUpperCase()} tone="text-ok" />
                <Outcome label="Avoided without re-testing" value={Object.keys((s.avoided_apis as object) ?? {}).join(", ").toUpperCase() || "—"} tone="text-bad" />
                <Outcome label="Requests saved" value={`${s.requests_saved} / ${s.baseline_requests}`} />
                <Outcome label="Agent A claimable reward" value={`${s.agent_a_claimable_near} Ⓝ`} tone="text-chain" />
              </div>
            ) : (
              <div className="text-sm text-bad">Scenario failed: {run.error}</div>
            )}
            <div className="mt-3 text-[11px] text-muted-foreground">
              Run {run.id} · {run.network} · finished {timeAgo(run.finished_at)}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function Outcome({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div>
      <div className="text-[11px] text-muted-foreground">{label}</div>
      <div className={cn("mt-0.5 font-mono text-lg font-semibold", tone)}>{value}</div>
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
  ver?.forEach((v) => v.result && bits.push(`${v.memory_id}: ${v.result} (measured ${Math.round((v.measured ?? 0) * 100)}%)`));
  if (r.chosen_api) bits.push(`chose ${r.chosen_api} · ${r.requests_made} requests instead of ${r.baseline_requests}`);
  if (!bits.length) return null;
  return <div className="mt-1 text-xs text-muted-foreground">{bits.join(" · ")}</div>;
}
