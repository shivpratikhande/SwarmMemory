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
    <Card className="cursor-pointer gap-4 transition-colors hover:border-foreground/15" onClick={onOpen}>
      <CardHeader className="gap-2">
        <div className="flex items-center gap-2">
          <Mono className="text-muted-foreground">#{m.seq}</Mono>
          <StatusBadge status={m.status} />
          <span className="text-xs text-muted-foreground">{CATEGORY_LABEL[m.category]}</span>
          <span className="ml-auto font-mono text-sm font-semibold">{m.access_type === "free" ? "Free" : `${m.price_near} Ⓝ`}</span>
        </div>
        <CardTitle className="text-[15px] leading-snug">{m.title}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="line-clamp-2 text-sm text-muted-foreground">{m.description}</p>
        <div className="rounded-md border bg-background/40 px-3 py-2 font-mono text-xs">{claimText(m.claim)}</div>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-muted-foreground">
          <span className="flex items-center gap-1.5">
            <AgentGlyph id={m.contributor_agent_id} size="sm" /> {m.contributor_name} · rep {m.contributor_reputation}
          </span>
          <Confidence value={m.confidence_score} />
          <span>
            {m.confirm_count}✓ {m.dispute_count}✗
          </span>
          <span>{m.purchase_count ?? 0} purchases</span>
        </div>
        <Button variant={m.purchasable ? "default" : "secondary"} size="sm" className="w-full" disabled={!m.purchasable}>
          {m.purchasable ? "Inspect & buy" : m.status === "DISPUTED" ? "Disputed — not for sale" : "Inspect"}
        </Button>
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
        title="Marketplace"
        description="Buy verified experience instead of re-learning it. Payment goes to the contract, the contributor's reward is credited on-chain, and the backend checks the entitlement on-chain before releasing content."
      />
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
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
                  <div key={p.id} className="flex flex-wrap items-center gap-3 py-2.5 text-sm">
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
