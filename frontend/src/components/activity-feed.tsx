"use client";

import { LinkIcon } from "lucide-react";

import { AgentGlyph, ChainTag, Empty, StatusBadge, TxHash } from "@/components/bits";
import type { ActivityEvent } from "@/lib/api";
import { clock } from "@/lib/format";
import { cn } from "@/lib/utils";

export function ActivityFeed({ events, compact = false }: { events: ActivityEvent[] | undefined; compact?: boolean }) {
  if (!events) return <div className="space-y-2">{Array.from({ length: 6 }).map((_, i) => <div key={i} className="h-9 animate-pulse rounded-md bg-muted/50" />)}</div>;
  if (!events.length) return <Empty>No swarm activity yet. Run the demo scenario or trigger an agent.</Empty>;
  return (
    <ol className="relative">
      {events.map((e) => (
        <li key={e.id} className={cn("group flex animate-rise items-start gap-3 border-b border-border/50 py-2.5 last:border-0", compact && "py-2")}>
          <span className="w-14 shrink-0 pt-0.5 font-mono text-[11px] text-muted-foreground tabular-nums">{clock(e.created_at)}</span>
          <span className="pt-px">
            {e.onchain ? (
              <span className="grid size-5 place-items-center rounded-md border border-chain/30 bg-chain/10 text-chain" title="Blockchain event">
                <LinkIcon className="size-3" />
              </span>
            ) : e.agent_id ? (
              <AgentGlyph id={e.agent_id} size="sm" />
            ) : (
              <span className="grid size-5 place-items-center rounded-md border bg-muted text-[10px] text-muted-foreground">·</span>
            )}
          </span>
          <div className="min-w-0 flex-1">
            <div className={cn("text-[13px] leading-snug", e.onchain ? "text-foreground/90" : "text-foreground")}>{e.message}</div>
            {e.onchain && (
              <div className="mt-1 flex flex-wrap items-center gap-2">
                <ChainTag simulated={e.network !== "testnet"} />
                {e.tx_status && <StatusBadge status={e.tx_status} />}
                <TxHash hash={e.tx_hash} url={e.explorer_url} />
              </div>
            )}
          </div>
        </li>
      ))}
    </ol>
  );
}
