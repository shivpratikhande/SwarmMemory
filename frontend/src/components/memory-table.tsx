"use client";

import { AgentGlyph, Confidence, Empty, Mono, StatusBadge } from "@/components/bits";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { Memory } from "@/lib/api";
import { CATEGORY_LABEL, claimText, pct, timeAgo } from "@/lib/format";

export function MemoryTable({ rows, onOpen, extra }: { rows: Memory[] | undefined; onOpen: (id: string) => void; extra?: (m: Memory) => React.ReactNode }) {
  if (!rows) return <div className="h-60 animate-pulse rounded-lg bg-muted/40" />;
  if (!rows.length) return <Empty>No memories match.</Empty>;
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead className="w-14">#</TableHead>
          <TableHead>Memory</TableHead>
          <TableHead>Contributor</TableHead>
          <TableHead>Status</TableHead>
          <TableHead>Confidence</TableHead>
          <TableHead className="text-right">Verif.</TableHead>
          <TableHead className="text-right">Used</TableHead>
          <TableHead className="text-right">Price</TableHead>
          {extra && <TableHead />}
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((m) => (
          <TableRow key={m.memory_id} className="cursor-pointer" onClick={() => onOpen(m.memory_id)}>
            <TableCell>
              <Mono className="text-muted-foreground">{m.seq}</Mono>
            </TableCell>
            <TableCell className="max-w-md">
              <div className="truncate text-[14px] font-medium">{m.title}</div>
              <div className="mt-1 flex items-center gap-2 text-xs text-muted-foreground">
                <span>{CATEGORY_LABEL[m.category] ?? m.category}</span>
                <Mono className="rounded-md bg-surface px-1.5 py-0.5 text-[11px] text-foreground/75 ring-1 ring-border/70">{claimText(m.claim)}</Mono>
                {m.similarity !== null && <span className="font-medium text-primary">{pct(m.similarity)} match</span>}
              </div>
            </TableCell>
            <TableCell>
              <div className="flex items-center gap-2">
                <AgentGlyph id={m.contributor_agent_id} size="sm" />
                <span className="text-[13px]">{(m.contributor_name ?? m.contributor_agent_id).split(" · ")[0]}</span>
              </div>
            </TableCell>
            <TableCell>
              <StatusBadge status={m.status} />
              <div className="mt-1 text-[10.5px] text-muted-foreground">{timeAgo(m.created_at)}</div>
            </TableCell>
            <TableCell>
              <Confidence value={m.confidence_score} />
            </TableCell>
            <TableCell className="text-right font-mono text-xs">
              <span className="text-ok">{m.confirm_count}</span>
              <span className="text-muted-foreground/60"> / </span>
              <span className="text-bad">{m.dispute_count}</span>
            </TableCell>
            <TableCell className="text-right font-mono text-xs">{m.usage_count}</TableCell>
            <TableCell className="text-right text-[13px] font-medium tabular-nums">{m.access_type === "free" ? "Free" : `${m.price_near} Ⓝ`}</TableCell>
            {extra && <TableCell onClick={(e) => e.stopPropagation()}>{extra(m)}</TableCell>}
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
