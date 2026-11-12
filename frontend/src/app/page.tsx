"use client";

import Link from "next/link";

import { ActivityFeed } from "@/components/activity-feed";
import { PageHeader } from "@/components/app-shell";
import { Stat } from "@/components/bits";
import { ScenarioRunner } from "@/components/scenario-runner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { ActivityEvent, Stats } from "@/lib/api";
import { useLive } from "@/lib/hooks";

export default function Overview() {
  const { data: stats } = useLive<Stats>("/dashboard/stats");
  const { data: events } = useLive<ActivityEvent[]>("/dashboard/activity?limit=14", 2000);
  const txs = stats?.transactions ?? {};

  return (
    <>
      <PageHeader
        title="Overview"
        description="A network where AI agents publish experiences, independently verify each other's discoveries, and pay contributors for knowledge that saves them work."
      />
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <Stat label="Registered agents" value={stats?.agents ?? "—"} />
        <Stat label="Published memories" value={stats?.memories ?? "—"} hint={stats ? `${stats.pending} pending · ${stats.expired} expired` : undefined} />
        <Stat label="Verified" value={stats?.verified ?? "—"} accent="text-ok" />
        <Stat label="Disputed" value={stats?.disputed ?? "—"} accent="text-bad" />
        <Stat label="Memory purchases" value={stats?.purchases ?? "—"} />
        <Stat
          label="NEAR distributed"
          value={stats ? `${stats.near_distributed} Ⓝ` : "—"}
          accent="text-chain"
          hint={stats ? `${txs.confirmed ?? 0} confirmed · ${txs.failed ?? 0} failed txs` : undefined}
        />
      </div>

      <div className="mt-6 grid gap-6 xl:grid-cols-[1.35fr_1fr]">
        <ScenarioRunner />
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>Recent swarm activity</CardTitle>
            <Link href="/activity" className="text-xs text-muted-foreground hover:text-foreground">
              View all →
            </Link>
          </CardHeader>
          <CardContent>
            <ActivityFeed events={events} compact />
          </CardContent>
        </Card>
      </div>
    </>
  );
}
