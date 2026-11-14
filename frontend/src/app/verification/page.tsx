"use client";

import { FileCheck2Icon, HourglassIcon, Loader2Icon, ShieldCheckIcon, ShieldXIcon } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { PageHeader } from "@/components/app-shell";
import { AgentGlyph, Empty, Mono, Stat, StatusBadge } from "@/components/bits";
import { MemoryDialog, RequestGrid } from "@/components/memory-dialog";
import { MemoryTable } from "@/components/memory-table";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { post, type ActivityEvent, type Memory, type VerificationRecord } from "@/lib/api";
import { claimText, pct, timeAgo } from "@/lib/format";
import { useLive } from "@/lib/hooks";

export default function VerificationCenter() {
  const { data: queue } = useLive<Memory[]>("/verification/queue", 2500);
  const { data: history } = useLive<VerificationRecord[]>("/verification/history", 2500);
  const { data: disputed } = useLive<Memory[]>("/memories?status=DISPUTED", 3000);
  const { data: feed } = useLive<ActivityEvent[]>("/dashboard/activity?limit=200", 2500);
  const [open, setOpen] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  async function trigger(memoryId?: string) {
    setBusy(memoryId ?? "all");
    try {
      await post("/verification/run", memoryId ? { memory_id: memoryId } : {});
      toast.success("Verification Agent dispatched — it will re-run the experiment independently");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed");
    } finally {
      setBusy(null);
    }
  }

  const confirmed = history?.filter((h) => h.verification_result === "CONFIRMED").length ?? 0;
  const verifierActivity = feed?.filter((e) => e.agent_id === "agent-b-verifier" && !e.onchain).slice(0, 8) ?? [];

  return (
    <>
      <PageHeader
        eyebrow="Knowledge"
        title="Verification Center"
        description="Every verification is an independent re-run of the claimed experiment. The backend recomputes the verdict from the verifier's own raw evidence and rejects anything that doesn't add up."
        actions={
          <Button onClick={() => trigger()} disabled={!!busy || !queue?.length} className="rounded-full px-4">
            {busy === "all" ? <Loader2Icon className="animate-spin" /> : <ShieldCheckIcon />} Verify pending queue
          </Button>
        }
      />
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <Stat label="Awaiting verification" value={queue?.length ?? "—"} icon={HourglassIcon} tone="warn" />
        <Stat label="Verifications submitted" value={history?.length ?? "—"} icon={FileCheck2Icon} tone="ember" />
        <Stat label="Confirmed" value={confirmed} icon={ShieldCheckIcon} tone="ok" />
        <Stat label="Disputed memories" value={disputed?.length ?? "—"} icon={ShieldXIcon} tone="bad" />
      </div>

      <div className="mt-6 grid gap-6 2xl:grid-cols-[1.6fr_1fr]">
        <Card>
          <CardHeader>
            <CardTitle>Pending & expired memories</CardTitle>
            <CardDescription>Expired memories passed their revalidation window and need a fresh independent test.</CardDescription>
          </CardHeader>
          <CardContent>
            <MemoryTable
              rows={queue}
              onOpen={setOpen}
              extra={(m) => (
                <Button size="sm" variant="secondary" onClick={() => trigger(m.memory_id)} disabled={!!busy}>
                  {busy === m.memory_id ? <Loader2Icon className="animate-spin" /> : null} Verify
                </Button>
              )}
            />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Verification agent activity</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {verifierActivity.length ? (
              verifierActivity.map((e) => (
                <div key={e.id} className="flex gap-2.5 text-[13px] leading-snug">
                  <AgentGlyph id="agent-b-verifier" size="sm" />
                  <span className="flex-1">{e.message}</span>
                  <span className="shrink-0 text-[11px] text-muted-foreground">{timeAgo(e.created_at)}</span>
                </div>
              ))
            ) : (
              <Empty icon={ShieldCheckIcon}>The verification agent has not run yet.</Empty>
            )}
          </CardContent>
        </Card>
      </div>

      <Card className="mt-6">
        <CardHeader>
          <CardTitle>Verification history</CardTitle>
          <CardDescription>Append-only. Each record carries the verifier&apos;s own request-level evidence and its on-chain record.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {!history?.length && <Empty icon={ShieldCheckIcon}>No verifications yet.</Empty>}
          {history?.map((v) => (
            <div key={v.id} className="grid gap-3 rounded-xl bg-surface/70 p-4 ring-1 ring-border md:grid-cols-[1fr_auto]">
              <div className="space-y-2">
                <div className="flex flex-wrap items-center gap-2">
                  {v.verification_result === "CONFIRMED" ? <ShieldCheckIcon className="size-4 text-ok" /> : <ShieldXIcon className="size-4 text-bad" />}
                  <StatusBadge status={v.verification_result} />
                  <button className="text-sm font-medium hover:underline" onClick={() => setOpen(v.memory_id)}>
                    #{v.memory_seq} {v.memory_title}
                  </button>
                  {v.memory_status && <StatusBadge status={v.memory_status} />}
                </div>
                <div className="text-xs text-muted-foreground">
                  Claim <Mono>{claimText(v.claim)}</Mono> (observed {pct(v.claim?.observed)}) · independent re-run measured{" "}
                  <span className="text-foreground">{pct(v.observed_value)}</span> over {v.verification_evidence.requests.length} requests
                </div>
                <RequestGrid requests={v.verification_evidence.requests} />
              </div>
              <div className="flex items-start gap-2 text-xs text-muted-foreground md:flex-col md:items-end">
                <span className="flex items-center gap-1.5">
                  <AgentGlyph id={v.verifier_agent_id} size="sm" /> {v.verifier_name}
                </span>
                <span>{timeAgo(v.verified_at)}</span>
              </div>
            </div>
          ))}
        </CardContent>
      </Card>
      <MemoryDialog memoryId={open} onOpenChange={(o) => !o && setOpen(null)} />
    </>
  );
}
