"use client";

import {
  ActivityIcon,
  ArrowLeftRightIcon,
  BotIcon,
  BrainCircuitIcon,
  CoinsIcon,
  LayoutGridIcon,
  ShieldCheckIcon,
  StoreIcon,
  WalletIcon,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { Button } from "@/components/ui/button";
import { useConfig } from "@/lib/hooks";
import { cn } from "@/lib/utils";
import { useWallet } from "@/lib/wallet";

const NAV = [
  { href: "/", label: "Overview", icon: LayoutGridIcon },
  { href: "/agents", label: "Agent Swarm", icon: BotIcon },
  { href: "/memories", label: "Memory Explorer", icon: BrainCircuitIcon },
  { href: "/marketplace", label: "Marketplace", icon: StoreIcon },
  { href: "/verification", label: "Verification Center", icon: ShieldCheckIcon },
  { href: "/economy", label: "Network Economy", icon: CoinsIcon },
  { href: "/transactions", label: "Transactions", icon: ArrowLeftRightIcon },
  { href: "/activity", label: "Activity Feed", icon: ActivityIcon },
];

export function ModeBadge({ className }: { className?: string }) {
  const { data } = useConfig();
  if (!data) return null;
  const real = data.network === "testnet";
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 font-mono text-[11px] tracking-wide uppercase",
        real ? "border-chain/40 bg-chain/10 text-chain" : "border-sim/40 bg-sim/10 text-sim",
        className,
      )}
      title={real ? `Real NEAR ${data.near_network_id} transactions · contract ${data.contract_id}` : "Demo mode: simulated contract, no real transactions"}
    >
      <span className={cn("size-1.5 rounded-full", real ? "bg-chain" : "bg-sim")} />
      {real ? `NEAR ${data.near_network_id}` : "Demo · simulated chain"}
    </span>
  );
}

function WalletButton() {
  const { enabled, accountId, signIn, signOut } = useWallet();
  if (!enabled) return null;
  return accountId ? (
    <Button variant="outline" size="sm" onClick={() => signOut()} className="font-mono text-xs" title="Sign out">
      <WalletIcon /> {accountId}
    </Button>
  ) : (
    <Button size="sm" onClick={signIn}>
      <WalletIcon /> Connect wallet
    </Button>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const { data: config } = useConfig();
  return (
    <div className="flex min-h-screen">
      <aside className="sticky top-0 hidden h-screen w-60 shrink-0 flex-col border-r border-sidebar-border bg-sidebar md:flex">
        <div className="flex items-center gap-2.5 px-5 pt-5 pb-6">
          <div className="grid size-7 place-items-center rounded-md bg-primary/15 text-primary">
            <BrainCircuitIcon className="size-4" />
          </div>
          <div className="leading-tight">
            <div className="text-sm font-semibold tracking-tight">SwarmMemory</div>
            <div className="text-[11px] text-muted-foreground">Collective agent memory</div>
          </div>
        </div>
        <nav className="flex flex-col gap-0.5 px-3">
          {NAV.map(({ href, label, icon: Icon }) => {
            const active = href === "/" ? path === "/" : path.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                className={cn(
                  "flex items-center gap-2.5 rounded-md px-2.5 py-2 text-[13px] text-muted-foreground transition-colors hover:bg-accent hover:text-foreground",
                  active && "bg-accent text-foreground",
                )}
              >
                <Icon className={cn("size-4", active && "text-primary")} />
                {label}
              </Link>
            );
          })}
        </nav>
        <div className="mt-auto space-y-2 border-t border-sidebar-border p-4 text-[11px] text-muted-foreground">
          <div>Contract</div>
          <div className="truncate font-mono text-foreground/80" title={config?.contract_id}>
            {config?.contract_id ?? "—"}
          </div>
        </div>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 flex h-14 items-center gap-3 border-b bg-background/80 px-4 backdrop-blur md:px-8">
          <div className="flex gap-1 overflow-x-auto md:hidden">
            {NAV.map(({ href, icon: Icon, label }) => (
              <Link key={href} href={href} title={label} className={cn("rounded-md p-2 text-muted-foreground", path === href && "bg-accent text-foreground")}>
                <Icon className="size-4" />
              </Link>
            ))}
          </div>
          <div className="ml-auto flex items-center gap-3">
            <ModeBadge />
            <WalletButton />
          </div>
        </header>
        <main className="mx-auto w-full max-w-[1400px] flex-1 px-4 py-6 md:px-8 md:py-8">{children}</main>
      </div>
    </div>
  );
}

export function PageHeader({ title, description, actions }: { title: string; description?: string; actions?: React.ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
        {description && <p className="mt-1 max-w-2xl text-sm text-muted-foreground">{description}</p>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  );
}
