export function timeAgo(iso: string | null | undefined): string {
  if (!iso) return "—";
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 5) return "just now";
  if (s < 60) return `${Math.floor(s)}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

export function clock(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23" });
}

export function shortHash(h: string | null | undefined, n = 6): string {
  if (!h) return "—";
  return h.length <= n * 2 + 1 ? h : `${h.slice(0, n)}…${h.slice(-n)}`;
}

export function pct(v: number | null | undefined, digits = 0): string {
  if (v === null || v === undefined) return "—";
  return `${(v * 100).toFixed(digits)}%`;
}

export function near(v: string | null | undefined): string {
  if (v === null || v === undefined) return "—";
  return `${v} Ⓝ`;
}

export const CATEGORY_LABEL: Record<string, string> = {
  api_discovery: "API discovery",
  failed_experiment: "Failed experiment",
  successful_workflow: "Successful workflow",
  deployment_strategy: "Deployment strategy",
  tool_usage: "Tool usage",
  research_discovery: "Research discovery",
};

export const ROLE_LABEL: Record<string, string> = {
  researcher: "Research Agent",
  verifier: "Verification Agent",
  developer: "Developer Agent",
};

export function claimText(c: { metric: string; operator: string; threshold: number; target: string } | undefined): string {
  if (!c) return "";
  return `${c.target} ${c.metric.replace("_", " ")} ${c.operator} ${pct(c.threshold)}`;
}

/** Display a NEAR amount string; sub-0.0001 amounts (e.g. 1 yocto) are shown compactly. */
export function nearAmount(v: string): string {
  const n = Number(v);
  if (n > 0 && n < 0.0001) return "<0.0001 Ⓝ";
  return `${v} Ⓝ`;
}
