"use client";

import {
  ActivityIcon,
  ArrowLeftRightIcon,
  BotIcon,
  BrainCircuitIcon,
  CoinsIcon,
  LayoutGridIcon,
  MenuIcon,
  ShieldCheckIcon,
  StoreIcon,
  WalletIcon,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

import { ThemeToggle } from "@/components/theme";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet";
import { useConfig } from "@/lib/hooks";
import { cn } from "@/lib/utils";
import { useWallet } from "@/lib/wallet";

const NAV_GROUPS = [
  {
    label: "Network",
    items: [
      { href: "/", label: "Overview", icon: LayoutGridIcon },
      { href: "/agents", label: "Agent Swarm", icon: BotIcon },
      { href: "/activity", label: "Activity", icon: ActivityIcon },
    ],
  },
  {
    label: "Knowledge",
    items: [
      { href: "/memories", label: "Memory Explorer", icon: BrainCircuitIcon },
      { href: "/verification", label: "Verification", icon: ShieldCheckIcon },
      { href: "/marketplace", label: "Marketplace", icon: StoreIcon },
    ],
  },
  {
    label: "Ledger",
    items: [
      { href: "/economy", label: "Economy", icon: CoinsIcon },
      { href: "/transactions", label: "Transactions", icon: ArrowLeftRightIcon },
    ],
  },
];

const isActive = (path: string, href: string) => (href === "/" ? path === "/" : path.startsWith(href));

/** Honeycomb mark: three cells of a swarm sharing one memory. */
export function LogoMark({ className }: { className?: string }) {
  return (
    <span className={cn("ember-gradient grid size-9 place-items-center rounded-xl text-white shadow-[0_6px_16px_-6px_oklch(0.6_0.18_40/60%)]", className)}>
      <svg viewBox="0 0 24 24" className="size-5" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" aria-hidden>
        <path d="M8 3.8 11 5.5v3.4L8 10.6 5 8.9V5.5z" fill="currentColor" fillOpacity=".95" />
        <path d="M16 3.8 19 5.5v3.4l-3 1.7-3-1.7V5.5z" />
        <path d="M12 11.2 15 12.9v3.4l-3 1.7-3-1.7v-3.4z" fill="currentColor" fillOpacity=".55" />
        <path d="M8 18.6v1.6M16 10.6v2.3M12 18v2.2" strokeLinecap="round" />
      </svg>
    </span>
  );
}

export function ModeBadge({ className }: { className?: string }) {
  const { data } = useConfig();
  if (!data) return null;
  const real = data.network === "testnet";
  return (
    <span
      className={cn(
        "inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-medium",
        real ? "border-chain/30 bg-chain/8 text-chain" : "border-sim/35 bg-sim/10 text-sim",
        className,
      )}
      title={real ? `Real NEAR ${data.near_network_id} transactions · contract ${data.contract_id}` : "Demo mode: simulated contract, no real transactions"}
    >
      <span className="relative flex size-2">
        <span className={cn("absolute inset-0 animate-ping-soft rounded-full", real ? "bg-chain" : "bg-sim")} />
        <span className={cn("relative size-2 rounded-full", real ? "bg-chain" : "bg-sim")} />
      </span>
      {real ? `NEAR ${data.near_network_id}` : "Demo · simulated chain"}
    </span>
  );
}

function WalletButton() {
  const { enabled, accountId, signIn, signOut } = useWallet();
  if (!enabled) return null;
  return accountId ? (
    <Button variant="outline" size="sm" onClick={() => signOut()} className="rounded-full font-mono text-xs" title="Sign out">
      <span className="size-2 rounded-full bg-ok" /> {accountId}
    </Button>
  ) : (
    <Button size="sm" onClick={signIn} className="rounded-full">
      <WalletIcon /> Connect wallet
    </Button>
  );
}

function Nav({ onNavigate }: { onNavigate?: () => void }) {
  const path = usePathname();
  return (
    <nav className="flex flex-col gap-6 px-3">
      {NAV_GROUPS.map((g) => (
        <div key={g.label} className="space-y-1">
          <div className="px-3 pb-1 text-[10.5px] font-semibold tracking-[0.12em] text-muted-foreground/80 uppercase">{g.label}</div>
          {g.items.map(({ href, label, icon: Icon }) => {
            const active = isActive(path, href);
            return (
              <Link
                key={href}
                href={href}
                onClick={onNavigate}
                className={cn(
                  "group relative flex items-center gap-3 rounded-lg px-3 py-2 text-[13.5px] font-medium text-muted-foreground transition-colors hover:bg-sidebar-accent/70 hover:text-foreground",
                  active && "bg-card text-foreground shadow-[var(--shadow-card)] ring-1 ring-border",
                )}
              >
                {active && <span className="absolute top-2 bottom-2 -left-3 w-[3px] rounded-r-full bg-primary" />}
                <Icon className={cn("size-[17px] transition-colors", active ? "text-primary" : "text-muted-foreground/80 group-hover:text-foreground")} />
                {label}
              </Link>
            );
          })}
        </div>
      ))}
    </nav>
  );
}

function NetworkCard() {
  const { data: config } = useConfig();
  const real = config?.network === "testnet";
  return (
    <div className="m-3 rounded-xl border bg-card p-3.5 shadow-[var(--shadow-card)]">
      <div className="flex items-center gap-2 text-xs font-medium">
        <span className="relative flex size-2">
          <span className="absolute inset-0 animate-ping-soft rounded-full bg-ok" />
          <span className="relative size-2 rounded-full bg-ok" />
        </span>
        {config ? (real ? `NEAR ${config.near_network_id}` : "Simulated chain") : "Connecting…"}
        <span className="ml-auto text-[10.5px] text-muted-foreground">live</span>
      </div>
      <div className="mt-2.5 text-[10.5px] tracking-wide text-muted-foreground uppercase">Contract</div>
      <div className="truncate font-mono text-[11.5px] text-foreground/85" title={config?.contract_id}>
        {config?.contract_id ?? "—"}
      </div>
    </div>
  );
}

function Brand() {
  return (
    <Link href="/" className="flex items-center gap-3 px-5 pt-5 pb-7">
      <LogoMark />
      <div className="leading-tight">
        <div className="font-[family-name:var(--font-display)] text-[17px] font-semibold tracking-tight">SwarmMemory</div>
        <div className="text-[11.5px] text-muted-foreground">Collective agent memory</div>
      </div>
    </Link>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const [open, setOpen] = useState(false);
  const current = NAV_GROUPS.flatMap((g) => g.items.map((i) => ({ ...i, group: g.label }))).find((i) => isActive(path, i.href));

  return (
    <div className="flex min-h-screen">
      <aside className="sticky top-0 hidden h-screen w-64 shrink-0 flex-col border-r border-sidebar-border bg-sidebar lg:flex">
        <Brand />
        <Nav />
        <div className="mt-auto">
          <NetworkCard />
        </div>
      </aside>

      <Sheet open={open} onOpenChange={setOpen}>
        <SheetContent side="left" className="flex w-72 flex-col gap-0 bg-sidebar p-0">
          <SheetTitle className="sr-only">Navigation</SheetTitle>
          <Brand />
          <Nav onNavigate={() => setOpen(false)} />
          <div className="mt-auto">
            <NetworkCard />
          </div>
        </SheetContent>
      </Sheet>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 flex h-16 items-center gap-3 border-b bg-background/80 px-4 backdrop-blur-md md:px-8">
          <Button variant="ghost" size="icon" className="-ml-1 lg:hidden" onClick={() => setOpen(true)} aria-label="Open navigation">
            <MenuIcon />
          </Button>
          <LogoMark className="size-8 rounded-lg lg:hidden" />
          {current && (
            <div className="hidden items-center gap-2 text-sm sm:flex">
              <span className="text-muted-foreground">{current.group}</span>
              <span className="text-muted-foreground/50">/</span>
              <span className="font-medium">{current.label}</span>
            </div>
          )}
          <div className="ml-auto flex items-center gap-2">
            <ModeBadge className="hidden sm:inline-flex" />
            <ThemeToggle />
            <WalletButton />
          </div>
        </header>
        <main className="mx-auto w-full max-w-[1360px] flex-1 px-4 py-6 md:px-8 md:py-10">{children}</main>
        <footer className="mx-auto flex w-full max-w-[1360px] flex-wrap items-center gap-x-4 gap-y-1 px-4 pb-8 text-xs text-muted-foreground md:px-8">
          <span>SwarmMemory · hackathon MVP</span>
          <span className="text-muted-foreground/50">·</span>
          <span>Identity, ownership, payments and reputation recorded on NEAR</span>
        </footer>
      </div>
    </div>
  );
}

export function PageHeader({ title, description, actions, eyebrow }: { title: string; description?: string; actions?: React.ReactNode; eyebrow?: string }) {
  return (
    <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
      <div className="max-w-3xl">
        {eyebrow && <div className="mb-2 text-xs font-semibold tracking-[0.14em] text-primary uppercase">{eyebrow}</div>}
        <h1 className="text-[28px] leading-tight font-semibold md:text-[32px]">{title}</h1>
        {description && <p className="mt-2 text-[15px] leading-relaxed text-muted-foreground">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}
