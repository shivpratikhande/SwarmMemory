"use client";

import { ArrowUpRightIcon, InboxIcon, LinkIcon, type LucideIcon } from "lucide-react";

import { Card } from "@/components/ui/card";
import type { Status } from "@/lib/api";
import { pct, shortHash } from "@/lib/format";
import { cn } from "@/lib/utils";

type Tone = "ok" | "warn" | "bad" | "neutral" | "chain";

const TONE: Record<Tone, string> = {
  ok: "bg-ok/12 text-ok ring-ok/25",
  warn: "bg-warn/14 text-warn ring-warn/30",
  bad: "bg-bad/12 text-bad ring-bad/25",
  chain: "bg-chain/10 text-chain ring-chain/25",
  neutral: "bg-muted text-muted-foreground ring-border",
};

const STATUS_TONE: Record<string, Tone> = {
  VERIFIED: "ok",
  CONFIRMED: "ok",
  confirmed: "ok",
  succeeded: "ok",
  PENDING: "warn",
  pending: "warn",
  running: "warn",
  DISPUTED: "bad",
  failed: "bad",
  error: "bad",
  EXPIRED: "neutral",
  queued: "neutral",
  idle: "neutral",
};

const STATUS_LABEL: Record<string, string> = {
  VERIFIED: "Verified",
  CONFIRMED: "Confirmed",
  PENDING: "Pending",
  DISPUTED: "Disputed",
  EXPIRED: "Expired",
};

export function StatusBadge({ status, className }: { status: Status | string; className?: string }) {
  const tone = STATUS_TONE[status] ?? "neutral";
  const live = status === "running" || status === "pending" || status === "PENDING";
  const label = STATUS_LABEL[status] ?? status.charAt(0).toUpperCase() + status.slice(1);
  return (
    <span className={cn("inline-flex shrink-0 items-center gap-1.5 rounded-full px-2 py-0.5 text-[11.5px] font-medium ring-1 ring-inset", TONE[tone], className)}>
      <span className={cn("size-1.5 rounded-full bg-current", live && "animate-pulse-dot")} />
      {label}
    </span>
  );
}

export function ChainTag({ simulated }: { simulated: boolean }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[10.5px] font-medium ring-1 ring-inset",
        simulated ? "bg-sim/10 text-sim ring-sim/30" : "bg-chain/10 text-chain ring-chain/25",
      )}
      title={simulated ? "Simulated transaction (demo mode)" : "Real NEAR testnet transaction"}
    >
      <LinkIcon className="size-2.5" />
      {simulated ? "Simulated" : "On-chain"}
    </span>
  );
}

export function TxHash({ hash, url, n = 6 }: { hash: string | null; url?: string | null; n?: number }) {
  if (!hash) return <span className="text-muted-foreground">—</span>;
  if (!url)
    return (
      <span className="font-mono text-xs text-muted-foreground" title={hash}>
        {shortHash(hash, n)}
      </span>
    );
  return (
    <a href={url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-0.5 font-mono text-xs text-chain hover:underline" title={hash}>
      {shortHash(hash, n)}
      <ArrowUpRightIcon className="size-3" />
    </a>
  );
}

export function Confidence({ value, className, wide = false }: { value: number; className?: string; wide?: boolean }) {
  const tone = value >= 0.6 ? "bg-ok" : value >= 0.34 ? "bg-warn" : "bg-bad";
  return (
    <div className={cn("flex items-center gap-2", className)} title="Derived from independent verifications and usage outcomes, never from an LLM">
      <div className={cn("h-1.5 overflow-hidden rounded-full bg-muted", wide ? "flex-1" : "w-16")}>
        <div className={cn("h-full rounded-full transition-all duration-500", tone)} style={{ width: `${Math.round(value * 100)}%` }} />
      </div>
      <span className="text-xs font-medium tabular-nums text-muted-foreground">{pct(value)}</span>
    </div>
  );
}

const STAT_TONE: Record<string, { chip: string; value: string }> = {
  ember: { chip: "bg-primary/12 text-primary", value: "" },
  ok: { chip: "bg-ok/12 text-ok", value: "text-ok" },
  bad: { chip: "bg-bad/12 text-bad", value: "text-bad" },
  warn: { chip: "bg-warn/15 text-warn", value: "" },
  chain: { chip: "bg-chain/12 text-chain", value: "text-chain" },
  neutral: { chip: "bg-muted text-muted-foreground", value: "" },
};

export function Stat({
  label,
  value,
  hint,
  icon: Icon,
  tone = "neutral",
}: {
  label: string;
  value: React.ReactNode;
  hint?: React.ReactNode;
  icon?: LucideIcon;
  tone?: keyof typeof STAT_TONE;
}) {
  const t = STAT_TONE[tone];
  return (
    <Card className="gap-0 px-5 py-4">
      <div className="flex items-center justify-between gap-2">
        <span className="text-[13px] text-muted-foreground">{label}</span>
        {Icon && (
          <span className={cn("grid size-7 place-items-center rounded-lg", t.chip)}>
            <Icon className="size-3.5" />
          </span>
        )}
      </div>
      <div className={cn("mt-2 font-[family-name:var(--font-display)] text-[28px] leading-none font-semibold tracking-tight tabular-nums", t.value)}>{value}</div>
      {hint && <div className="mt-2 text-xs text-muted-foreground">{hint}</div>}
    </Card>
  );
}

const ROLE_GRADIENT: Record<string, string> = {
  researcher: "linear-gradient(135deg, oklch(0.74 0.15 60), oklch(0.62 0.17 38))",
  verifier: "linear-gradient(135deg, oklch(0.72 0.13 165), oklch(0.55 0.12 175))",
  developer: "linear-gradient(135deg, oklch(0.68 0.13 285), oklch(0.52 0.15 270))",
};

export function roleOf(id: string, role?: string) {
  return role ?? (id.includes("research") ? "researcher" : id.includes("verif") ? "verifier" : id.includes("dev") ? "developer" : "");
}

export function AgentGlyph({ id, role, size = "md" }: { id: string; role?: string; size?: "sm" | "md" | "lg" }) {
  const r = roleOf(id, role);
  const letter = id.match(/agent-([a-z])/)?.[1]?.toUpperCase() ?? id[0]?.toUpperCase();
  const bg = ROLE_GRADIENT[r];
  return (
    <span
      className={cn(
        "grid shrink-0 place-items-center rounded-full font-semibold ring-2 ring-card",
        size === "sm" && "size-6 text-[10.5px]",
        size === "md" && "size-9 text-sm",
        size === "lg" && "size-12 text-lg",
        bg ? "text-white" : "bg-muted text-muted-foreground",
      )}
      style={bg ? { background: bg } : undefined}
    >
      {letter}
    </span>
  );
}

export function Empty({ children, icon: Icon = InboxIcon }: { children: React.ReactNode; icon?: LucideIcon }) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-xl border border-dashed bg-surface/60 px-6 py-12 text-center text-sm text-muted-foreground">
      <span className="grid size-10 place-items-center rounded-full bg-muted">
        <Icon className="size-4.5" />
      </span>
      <div className="max-w-sm">{children}</div>
    </div>
  );
}

export function Mono({ children, className }: { children: React.ReactNode; className?: string }) {
  return <span className={cn("font-mono text-xs", className)}>{children}</span>;
}

export function Near({ value, className }: { value: React.ReactNode; className?: string }) {
  return (
    <span className={cn("tabular-nums", className)}>
      {value} <span className="text-[0.85em] opacity-70">Ⓝ</span>
    </span>
  );
}

export function Delta({ value }: { value: number }) {
  return <span className={cn("font-mono text-sm font-medium tabular-nums", value > 0 ? "text-ok" : "text-bad")}>{value > 0 ? `+${value}` : value}</span>;
}
