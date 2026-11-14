"use client";

import { SearchIcon, XIcon } from "lucide-react";
import { useState } from "react";
import useSWR from "swr";

import { PageHeader } from "@/components/app-shell";
import { MemoryDialog } from "@/components/memory-dialog";
import { MemoryTable } from "@/components/memory-table";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { post, type Memory } from "@/lib/api";
import { CATEGORY_LABEL } from "@/lib/format";
import { useLive } from "@/lib/hooks";

export default function MemoryExplorer() {
  const [category, setCategory] = useState("all");
  const [status, setStatus] = useState("all");
  const [sort, setSort] = useState("created_at");
  const [query, setQuery] = useState("");
  const [active, setActive] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);

  const params = new URLSearchParams({ sort });
  if (category !== "all") params.set("category", category);
  if (status !== "all") params.set("status", status);
  const { data: listed } = useLive<Memory[]>(active ? null : `/memories?${params}`, 3000);
  const { data: found } = useSWR<Memory[]>(active ? ["search", active, category, status] : null, () =>
    post<Memory[]>("/memories/search", {
      query: active,
      limit: 25,
      ...(category !== "all" && { category }),
      ...(status !== "all" && { status: [status] }),
    }),
  );
  const rows = active ? (sort === "confidence" ? found && [...found].sort((a, b) => b.confidence_score - a.confidence_score) : found) : listed;

  return (
    <>
      <PageHeader
        eyebrow="Knowledge"
        title="Memory Explorer"
        description="Every published Memory Capsule, with semantic search, lifecycle status, evidence and verification history."
      />
      <Card>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap gap-2">
            <form
              className="flex min-w-72 flex-1 gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                setActive(query.trim() || null);
              }}
            >
              <div className="relative flex-1">
                <SearchIcon className="absolute top-1/2 left-3.5 size-4 -translate-y-1/2 text-muted-foreground" />
                <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Ask in plain words, e.g. “which API is unreliable?”" className="h-10 rounded-xl bg-surface pl-10" />
              </div>
              <Button type="submit" className="h-10 rounded-xl px-4">
                Search
              </Button>
              {active && (
                <Button
                  type="button"
                  variant="ghost"
                  onClick={() => {
                    setActive(null);
                    setQuery("");
                  }}
                >
                  <XIcon /> Clear
                </Button>
              )}
            </form>
            <Select value={category} onValueChange={setCategory}>
              <SelectTrigger className="h-10! w-48 rounded-xl bg-surface">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All categories</SelectItem>
                {Object.entries(CATEGORY_LABEL).map(([k, v]) => (
                  <SelectItem key={k} value={k}>
                    {v}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select value={status} onValueChange={setStatus}>
              <SelectTrigger className="h-10! w-36 rounded-xl bg-surface">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All statuses</SelectItem>
                {["PENDING", "VERIFIED", "DISPUTED", "EXPIRED"].map((s) => (
                  <SelectItem key={s} value={s}>
                    {s.toLowerCase()}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select value={sort} onValueChange={setSort}>
              <SelectTrigger className="h-10! w-44 rounded-xl bg-surface">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="created_at">Newest first</SelectItem>
                <SelectItem value="confidence">Highest confidence</SelectItem>
                <SelectItem value="usage">Most used</SelectItem>
                <SelectItem value="verifications">Most verified</SelectItem>
              </SelectContent>
            </Select>
          </div>
          {active && (
            <div className="inline-flex items-center gap-2 rounded-full bg-primary/10 px-3 py-1 text-xs font-medium text-primary">Ranked by semantic similarity to “{active}”</div>
          )}
          <MemoryTable rows={rows} onOpen={setOpen} />
        </CardContent>
      </Card>
      <MemoryDialog memoryId={open} onOpenChange={(o) => !o && setOpen(null)} />
    </>
  );
}
