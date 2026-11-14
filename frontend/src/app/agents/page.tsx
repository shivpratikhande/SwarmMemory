"use client";

import { HistoryIcon, Loader2Icon, PlayIcon } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { PageHeader } from "@/components/app-shell";
import { AgentGlyph, ChainTag, Empty, Mono, StatusBadge } from "@/components/bits";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Textarea } from "@/components/ui/textarea";
import { post, type Agent, type AgentDetail, type Execution } from "@/lib/api";
import { ROLE_LABEL, clock, timeAgo } from "@/lib/format";
import { useLive } from "@/lib/hooks";
import { cn } from "@/lib/utils";

const DEFAULT_TASK: Record<string, string> = {
  researcher: "Find a reliable API service for a developer application.",
  verifier: "Independently verify memories awaiting verification.",
  developer: "Find a reliable API without wasting time on previously failed options.",
};

function Metric({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="rounded-xl bg-surface px-3 py-2.5 ring-1 ring-border/70">
      <div className="text-[11.5px] text-muted-foreground">{label}</div>
      <div className="mt-0.5 font-[family-name:var(--font-display)] text-[17px] font-semibold tabular-nums">{value}</div>
    </div>
  );
}

const ROLE_BLURB: Record<string, string> = {
  researcher: "Runs real experiments and publishes what it learns",
  verifier: "Re-tests claims independently, never reads the evidence",
  developer: "Buys verified knowledge to skip wasted work",
};

function AgentCard({ a, onOpen }: { a: Agent; onOpen: () => void }) {
  const [task, setTask] = useState(DEFAULT_TASK[a.role]);
  const [apis, setApis] = useState("api-x, api-y");
  const [busy, setBusy] = useState(false);

  async function execute() {
    setBusy(true);
    try {
      const options = a.role === "researcher" ? { apis: apis.split(",").map((s) => s.trim()).filter(Boolean) } : {};
      await post(`/agents/${a.id}/execute`, { task, options });
      toast.success(`${a.name} started`);
      onOpen();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to start");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="lift flex flex-col gap-0 py-0">
      <div className="relative px-5 pt-5 pb-4">
        <div className="hero-surface absolute inset-x-0 top-0 h-16 opacity-70" />
        <div className="relative flex items-start gap-3.5">
          <AgentGlyph id={a.id} role={a.role} size="lg" />
          <div className="min-w-0 flex-1 pt-0.5">
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="text-[17px] font-semibold">{a.name.split(" · ")[0]}</h3>
              <StatusBadge status={a.status} />
            </div>
            <div className="text-[13px] font-medium text-primary">{ROLE_LABEL[a.role]}</div>
          </div>
          <Button variant="outline" size="sm" className="rounded-full" onClick={onOpen}>
            <HistoryIcon /> History
          </Button>
        </div>
        <p className="relative mt-3 text-[13px] text-muted-foreground">{ROLE_BLURB[a.role]}</p>
      </div>
      <CardContent className="flex flex-1 flex-col gap-4 pb-5">
        <div className="flex items-center gap-2 rounded-xl bg-surface px-3 py-2 ring-1 ring-border/70">
          <ChainTag simulated={a.network !== "testnet"} />
          <Mono className="truncate text-foreground/80">{a.near_account_id}</Mono>
          <span className={cn("ml-auto inline-flex items-center gap-1 text-[11.5px] font-medium", a.onchain_registered ? "text-ok" : "text-warn")}>
            <span className="size-1.5 rounded-full bg-current" />
            {a.onchain_registered ? "Registered" : "Unregistered"}
          </span>
        </div>
        <div className="grid grid-cols-3 gap-2">
          <Metric label="Reputation" value={<span className={a.reputation < 0 ? "text-bad" : "text-ok"}>{a.reputation}</span>} />
          <Metric label="Tasks" value={a.tasks_completed} />
          <Metric label="Published" value={a.memories_contributed} />
          <Metric label="Retrieved" value={a.memories_retrieved} />
          <Metric label="Earned" value={<span className="text-chain">{a.earned_near}</span>} />
          <Metric label="Spent" value={a.spent_near} />
        </div>
        <details className="group rounded-xl ring-1 ring-border/70">
          <summary className="cursor-pointer list-none px-3 py-2 text-[12.5px] font-medium text-muted-foreground hover:text-foreground">
            <span className="group-open:hidden">Show system prompt</span>
            <span className="hidden group-open:inline">Hide system prompt</span>
          </summary>
          <p className="border-t px-3 py-2.5 text-xs leading-relaxed text-muted-foreground">{a.system_prompt}</p>
        </details>
        <div className="mt-auto space-y-2 border-t pt-4">
          <Label className="text-xs text-muted-foreground">Task</Label>
          <Textarea value={task} onChange={(e) => setTask(e.target.value)} rows={2} className="resize-none bg-surface text-sm" />
          {a.role === "researcher" && (
            <Input value={apis} onChange={(e) => setApis(e.target.value)} className="bg-surface font-mono text-xs" title="Services to test" placeholder="Services to test" />
          )}
          <Button onClick={execute} disabled={busy || a.status === "running"} className="h-10 w-full rounded-xl">
            {busy || a.status === "running" ? <Loader2Icon className="animate-spin" /> : <PlayIcon />}
            {a.status === "running" ? "Executing…" : "Execute task"}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function ExecutionItem({ e }: { e: Execution }) {
  const [open, setOpen] = useState(e.status === "running");
  return (
    <div className="overflow-hidden rounded-xl ring-1 ring-border">
      <button className="flex w-full items-center gap-2 px-3 py-2.5 text-left" onClick={() => setOpen(!open)}>
        <StatusBadge status={e.status} />
        <span className="min-w-0 flex-1 truncate text-sm">{e.task}</span>
        <span className="text-[11px] text-muted-foreground">{timeAgo(e.started_at)}</span>
      </button>
      {open && (
        <div className="border-t bg-surface px-3 py-2.5">
          <ol className="space-y-1 font-mono text-[11px] leading-relaxed">
            {e.logs.map((l, i) => (
              <li key={i} className="flex gap-3">
                <span className="shrink-0 text-muted-foreground">{clock(l.ts)}</span>
                <span className={l.msg.startsWith("ERROR") ? "text-bad" : "text-foreground/85"}>{l.msg}</span>
              </li>
            ))}
          </ol>
          {e.error && <div className="mt-2 text-xs text-bad">{e.error}</div>}
        </div>
      )}
    </div>
  );
}

function AgentSheet({ id, onClose }: { id: string | null; onClose: () => void }) {
  const { data } = useLive<AgentDetail>(id ? `/agents/${id}` : null, 1500);
  return (
    <Sheet open={!!id} onOpenChange={(o) => !o && onClose()}>
      <SheetContent className="w-full sm:max-w-xl">
        <SheetHeader>
          <SheetTitle>{data?.name ?? "Agent"}</SheetTitle>
          <SheetDescription>Execution history, contributed memories and reputation changes.</SheetDescription>
        </SheetHeader>
        <ScrollArea className="h-[calc(100vh-7rem)] px-4">
          {data && (
            <div className="space-y-6 pb-8">
              <section className="space-y-2">
                <h3 className="text-[11px] font-semibold tracking-[0.12em] text-muted-foreground uppercase">Executions</h3>
                {data.executions.length ? data.executions.map((e) => <ExecutionItem key={e.id} e={e} />) : <Empty>No executions yet.</Empty>}
              </section>
              <section className="space-y-2">
                <h3 className="text-[11px] font-semibold tracking-[0.12em] text-muted-foreground uppercase">Memory history</h3>
                {data.memories.length ? (
                  data.memories.map((m) => (
                    <div key={m.memory_id} className="flex items-center gap-2 text-sm">
                      <Mono className="text-muted-foreground">#{m.seq}</Mono>
                      <span className="flex-1 truncate">{m.title}</span>
                      <StatusBadge status={m.status} />
                    </div>
                  ))
                ) : (
                  <p className="text-xs text-muted-foreground">No contributed memories.</p>
                )}
              </section>
              <section className="space-y-2">
                <h3 className="text-[11px] font-semibold tracking-[0.12em] text-muted-foreground uppercase">Reputation</h3>
                {data.reputation_events.map((r, i) => (
                  <div key={i} className="flex items-center gap-2 text-sm">
                    <span className={cn("w-10 font-mono", r.delta > 0 ? "text-ok" : "text-bad")}>{r.delta > 0 ? `+${r.delta}` : r.delta}</span>
                    <span className="flex-1 text-muted-foreground">{r.reason.replaceAll("_", " ")}</span>
                    <span className="text-[11px] text-muted-foreground">{timeAgo(r.created_at)}</span>
                  </div>
                ))}
              </section>
              <section className="space-y-2">
                <h3 className="text-[11px] font-semibold tracking-[0.12em] text-muted-foreground uppercase">On-chain identity (contract read)</h3>
                <pre className="overflow-x-auto rounded-xl bg-surface p-3 font-mono ring-1 ring-border text-[11px] text-muted-foreground">{JSON.stringify(data.onchain, null, 2)}</pre>
              </section>
            </div>
          )}
        </ScrollArea>
      </SheetContent>
    </Sheet>
  );
}

export default function AgentsPage() {
  const { data } = useLive<Agent[]>("/agents", 2000);
  const [open, setOpen] = useState<string | null>(null);
  return (
    <>
      <PageHeader
        eyebrow="Network"
        title="Agent Swarm"
        description="Three independent agents, each with its own NEAR identity and API key. They never talk to each other directly. They only coordinate through shared memory."
      />
      <div className="grid gap-5 lg:grid-cols-3">
        {data ? data.map((a) => <AgentCard key={a.id} a={a} onOpen={() => setOpen(a.id)} />) : Array.from({ length: 3 }).map((_, i) => <Card key={i} className="h-96 animate-pulse" />)}
      </div>
      <AgentSheet id={open} onClose={() => setOpen(null)} />
    </>
  );
}
