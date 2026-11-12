"use client";

import { ExternalLinkIcon, LinkIcon } from "lucide-react";

import { Card } from "@/components/ui/card";
import type { Status } from "@/lib/api";
import { pct, shortHash } from "@/lib/format";
import { cn } from "@/lib/utils";

const STATUS_STYLE: Record<string, string> = {
  VERIFIED: "border-ok/30 bg-ok/10 text-ok",
  PENDING: "border-warn/30 bg-warn/10 text-warn",
  DISPUTED: "border-bad/30 bg-bad/10 text-bad",
  EXPIRED: "border-border bg-muted text-muted-foreground",
  CONFIRMED: "border-ok/30 bg-ok/10 text-ok",
  confirmed: "border-ok/30 bg-ok/10 text-ok",
  succeeded: "border-ok/30 bg-ok/10 text-ok",
  pending: "border-warn/30 bg-warn/10 text-warn",
  running: "border-warn/30 bg-warn/10 text-warn",
  queued: "border-border bg-muted text-muted-foreground",
  failed: "border-bad/30 bg-bad/10 text-bad",
  error: "border-bad/30 bg-bad/10 text-bad",
  idle: "border-border bg-muted text-muted-foreground",
};

export function StatusBadge({ status, className }: { status: Status | string; className?: string }) {
  const live = status === "running" || status === "pending";
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md border px-1.5 py-0.5 font-mono text-[10.5px] font-medium tracking-wide uppercase",
        STATUS_STYLE[status] ?? "border-border text-muted-foreground",
        className,
      )}
    >
      {live && <span className="size-1.5 animate-pulse-dot rounded-full bg-current" />}
      {status}
    </span>
  );
}

export function ChainTag({ simulated }: { simulated: boolean }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded border px-1 py-px font-mono text-[9.5px] tracking-wider uppercase",
        simulated ? "border-sim/30 text-sim" : "border-chain/30 text-chain",
      )}
      title={simulated ? "Simulated transaction (demo mode)" : "Real NEAR testnet transaction"}
    >
      <LinkIcon className="size-2.5" />
      {simulated ? "sim" : "on-chain"}
    </span>
  );
}

export function TxHash({ hash, url, n = 6 }: { hash: string | null; url?: string | null; n?: number }) {
  if (!hash) return <span className="text-muted-foreground">—</span>;
  if (!url) return <span className="font-mono text-xs text-muted-foreground" title={hash}>{shortHash(hash, n)}</span>;
  return (
    <a href={url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 font-mono text-xs text-chain hover:underline" title={hash}>
      {shortHash(hash, n)}
      <ExternalLinkIcon className="size-3" />
    </a>
  );
}

export function Confidence({ value, className }: { value: number; className?: string }) {
  const tone = value >= 0.6 ? "bg-ok" : value >= 0.34 ? "bg-warn" : "bg-bad";
  return (
    <div className={cn("flex items-center gap-2", className)} title="Derived from independent verifications and usage outcomes — never from an LLM">
      <div className="h-1.5 w-16 overflow-hidden rounded-full bg-muted">
        <div className={cn("h-full rounded-full transition-all", tone)} style={{ width: `${Math.round(value * 100)}%` }} />
      </div>
      <span className="font-mono text-xs tabular-nums text-muted-foreground">{pct(value)}</span>
    </div>
  );
}

export function Stat({ label, value, hint, accent }: { label: string; value: React.ReactNode; hint?: React.ReactNode; accent?: string }) {
  return (
    <Card className="gap-1 px-5 py-4">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className={cn("text-2xl font-semibold tracking-tight tabular-nums", accent)}>{value}</div>
      {hint && <div className="text-[11px] text-muted-foreground">{hint}</div>}
    </Card>
  );
}

const ROLE_TONE: Record<string, string> = {
  researcher: "bg-sky-400/10 text-sky-300 border-sky-400/25",
  verifier: "bg-ok/10 text-ok border-ok/25",
  developer: "bg-chain/10 text-chain border-chain/25",
};

export function AgentGlyph({ id, role, size = "md" }: { id: string; role?: string; size?: "sm" | "md" }) {
  const r = role ?? (id.includes("research") ? "researcher" : id.includes("verif") ? "verifier" : id.includes("dev") ? "developer" : "");
  const letter = id.match(/agent-([a-z])/)?.[1]?.toUpperCase() ?? id[0]?.toUpperCase();
  return (
    <span
      className={cn(
        "grid shrink-0 place-items-center rounded-md border font-mono font-semibold",
        size === "sm" ? "size-5 text-[10px]" : "size-8 text-xs",
        ROLE_TONE[r] ?? "bg-muted text-muted-foreground",
      )}
    >
      {letter}
    </span>
  );
}

export function Empty({ children }: { children: React.ReactNode }) {
  return <div className="rounded-lg border border-dashed px-6 py-10 text-center text-sm text-muted-foreground">{children}</div>;
}

export function Mono({ children, className }: { children: React.ReactNode; className?: string }) {
  return <span className={cn("font-mono text-xs", className)}>{children}</span>;
}
