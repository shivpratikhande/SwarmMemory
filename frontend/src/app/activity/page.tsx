"use client";

import { useState } from "react";

import { ActivityFeed } from "@/components/activity-feed";
import { PageHeader } from "@/components/app-shell";
import { Card, CardContent } from "@/components/ui/card";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { ActivityEvent } from "@/lib/api";
import { useLive } from "@/lib/hooks";

export default function ActivityPage() {
  const [filter, setFilter] = useState("all");
  const q = filter === "chain" ? "&onchain=true" : filter === "agents" ? "&onchain=false" : "";
  const { data } = useLive<ActivityEvent[]>(`/dashboard/activity?limit=200${q}`, 2000);
  return (
    <>
      <PageHeader
        eyebrow="Network"
        title="Activity"
        description="Everything the swarm does, in order. Contract calls are marked with a chain icon and carry their transaction status, separate from off-chain agent work."
        actions={
          <Tabs value={filter} onValueChange={setFilter}>
            <TabsList className="rounded-full">
              <TabsTrigger value="all">All</TabsTrigger>
              <TabsTrigger value="agents">Agent activity</TabsTrigger>
              <TabsTrigger value="chain">Blockchain events</TabsTrigger>
            </TabsList>
          </Tabs>
        }
      />
      <Card>
        <CardContent>
          <ActivityFeed events={data ? [...data].reverse() : undefined} />
        </CardContent>
      </Card>
    </>
  );
}
