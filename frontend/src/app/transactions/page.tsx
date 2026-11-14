"use client";

import { useState } from "react";

import { PageHeader } from "@/components/app-shell";
import { AgentGlyph, ChainTag, Empty, Mono, StatusBadge, TxHash } from "@/components/bits";
import { Card, CardContent } from "@/components/ui/card";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { Tx } from "@/lib/api";
import { clock, nearAmount } from "@/lib/format";
import { useConfig, useLive } from "@/lib/hooks";

const METHODS = ["register_agent", "publish_memory", "record_verification", "purchase_memory", "withdraw_rewards", "update_reputation"];

export default function TransactionsPage() {
  const { data: config } = useConfig();
  const [method, setMethod] = useState("all");
  const [status, setStatus] = useState("all");
  const [sel, setSel] = useState<Tx | null>(null);
  const q = new URLSearchParams({ limit: "300" });
  if (method !== "all") q.set("method", method);
  if (status !== "all") q.set("status", status);
  const { data } = useLive<Tx[]>(`/transactions?${q}`, 2500);
  const sim = config?.network === "simulated";

  return (
    <>
      <PageHeader
        eyebrow="Ledger"
        title="Transaction Explorer"
        description={
          sim
            ? "Demo mode: these are SIMULATED contract calls (sim_ hashes) executed against a local mirror of the contract. They are never shown alongside real transactions."
            : `Real NEAR ${config?.near_network_id ?? ""} transactions to ${config?.contract_id ?? ""}. A transaction is only marked confirmed once its FINAL outcome is successful.`
        }
        actions={
          <>
            <Select value={method} onValueChange={setMethod}>
              <SelectTrigger className="h-9! w-48 rounded-full bg-card">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All methods</SelectItem>
                {METHODS.map((m) => (
                  <SelectItem key={m} value={m}>
                    {m}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select value={status} onValueChange={setStatus}>
              <SelectTrigger className="h-9! w-36 rounded-full bg-card">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Any status</SelectItem>
                <SelectItem value="confirmed">confirmed</SelectItem>
                <SelectItem value="pending">pending</SelectItem>
                <SelectItem value="failed">failed</SelectItem>
              </SelectContent>
            </Select>
          </>
        }
      />
      <Card>
        <CardContent>
          {!data ? (
            <div className="h-60 animate-pulse rounded-lg bg-muted/40" />
          ) : !data.length ? (
            <Empty>No transactions yet.</Empty>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Time</TableHead>
                  <TableHead>Tx hash</TableHead>
                  <TableHead>Method</TableHead>
                  <TableHead>Signer</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">Deposit</TableHead>
                  <TableHead>Memory</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.map((t) => (
                  <TableRow key={t.id} className="cursor-pointer" onClick={() => setSel(t)}>
                    <TableCell className="font-mono text-xs text-muted-foreground">{clock(t.created_at)}</TableCell>
                    <TableCell onClick={(e) => e.stopPropagation()}>
                      <div className="flex items-center gap-2">
                        <ChainTag simulated={t.simulated} />
                        <TxHash hash={t.tx_hash} url={t.explorer_url} />
                      </div>
                    </TableCell>
                    <TableCell>
                      <Mono className="rounded-md bg-surface px-1.5 py-0.5 ring-1 ring-border/70">{t.method}</Mono>
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        {t.agent_id && t.initiated_by === "agent" ? <AgentGlyph id={t.agent_id} size="sm" /> : null}
                        <Mono className="text-muted-foreground">{t.signer_id}</Mono>
                        {t.initiated_by !== "agent" && <span className="text-[10px] text-muted-foreground uppercase">{t.initiated_by}</span>}
                      </div>
                    </TableCell>
                    <TableCell>
                      <StatusBadge status={t.status} />
                      {t.error && <div className="mt-1 max-w-56 truncate text-[11px] text-bad" title={t.error}>{t.error}</div>}
                    </TableCell>
                    <TableCell className="text-right font-mono text-xs">{Number(t.deposit_near) > 0 ? nearAmount(t.deposit_near) : "—"}</TableCell>
                    <TableCell>
                      <Mono className="text-muted-foreground">{t.memory_id ?? "—"}</Mono>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
      <Dialog open={!!sel} onOpenChange={(o) => !o && setSel(null)}>
        <DialogContent className="sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Mono className="text-base">{sel?.method}</Mono> {sel && <StatusBadge status={sel.status} />}
            </DialogTitle>
          </DialogHeader>
          {sel && <pre className="max-h-[60vh] overflow-auto rounded-xl bg-surface p-3 font-mono ring-1 ring-border text-[11px] text-muted-foreground">{JSON.stringify(sel, null, 2)}</pre>}
        </DialogContent>
      </Dialog>
    </>
  );
}
