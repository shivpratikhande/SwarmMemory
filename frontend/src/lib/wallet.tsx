"use client";

import type { WalletSelector } from "@near-wallet-selector/core";
import type { WalletSelectorModal } from "@near-wallet-selector/modal-ui";
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

import { useConfig } from "./hooks";

/**
 * NEAR Wallet Selector integration. Only active in testnet mode: the browser
 * signs `purchase_memory` itself; no private key ever reaches the frontend.
 */
interface WalletCtx {
  enabled: boolean;
  accountId: string | null;
  signIn: () => void;
  signOut: () => Promise<void>;
  /** Signs purchase_memory with an attached deposit. Returns the tx hash, or null if the wallet redirected. */
  purchase: (memoryId: string, priceYocto: string) => Promise<string | null>;
}

const Ctx = createContext<WalletCtx>({
  enabled: false,
  accountId: null,
  signIn: () => {},
  signOut: async () => {},
  purchase: async () => null,
});

export const PENDING_PURCHASE_KEY = "swarm.pendingPurchase";

export function WalletProvider({ children }: { children: React.ReactNode }) {
  const { data: config } = useConfig();
  const [selector, setSelector] = useState<WalletSelector | null>(null);
  const [modal, setModal] = useState<WalletSelectorModal | null>(null);
  const [accountId, setAccountId] = useState<string | null>(null);
  const enabled = !!config?.wallet_purchases_enabled;

  useEffect(() => {
    if (!enabled || !config) return;
    let unsub: (() => void) | undefined;
    (async () => {
      const [{ setupWalletSelector }, { setupModal }, { setupMyNearWallet }, { setupMeteorWallet }] = await Promise.all([
        import("@near-wallet-selector/core"),
        import("@near-wallet-selector/modal-ui"),
        import("@near-wallet-selector/my-near-wallet"),
        import("@near-wallet-selector/meteor-wallet"),
      ]);
      await import("@near-wallet-selector/modal-ui/styles.css");
      const sel = await setupWalletSelector({
        network: (config.near_network_id ?? "testnet") as "testnet",
        modules: [setupMyNearWallet(), setupMeteorWallet()],
      });
      const m = setupModal(sel, { contractId: config.contract_id, theme: "dark", description: "Sign in to buy memories on SwarmMemory" });
      const sub = sel.store.observable.subscribe((state) => setAccountId(state.accounts.find((a) => a.active)?.accountId ?? null));
      unsub = () => sub.unsubscribe();
      setSelector(sel);
      setModal(m);
    })();
    return () => unsub?.();
  }, [enabled, config]);

  const signIn = useCallback(() => modal?.show(), [modal]);
  const signOut = useCallback(async () => {
    if (!selector) return;
    const w = await selector.wallet();
    await w.signOut();
  }, [selector]);

  const purchase = useCallback(
    async (memoryId: string, priceYocto: string) => {
      if (!selector || !config) throw new Error("wallet not ready");
      const { actionCreators } = await import("@near-wallet-selector/core");
      const wallet = await selector.wallet();
      // Remember what we were buying in case a browser wallet redirects away.
      window.localStorage.setItem(PENDING_PURCHASE_KEY, JSON.stringify({ memoryId, accountId }));
      const outcome = await wallet.signAndSendTransaction({
        receiverId: config.contract_id,
        actions: [actionCreators.functionCall("purchase_memory", { memory_id: memoryId }, BigInt(30_000_000_000_000), BigInt(priceYocto))],
        // browser wallets (MyNearWallet) redirect here; injected wallets ignore it
        callbackUrl: `${window.location.origin}/marketplace`,
      });
      const hash = (outcome as { transaction?: { hash?: string } } | void)?.transaction?.hash ?? null;
      if (hash) window.localStorage.removeItem(PENDING_PURCHASE_KEY);
      return hash;
    },
    [selector, config, accountId],
  );

  const value = useMemo(() => ({ enabled, accountId, signIn, signOut, purchase }), [enabled, accountId, signIn, signOut, purchase]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export const useWallet = () => useContext(Ctx);
