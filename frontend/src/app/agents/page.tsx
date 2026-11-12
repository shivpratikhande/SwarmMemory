"use client";

import { Loader2Icon, PlayIcon } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { PageHeader } from "@/components/app-shell";
import { AgentGlyph, ChainTag, Empty, Mono, StatusBadge } from "@/components/bits";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
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
    <div>
      <div className="text-[11px] text-muted-foreground">{label}</div>
      <div className="font-mono text-sm tabular-nums">{value}</div>
    </div>
  );
}

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
    <Card className="flex flex-col">
      <CardHeader className="flex flex-row items-start gap-3">
        <AgentGlyph id={a.id} role={a.role} />
        <div className="min-w-0 flex-1 space-y-1">
          <CardTitle className="flex items-center gap-2 text-base">
            {a.name} <StatusBadge status={a.status} />
          </CardTitle>
          <CardDescription>{ROLE_LABEL[a.role]}</CardDescription>
        </div>
        <Button variant="ghost" size="sm" onClick={onOpen}>
          History
        </Button>
      </CardHeader>
      <CardContent className="flex flex-1 flex-col gap-5">
        <div className="flex items-center gap-2 rounded-md border bg-background/40 px-3 py-2">
          <ChainTag simulated={a.network !== "testnet"} />
          <Mono className="truncate">{a.near_account_id}</Mono>
          <span className={cn("ml-auto text-[11px]", a.onchain_registered ? "text-ok" : "text-warn")}>{a.onchain_registered ? "registered" : "unregistered"}</span>
        </div>
        <div className="grid grid-cols-3 gap-3">
          <Metric label="Reputation" value={<span className={a.reputation < 0 ? "text-bad" : "text-ok"}>{a.reputation}</span>} />
          <Metric label="Tasks completed" value={a.tasks_completed} />
          <Metric label="Memories contributed" value={a.memories_contributed} />
          <Metric label="Memories retrieved" value={a.memories_retrieved} />
          <Metric label="Earned" value={`${a.earned_near} Ⓝ`} />
          <Metric label="Spent" value={`${a.spent_near} Ⓝ`} />
        </div>
        <p className="line-clamp-3 text-xs leading-relaxed text-muted-foreground" title={a.system_prompt}>
          {a.system_prompt}
        </p>
        <div className="mt-auto space-y-2 border-t pt-4">
          <Textarea value={task} onChange={(e) => setTask(e.target.value)} rows={2} className="resize-none text-sm" />
          {a.role === "researcher" && <Input value={apis} onChange={(e) => setApis(e.target.value)} className="font-mono text-xs" title="Services to test" />}
          <Button onClick={execute} disabled={busy || a.status === "running"} className="w-full">
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
    <div className="rounded-lg border">
      <button className="flex w-full items-center gap-2 px-3 py-2.5 text-left" onClick={() => setOpen(!open)}>
        <StatusBadge status={e.status} />
        <span className="min-w-0 flex-1 truncate text-sm">{e.task}</span>
        <span className="text-[11px] text-muted-foreground">{timeAgo(e.started_at)}</span>
      </button>
      {open && (
        <div className="border-t bg-background/50 px-3 py-2">
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
                <h3 className="text-xs tracking-wide text-muted-foreground uppercase">Executions</h3>
                {data.executions.length ? data.executions.map((e) => <ExecutionItem key={e.id} e={e} />) : <Empty>No executions yet.</Empty>}
              </section>
              <section className="space-y-2">
                <h3 className="text-xs tracking-wide text-muted-foreground uppercase">Memory history</h3>
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
                <h3 className="text-xs tracking-wide text-muted-foreground uppercase">Reputation</h3>
                {data.reputation_events.map((r, i) => (
                  <div key={i} className="flex items-center gap-2 text-sm">
                    <span className={cn("w-10 font-mono", r.delta > 0 ? "text-ok" : "text-bad")}>{r.delta > 0 ? `+${r.delta}` : r.delta}</span>
                    <span className="flex-1 text-muted-foreground">{r.reason.replaceAll("_", " ")}</span>
                    <span className="text-[11px] text-muted-foreground">{timeAgo(r.created_at)}</span>
                  </div>
                ))}
              </section>
              <section className="space-y-2">
                <h3 className="text-xs tracking-wide text-muted-foreground uppercase">On-chain identity (contract read)</h3>
                <pre className="overflow-x-auto rounded-md border bg-background/60 p-3 font-mono text-[11px] text-muted-foreground">{JSON.stringify(data.onchain, null, 2)}</pre>
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
        title="Agent Swarm"
        description="Three independent agents with their own NEAR identities and API credentials. They only coordinate through the SwarmMemory API."
      />
      <div className="grid gap-4 lg:grid-cols-3">
        {data ? data.map((a) => <AgentCard key={a.id} a={a} onOpen={() => setOpen(a.id)} />) : Array.from({ length: 3 }).map((_, i) => <Card key={i} className="h-96 animate-pulse" />)}
      </div>
      <AgentSheet id={open} onClose={() => setOpen(null)} />
    </>
  );
}
