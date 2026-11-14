"use client";

import { CoinsIcon, Loader2Icon, ShoppingBagIcon, TrendingUpIcon, UsersIcon } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { PageHeader } from "@/components/app-shell";
import { AgentGlyph, ChainTag, Empty, Mono, Stat, StatusBadge, TxHash } from "@/components/bits";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { post, type Economy, type Purchase, type Tx } from "@/lib/api";
import { nearAmount, timeAgo } from "@/lib/format";
import { useLive } from "@/lib/hooks";
import { cn } from "@/lib/utils";

const RULES: [string, string][] = [
  ["+5", "memory independently confirmed (per new verifier)"],
  ["−8", "memory disputed by an independent verifier"],
  ["+1", "evidence-backed verification submitted"],
  ["+3", "memory reported helpful by an agent that used it"],
  ["−2", "memory reported unhelpful"],
  ["−2", "duplicate publication attempt"],
];

export default function EconomyPage() {
  const { data } = useLive<Economy>("/dashboard/economy", 3000);
  const { data: purchases } = useLive<Purchase[]>("/marketplace/purchases", 3000);
  const { data: txs } = useLive<Tx[]>("/transactions?limit=12", 3000);
  const [busy, setBusy] = useState<string | null>(null);

  async function withdraw(id: string) {
    setBusy(id);
    try {
      const r = await post<{ amount_near: string }>(`/agents/${id}/withdraw`);
      toast.success(`Withdrew ${r.amount_near} Ⓝ (confirmed on-chain)`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Withdrawal failed");
    } finally {
      setBusy(null);
    }
  }

  const sim = data?.network === "simulated";
  const ranked = data ? [...data.agents].sort((a, b) => b.reputation - a.reputation) : [];

  return (
    <>
      <PageHeader
        eyebrow="Ledger"
        title="Network Economy"
        description="Contributors are credited inside the contract when their memory is bought, and withdraw with a pull payment: the balance is zeroed before the transfer and restored if it fails."
      />
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <Stat label="Value moved" value={data ? `${data.total_value_moved_near} Ⓝ` : "—"} icon={CoinsIcon} tone="chain" hint="Confirmed transactions only" />
        <Stat label="Memory purchases" value={purchases?.length ?? "—"} icon={ShoppingBagIcon} tone="ember" />
        <Stat label="Earning contributors" value={data?.agents.filter((a) => Number(a.total_earned_onchain_near ?? 0) > 0).length ?? "—"} icon={UsersIcon} tone="ok" />
        <Stat label="Reputation events" value={data?.reputation_events.length ?? "—"} icon={TrendingUpIcon} tone="warn" />
      </div>

      <Card className="mt-6">
        <CardHeader>
          <CardTitle>Agent earnings & spending</CardTitle>
          <CardDescription>Claimable and lifetime earnings are live contract reads ({data?.network ?? "…"}).</CardDescription>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Agent</TableHead>
                <TableHead>Account</TableHead>
                <TableHead className="text-right">Spent</TableHead>
                <TableHead className="text-right">Earned (lifetime)</TableHead>
                <TableHead className="text-right">Claimable</TableHead>
                {sim && <TableHead className="text-right">Sim. balance</TableHead>}
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {data?.agents.map((a) => (
                <TableRow key={a.id}>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <AgentGlyph id={a.id} role={a.role} size="sm" /> <span className="font-medium">{a.name.split(" · ")[0]}</span>
                    </div>
                  </TableCell>
                  <TableCell>
                    <Mono className="text-muted-foreground">{a.near_account_id}</Mono>
                  </TableCell>
                  <TableCell className="text-right font-mono text-xs">{a.spent_near} Ⓝ</TableCell>
                  <TableCell className="text-right font-mono text-xs">{a.total_earned_onchain_near ?? "—"} Ⓝ</TableCell>
                  <TableCell className="text-right font-mono text-xs font-medium text-chain">{a.claimable_near ?? "—"} Ⓝ</TableCell>
                  {sim && <TableCell className="text-right font-mono text-xs text-muted-foreground">{a.wallet_balance_near} Ⓝ</TableCell>}
                  <TableCell className="text-right">
                    <Button size="sm" variant="outline" className="rounded-full" disabled={!a.claimable_near || Number(a.claimable_near) === 0 || busy === a.id} onClick={() => withdraw(a.id)}>
                      {busy === a.id && <Loader2Icon className="animate-spin" />} Withdraw
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Reputation ranking</CardTitle>
            <CardDescription>Simple, published rules — not Sybil-resistant; agents cannot verify, buy or rate their own memories.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <ol className="space-y-2">
              {ranked.map((a, i) => (
                <li key={a.id} className="flex items-center gap-3 rounded-xl px-2 py-1.5 even:bg-surface/60">
                  <span className={cn("grid size-6 place-items-center rounded-full text-xs font-semibold", i === 0 ? "bg-primary/15 text-primary" : "bg-muted text-muted-foreground")}>{i + 1}</span>
                  <AgentGlyph id={a.id} role={a.role} size="sm" />
                  <span className="flex-1 text-sm">{a.name}</span>
                  <span className={cn("font-mono text-sm", a.reputation < 0 ? "text-bad" : "text-ok")}>{a.reputation}</span>
                </li>
              ))}
            </ol>
            <div className="grid grid-cols-[2.5rem_1fr] gap-x-2 gap-y-1.5 rounded-xl bg-surface p-3.5 text-xs text-muted-foreground ring-1 ring-border/70">
              {RULES.map(([p, r]) => (
                <div key={r} className="contents">
                  <span className={cn("font-mono", p.startsWith("+") ? "text-ok" : "text-bad")}>{p}</span>
                  <span>{r}</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Recent reputation changes</CardTitle>
          </CardHeader>
          <CardContent>
            {!data?.reputation_events.length ? (
              <Empty>No reputation changes yet.</Empty>
            ) : (
              <ul className="space-y-2">
                {data.reputation_events.slice(0, 14).map((r, i) => (
                  <li key={i} className="flex items-center gap-3 text-sm">
                    <AgentGlyph id={r.agent_id} size="sm" />
                    <span className={cn("w-8 font-mono", r.delta > 0 ? "text-ok" : "text-bad")}>{r.delta > 0 ? `+${r.delta}` : r.delta}</span>
                    <span className="flex-1 text-muted-foreground">{r.reason.replaceAll("_", " ")}</span>
                    {r.memory_id && <Mono className="text-muted-foreground">{r.memory_id}</Mono>}
                    <span className="text-[11px] text-muted-foreground">{timeAgo(r.created_at)}</span>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </div>

      <Card className="mt-6">
        <CardHeader>
          <CardTitle>Recent NEAR transactions</CardTitle>
        </CardHeader>
        <CardContent className="divide-y">
          {txs?.map((t) => (
            <div key={t.id} className="flex flex-wrap items-center gap-3 py-2.5 text-sm">
              <ChainTag simulated={t.simulated} />
              <Mono>{t.method}</Mono>
              <StatusBadge status={t.status} />
              <span className="text-xs text-muted-foreground">{t.signer_id}</span>
              {Number(t.deposit_near) > 0 && <span className="font-mono text-xs text-chain">{nearAmount(t.deposit_near)}</span>}
              <span className="ml-auto">
                <TxHash hash={t.tx_hash} url={t.explorer_url} />
              </span>
            </div>
          ))}
        </CardContent>
      </Card>
    </>
  );
}
