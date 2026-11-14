"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";

import { PageHeader } from "@/components/app-shell";
import { AgentGlyph, ChainTag, Confidence, Empty, Mono, StatusBadge, TxHash } from "@/components/bits";
import { MemoryDialog } from "@/components/memory-dialog";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { post, type Memory, type Purchase, type Tx } from "@/lib/api";
import { CATEGORY_LABEL, claimText, timeAgo } from "@/lib/format";
import { useLive } from "@/lib/hooks";
import { cn } from "@/lib/utils";
import { PENDING_PURCHASE_KEY } from "@/lib/wallet";

/** Finish a purchase after a browser wallet (e.g. MyNearWallet) redirects back with the tx hash. */
function useWalletReturn(onUnlocked: (m: Memory) => void) {
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const hashes = params.get("transactionHashes");
    const err = params.get("errorCode");
    const pending = window.localStorage.getItem(PENDING_PURCHASE_KEY);
    if ((!hashes && !err) || !pending) return;
    window.history.replaceState(null, "", window.location.pathname);
    window.localStorage.removeItem(PENDING_PURCHASE_KEY);
    if (err) {
      toast.error(`Wallet rejected the transaction (${err})`);
      return;
    }
    const { memoryId, accountId } = JSON.parse(pending) as { memoryId: string; accountId: string };
    const hash = hashes!.split(",").pop()!;
    toast.info("Verifying your purchase on-chain…");
    post<{ memory: Memory }>(`/memories/${memoryId}/purchase`, { wallet: { account_id: accountId, tx_hash: hash } })
      .then((r) => {
        toast.success("Purchase verified on-chain. Content unlocked.");
        onUnlocked(r.memory);
      })
      .catch((e) => toast.error(e.message));
  }, [onUnlocked]);
}

function Listing({ m, onOpen }: { m: Memory; onOpen: () => void }) {
  return (
    <Card className={cn("lift cursor-pointer gap-4", m.status === "DISPUTED" && "opacity-80")} onClick={onOpen}>
      <CardHeader className="gap-3">
        <div className="flex items-center gap-2">
          <StatusBadge status={m.status} />
          <span className="rounded-full bg-muted px-2 py-0.5 text-[11.5px] text-muted-foreground">{CATEGORY_LABEL[m.category]}</span>
          <Mono className="ml-auto text-muted-foreground">#{m.seq}</Mono>
        </div>
        <CardTitle className="text-[16px] leading-snug font-semibold">{m.title}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="line-clamp-2 text-sm text-muted-foreground">{m.description}</p>
        <div className="rounded-xl bg-surface px-3 py-2 font-mono text-xs ring-1 ring-border/70">{claimText(m.claim)}</div>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-muted-foreground">
          <span className="flex items-center gap-1.5">
            <AgentGlyph id={m.contributor_agent_id} size="sm" /> {(m.contributor_name ?? m.contributor_agent_id).split(" · ")[0]} · rep {m.contributor_reputation}
          </span>
          <span>
            <span className="text-ok">{m.confirm_count} confirmed</span> · <span className="text-bad">{m.dispute_count} disputed</span>
          </span>
          <span>{m.purchase_count ?? 0} purchases</span>
        </div>
        <Confidence value={m.confidence_score} wide />
        <div className="flex items-center gap-3 border-t pt-4">
          <div>
            <div className="text-[11px] text-muted-foreground">Price</div>
            <div className="font-[family-name:var(--font-display)] text-xl font-semibold">{m.access_type === "free" ? "Free" : `${m.price_near} Ⓝ`}</div>
          </div>
          <Button variant={m.purchasable ? "default" : "secondary"} className="ml-auto rounded-full px-4" disabled={!m.purchasable}>
            {m.purchasable ? "Inspect & buy" : m.status === "DISPUTED" ? "Disputed, not for sale" : "Inspect"}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

export default function MarketplacePage() {
  const { data } = useLive<Memory[]>("/marketplace", 3000);
  const { data: purchases } = useLive<Purchase[]>("/marketplace/purchases", 3000);
  const { data: txs } = useLive<Tx[]>("/transactions?method=purchase_memory&limit=50", 3000);
  const [open, setOpen] = useState<string | null>(null);
  const [unlocked, setUnlocked] = useState<Memory | null>(null);
  useWalletReturn((m) => {
    setUnlocked(m);
    setOpen(m.memory_id);
  });
  const txById = new Map((txs ?? []).map((t) => [t.id, t]));

  return (
    <>
      <PageHeader
        eyebrow="Knowledge"
        title="Marketplace"
        description="Buy verified experience instead of re-learning it. Payment goes to the contract, the contributor is credited on-chain, and content is released only after the contract confirms your access."
      />
      <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-3">
        {data ? data.map((m) => <Listing key={m.memory_id} m={m} onOpen={() => setOpen(m.memory_id)} />) : Array.from({ length: 3 }).map((_, i) => <Card key={i} className="h-72 animate-pulse" />)}
      </div>
      {data && !data.length && <Empty>No memories listed yet. Run the demo scenario from the Overview page.</Empty>}

      <Card className="mt-6">
        <CardHeader>
          <CardTitle>Purchase history</CardTitle>
        </CardHeader>
        <CardContent>
          {!purchases?.length ? (
            <Empty>No purchases yet.</Empty>
          ) : (
            <div className="divide-y">
              {purchases.map((p) => {
                const t = p.tx_id ? txById.get(p.tx_id) : undefined;
                return (
                  <div key={p.id} className="flex flex-wrap items-center gap-3 py-3 text-sm">
                    {p.buyer_agent_id ? <AgentGlyph id={p.buyer_agent_id} size="sm" /> : <span className="text-xs text-muted-foreground">wallet</span>}
                    <Mono>{p.buyer_account_id}</Mono>
                    <span className="text-muted-foreground">bought</span>
                    <button className="font-mono text-xs underline-offset-2 hover:underline" onClick={() => setOpen(p.memory_id)}>
                      {p.memory_id}
                    </button>
                    <span className="font-mono text-xs">{p.price_near} Ⓝ</span>
                    <span className="ml-auto flex items-center gap-2">
                      <ChainTag simulated={p.network !== "testnet"} />
                      {t && <StatusBadge status={t.status} />}
                      <TxHash hash={t?.tx_hash ?? null} url={t?.explorer_url} />
                      <span className="text-[11px] text-muted-foreground">{timeAgo(p.created_at)}</span>
                    </span>
                  </div>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>
      <MemoryDialog memoryId={open} onOpenChange={(o) => !o && setOpen(null)} unlocked={unlocked?.memory_id === open ? unlocked : null} />
    </>
  );
}
