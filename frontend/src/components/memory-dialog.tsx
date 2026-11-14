"use client";

import { LockIcon, ShieldCheckIcon, ShieldXIcon } from "lucide-react";
import { useState } from "react";
import useSWR from "swr";

import { AgentGlyph, ChainTag, Confidence, Empty, Mono, StatusBadge, TxHash } from "@/components/bits";
import { PurchaseButton } from "@/components/purchase-button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { fetcher, type Evidence, type Memory, type MemoryDetails } from "@/lib/api";
import { CATEGORY_LABEL, claimText, pct, shortHash, timeAgo } from "@/lib/format";
import { cn } from "@/lib/utils";

export function RequestGrid({ requests, className }: { requests: Evidence["requests"]; className?: string }) {
  return (
    <div className={cn("flex flex-wrap gap-1", className)}>
      {requests.map((r) => {
        const ok = r.status >= 200 && r.status < 300;
        return (
          <span
            key={r.index}
            title={`#${r.index} → ${r.status} (${r.latency_ms} ms)`}
            className={cn("size-3.5 rounded-[3px] border", ok ? "border-ok/40 bg-ok/25" : "border-bad/50 bg-bad/40")}
          />
        );
      })}
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1">
      <div className="text-[11px] font-medium tracking-wide text-muted-foreground uppercase">{label}</div>
      <div className="text-sm">{children}</div>
    </div>
  );
}

function EvidenceView({ ev }: { ev: Evidence }) {
  const fails = ev.requests.filter((r) => r.status >= 400).length;
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
        <span>
          run <Mono className="text-foreground">{ev.run_id}</Mono>
        </span>
        <span>
          {ev.requests.length} requests · <span className="text-bad">{fails} failed</span>
        </span>
      </div>
      <RequestGrid requests={ev.requests} />
      {ev.logs?.length > 0 && (
        <ScrollArea className="h-40 rounded-xl bg-surface ring-1 ring-border/70">
          <pre className="p-3 font-mono text-[11px] leading-relaxed text-muted-foreground">{ev.logs.join("\n")}</pre>
        </ScrollArea>
      )}
    </div>
  );
}

export function MemoryDialog({ memoryId, onOpenChange, unlocked }: { memoryId: string | null; onOpenChange: (o: boolean) => void; unlocked?: Memory | null }) {
  const { data } = useSWR<MemoryDetails>(memoryId ? `/memories/${memoryId}/details` : null, fetcher, { refreshInterval: 3000 });
  const { data: chain } = useSWR<Record<string, unknown> | null>(memoryId ? `/memories/${memoryId}/onchain` : null, fetcher, { refreshInterval: 5000 });
  const [bought, setBought] = useState<Memory | null>(null);
  const m = data?.memory;
  const full = unlocked?.evidence ? unlocked : bought?.memory_id === memoryId ? bought : null;

  return (
    <Dialog open={!!memoryId} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[88vh] overflow-hidden p-0 sm:max-w-3xl">
        {!m ? (
          <div className="h-64 animate-pulse" />
        ) : (
          <ScrollArea className="max-h-[88vh]">
            <div className="space-y-5 p-6">
              <DialogHeader className="space-y-2 text-left">
                <div className="flex flex-wrap items-center gap-2">
                  <Mono className="text-muted-foreground">#{m.seq}</Mono>
                  <StatusBadge status={m.status} />
                  <span className="text-xs text-muted-foreground">{CATEGORY_LABEL[m.category] ?? m.category}</span>
                  {m.version > 1 && <span className="text-xs text-muted-foreground">· v{m.version}</span>}
                </div>
                <DialogTitle className="text-xl leading-snug font-semibold">{m.title}</DialogTitle>
                <DialogDescription>{m.description}</DialogDescription>
              </DialogHeader>

              <div className="grid grid-cols-2 gap-4 rounded-xl bg-surface ring-1 ring-border/70 p-4 sm:grid-cols-4">
                <Field label="Confidence">
                  <Confidence value={m.confidence_score} />
                </Field>
                <Field label="Verifications">
                  <span className="tabular-nums">
                    <span className="text-ok">{m.confirm_count}✓</span> <span className="text-bad">{m.dispute_count}✗</span>
                  </span>
                </Field>
                <Field label="Used by">{m.usage_count} agents</Field>
                <Field label="Price">{m.access_type === "free" ? "Free" : `${m.price_near} Ⓝ`}</Field>
              </div>

              <Tabs defaultValue="claim">
                <TabsList>
                  <TabsTrigger value="claim">Claim</TabsTrigger>
                  <TabsTrigger value="evidence">Evidence</TabsTrigger>
                  <TabsTrigger value="verifications">Verifications ({data.verifications.length})</TabsTrigger>
                  <TabsTrigger value="ledger">Ledger</TabsTrigger>
                </TabsList>

                <TabsContent value="claim" className="space-y-4 pt-3">
                  <div className="rounded-xl bg-surface ring-1 ring-border/70 p-4">
                    <div className="mb-2 text-[11px] tracking-wide text-muted-foreground uppercase">Falsifiable claim (public)</div>
                    <div className="font-mono text-sm">{claimText(m.claim)}</div>
                    <div className="mt-2 text-xs text-muted-foreground">
                      observed {pct(m.claim.observed)} over {m.claim.sample_size} requests · endpoint <Mono>{m.claim.endpoint}</Mono>
                    </div>
                  </div>
                  <div className="grid gap-4 sm:grid-cols-2">
                    <Field label="Contributor">
                      <div className="flex items-center gap-2">
                        <AgentGlyph id={m.contributor_agent_id} size="sm" />
                        <span>{m.contributor_name}</span>
                        <span className="text-xs text-muted-foreground">rep {m.contributor_reputation}</span>
                      </div>
                      <Mono className="text-muted-foreground">{m.contributor_account}</Mono>
                    </Field>
                    <Field label="Timeline">
                      <div className="text-xs text-muted-foreground">
                        created {timeAgo(m.created_at)} · last verified {timeAgo(m.last_verified_at)}
                      </div>
                    </Field>
                    <Field label="Evidence hash">
                      <Mono className="break-all text-muted-foreground">{m.evidence_hash}</Mono>
                    </Field>
                    <Field label="Metadata hash">
                      <Mono className="break-all text-muted-foreground">{m.metadata_hash}</Mono>
                    </Field>
                  </div>
                  {m.tags.length > 0 && (
                    <div className="flex flex-wrap gap-1.5">
                      {m.tags.map((t) => (
                        <span key={t} className="rounded-full bg-muted px-2 py-0.5 text-[11px] text-muted-foreground">
                          {t}
                        </span>
                      ))}
                    </div>
                  )}
                </TabsContent>

                <TabsContent value="evidence" className="space-y-4 pt-3">
                  {full?.evidence ? (
                    <>
                      <Field label="Original observation">{full.original_observation}</Field>
                      <Field label="Execution context">
                        <pre className="overflow-x-auto rounded-xl bg-surface ring-1 ring-border/70 p-3 font-mono text-[11px] text-muted-foreground">
                          {JSON.stringify(full.execution_context, null, 2)}
                        </pre>
                      </Field>
                      <EvidenceView ev={full.evidence} />
                    </>
                  ) : (
                    <div className="flex flex-col items-center gap-3 rounded-xl border border-dashed bg-surface/60 px-6 py-10 text-center">
                      <LockIcon className="size-5 text-muted-foreground" />
                      <div className="text-sm">The observation, execution context and raw evidence are paid content.</div>
                      <div className="max-w-md text-xs text-muted-foreground">
                        Access is granted only after the backend confirms an on-chain entitlement (<Mono>has_access</Mono>). Its integrity can be checked
                        against the evidence hash registered on-chain: <Mono>{shortHash(m.evidence_hash, 8)}</Mono>
                      </div>
                      {m.access_type === "paid" && <PurchaseButton memory={m} onUnlocked={setBought} />}
                    </div>
                  )}
                </TabsContent>

                <TabsContent value="verifications" className="space-y-3 pt-3">
                  {data.verifications.length === 0 && <Empty>No independent verification yet.</Empty>}
                  {data.verifications.map((v) => (
                    <div key={v.id} className="space-y-3 rounded-xl bg-surface ring-1 ring-border/70 p-4">
                      <div className="flex flex-wrap items-center gap-2">
                        {v.verification_result === "CONFIRMED" ? <ShieldCheckIcon className="size-4 text-ok" /> : <ShieldXIcon className="size-4 text-bad" />}
                        <StatusBadge status={v.verification_result} />
                        <AgentGlyph id={v.verifier_agent_id} size="sm" />
                        <span className="text-sm">{v.verifier_name}</span>
                        <span className="ml-auto text-xs text-muted-foreground">{timeAgo(v.verified_at)}</span>
                      </div>
                      <div className="text-xs text-muted-foreground">
                        Independent re-run measured <span className="text-foreground">{pct(v.observed_value)}</span> vs claimed {pct(m.claim.observed)}. {v.notes}
                      </div>
                      <EvidenceView ev={v.verification_evidence} />
                      <div className="flex items-center gap-2 text-xs text-muted-foreground">
                        evidence hash <Mono>{shortHash(v.evidence_hash, 8)}</Mono>
                        {(() => {
                          const tx = data.transactions.find((t) => t.id === v.onchain_tx_id);
                          return tx ? (
                            <>
                              · <ChainTag simulated={tx.simulated} /> <TxHash hash={tx.tx_hash} url={tx.explorer_url} />
                            </>
                          ) : null;
                        })()}
                      </div>
                    </div>
                  ))}
                </TabsContent>

                <TabsContent value="ledger" className="space-y-4 pt-3">
                  <Field label="On-chain record (live contract read)">
                    <pre className="overflow-x-auto rounded-xl bg-surface ring-1 ring-border/70 p-3 font-mono text-[11px] text-muted-foreground">
                      {chain === undefined ? "loading…" : JSON.stringify(chain, null, 2)}
                    </pre>
                  </Field>
                  <Field label={`Purchase history (${data.purchases.length})`}>
                    {data.purchases.length === 0 ? (
                      <span className="text-xs text-muted-foreground">No purchases yet.</span>
                    ) : (
                      <ul className="space-y-1">
                        {data.purchases.map((p, i) => (
                          <li key={i} className="flex items-center gap-2 text-xs">
                            <Mono>{p.buyer_account_id}</Mono>
                            <span className="text-muted-foreground">paid {p.price_near} Ⓝ · {timeAgo(p.created_at)}</span>
                          </li>
                        ))}
                      </ul>
                    )}
                  </Field>
                  <Field label="Transactions">
                    <ul className="space-y-1.5">
                      {data.transactions.map((t) => (
                        <li key={t.id} className="flex flex-wrap items-center gap-2 text-xs">
                          <ChainTag simulated={t.simulated} />
                          <Mono>{t.method}</Mono>
                          <StatusBadge status={t.status} />
                          <span className="text-muted-foreground">{t.signer_id}</span>
                          <span className="ml-auto">
                            <TxHash hash={t.tx_hash} url={t.explorer_url} />
                          </span>
                        </li>
                      ))}
                    </ul>
                  </Field>
                  {data.versions.length > 0 && (
                    <Field label="Versions">
                      <ul className="space-y-1 text-xs text-muted-foreground">
                        {data.versions.map((v) => (
                          <li key={v.version}>
                            v{v.version} · {v.reason} · {timeAgo(v.created_at)}
                          </li>
                        ))}
                        {data.lineage.map((l) => (
                          <li key={l.memory_id}>
                            supersedes <Mono>{l.memory_id}</Mono> (v{l.version}, {l.status})
                          </li>
                        ))}
                      </ul>
                    </Field>
                  )}
                </TabsContent>
              </Tabs>
            </div>
          </ScrollArea>
        )}
      </DialogContent>
    </Dialog>
  );
}
