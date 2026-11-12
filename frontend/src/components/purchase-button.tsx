"use client";

import { Loader2Icon, WalletIcon } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { post, type Memory } from "@/lib/api";
import { useConfig } from "@/lib/hooks";
import { useWallet } from "@/lib/wallet";

/**
 * Wallet purchase (testnet mode only): the browser wallet signs purchase_memory,
 * then the backend independently verifies the tx outcome and the contract
 * entitlement before releasing content. In demo mode, purchases are made by agents.
 */
export function PurchaseButton({ memory, onUnlocked }: { memory: Memory; onUnlocked?: (m: Memory) => void }) {
  const { data: config } = useConfig();
  const { enabled, accountId, signIn, purchase } = useWallet();
  const [busy, setBusy] = useState(false);

  if (!config) return null;
  if (!enabled)
    return (
      <p className="max-w-sm text-center text-xs text-muted-foreground">
        Demo mode: purchases are made by agents on the simulated chain. Switch to <span className="font-mono">SWARM_MODE=testnet</span> to buy with a NEAR
        wallet.
      </p>
    );
  if (memory.status === "DISPUTED") return <p className="text-xs text-bad">Disputed memories cannot be purchased.</p>;
  if (!accountId)
    return (
      <Button onClick={signIn}>
        <WalletIcon /> Connect wallet to buy
      </Button>
    );

  async function buy() {
    setBusy(true);
    try {
      const hash = await purchase(memory.memory_id, memory.price_yocto);
      if (!hash) return; // browser wallet redirected; the marketplace page finishes on return
      toast.info("Transaction signed. Verifying on-chain…");
      const res = await post<{ memory: Memory; tx_hash: string }>(`/memories/${memory.memory_id}/purchase`, { wallet: { account_id: accountId, tx_hash: hash } });
      toast.success("Purchase verified on-chain. Content unlocked.");
      onUnlocked?.(res.memory);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Purchase failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Button onClick={buy} disabled={busy}>
      {busy ? <Loader2Icon className="animate-spin" /> : <WalletIcon />}
      Buy for {memory.price_near} Ⓝ
    </Button>
  );
}
