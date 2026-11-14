"use client";

import { LinkIcon, SparklesIcon } from "lucide-react";

import { AgentGlyph, ChainTag, Empty, StatusBadge, TxHash } from "@/components/bits";
import type { ActivityEvent } from "@/lib/api";
import { clock, timeAgo } from "@/lib/format";
import { cn } from "@/lib/utils";

function Glyph({ e }: { e: ActivityEvent }) {
  if (e.onchain)
    return (
      <span className="grid size-6 shrink-0 place-items-center rounded-full bg-chain/12 text-chain ring-2 ring-card" title="Blockchain event">
        <LinkIcon className="size-3" />
      </span>
    );
  if (e.agent_id) return <AgentGlyph id={e.agent_id} size="sm" />;
  return (
    <span className="grid size-6 shrink-0 place-items-center rounded-full bg-primary/12 text-primary ring-2 ring-card">
      <SparklesIcon className="size-3" />
    </span>
  );
}

export function ActivityFeed({ events, compact = false }: { events: ActivityEvent[] | undefined; compact?: boolean }) {
  if (!events)
    return (
      <div className="space-y-3">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="h-10 animate-pulse rounded-lg bg-muted/60" />
        ))}
      </div>
    );
  if (!events.length) return <Empty>No swarm activity yet. Run the demo scenario or trigger an agent.</Empty>;
  return (
    <ol className="relative">
      {events.map((e, i) => (
        <li key={e.id} className={cn("relative flex animate-rise gap-3", compact ? "pb-3.5" : "pb-5")}>
          {i < events.length - 1 && <span className="absolute top-7 bottom-0 left-[11px] w-px bg-border" />}
          <Glyph e={e} />
          <div className="min-w-0 flex-1">
            <div className="flex items-start gap-3">
              <div className={cn("min-w-0 flex-1 text-[13.5px] leading-snug", e.onchain && "text-foreground/85")}>{e.message}</div>
              <span className="shrink-0 pt-0.5 text-[11px] text-muted-foreground tabular-nums" title={new Date(e.created_at).toLocaleString()}>
                {compact ? timeAgo(e.created_at) : clock(e.created_at)}
              </span>
            </div>
            {e.onchain && (
              <div className="mt-1.5 flex flex-wrap items-center gap-2">
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
