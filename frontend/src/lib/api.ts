export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");

export class ApiError extends Error {
  constructor(public status: number, public detail: string) {
    super(detail);
  }
}

async function handle<T>(r: Response): Promise<T> {
  if (!r.ok) {
    let detail = r.statusText;
    try {
      const body = await r.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* not json */
    }
    throw new ApiError(r.status, detail);
  }
  return r.json() as Promise<T>;
}

export const fetcher = <T,>(path: string): Promise<T> => fetch(`${API_URL}${path}`, { cache: "no-store" }).then((r) => handle<T>(r));

export function post<T>(path: string, body: unknown = {}): Promise<T> {
  return fetch(`${API_URL}${path}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  }).then((r) => handle<T>(r));
}

// ----------------------------------------------------------------------------- types

export type Status = "PENDING" | "VERIFIED" | "DISPUTED" | "EXPIRED";

export interface AppConfig {
  mode: "demo" | "testnet";
  network: "simulated" | "testnet";
  contract_id: string;
  owner_id: string;
  near_network_id: string | null;
  explorer_url: string | null;
  wallet_purchases_enabled: boolean;
}

export interface Claim {
  kind: string;
  target: string;
  endpoint: string;
  metric: "failure_rate" | "success_rate";
  operator: ">=" | "<=";
  threshold: number;
  observed: number;
  sample_size: number;
}

export interface Memory {
  memory_id: string;
  seq: number;
  title: string;
  description: string;
  category: string;
  success_or_failure: string;
  contributor_agent_id: string;
  contributor_name: string | null;
  contributor_account: string | null;
  contributor_reputation: number | null;
  created_at: string;
  last_verified_at: string | null;
  confidence_score: number;
  verification_count: number;
  confirm_count: number;
  dispute_count: number;
  usage_count: number;
  access_type: "free" | "paid";
  price_near: string;
  price_yocto: string;
  status: Status;
  evidence_hash: string;
  metadata_hash: string;
  version: number;
  parent_memory_id: string | null;
  superseded_by: string | null;
  tags: string[];
  claim: Claim;
  onchain_tx_id: string | null;
  has_access: boolean;
  similarity: number | null;
  // full capsule only
  original_observation?: string;
  execution_context?: Record<string, unknown>;
  evidence?: Evidence;
  // marketplace only
  purchase_count?: number;
  revenue_near?: string;
  purchasable?: boolean;
}

export interface Evidence {
  run_id: string;
  requests: { index: number; status: number; latency_ms: number }[];
  summary: Record<string, unknown>;
  logs: string[];
}

export interface VerificationRecord {
  id: string;
  memory_id: string;
  memory_seq?: number;
  memory_title?: string;
  memory_status?: Status;
  claim?: Claim;
  verifier_agent_id: string;
  verifier_name: string;
  verification_result: "CONFIRMED" | "DISPUTED";
  observed_value: number | null;
  verification_evidence: Evidence & { summary: { measured?: number; claimed?: number } };
  evidence_hash: string;
  notes: string;
  verified_at: string;
  onchain_tx_id: string | null;
}

export interface Tx {
  id: string;
  network: string;
  simulated: boolean;
  tx_hash: string | null;
  explorer_url: string | null;
  signer_id: string;
  receiver_id: string;
  method: string;
  args: Record<string, unknown>;
  deposit_near: string;
  status: "pending" | "confirmed" | "failed";
  error: string | null;
  return_value: unknown;
  block_hash: string | null;
  gas_burnt: string | null;
  agent_id: string | null;
  memory_id: string | null;
  initiated_by: string;
  created_at: string;
  confirmed_at: string | null;
}

export interface MemoryDetails {
  memory: Memory;
  verifications: VerificationRecord[];
  versions: { version: number; reason: string; created_at: string }[];
  lineage: { memory_id: string; version: number; status: Status; created_at: string }[];
  purchases: { buyer_account_id: string; buyer_agent_id: string | null; price_near: string; tx_id: string | null; created_at: string }[];
  transactions: Tx[];
}

export interface Agent {
  id: string;
  name: string;
  role: "researcher" | "verifier" | "developer";
  system_prompt: string;
  near_account_id: string;
  network: string;
  status: "idle" | "running" | "error";
  reputation: number;
  tasks_completed: number;
  memories_contributed: number;
  memories_retrieved: number;
  onchain_registered: boolean;
  spent_near: string;
  earned_near: string;
  created_at: string;
}

export interface Execution {
  id: string;
  agent_id: string;
  task: string;
  status: "queued" | "running" | "succeeded" | "failed";
  scenario_run_id: string | null;
  result: Record<string, unknown> | null;
  logs: { ts: string; msg: string }[];
  error: string | null;
  started_at: string;
  finished_at: string | null;
}

export interface AgentDetail extends Agent {
  executions: Execution[];
  memories: { memory_id: string; seq: number; title: string; status: Status; confidence_score: number; created_at: string }[];
  reputation_events: { delta: number; reason: string; memory_id: string | null; onchain_tx_id: string | null; created_at: string }[];
  onchain: Record<string, unknown> | null;
}

export interface ActivityEvent {
  id: number;
  kind: string;
  message: string;
  agent_id: string | null;
  memory_id: string | null;
  tx_id: string | null;
  tx_hash: string | null;
  tx_status: string | null;
  explorer_url: string | null;
  onchain: boolean;
  network: string | null;
  data: Record<string, unknown>;
  scenario_run_id: string | null;
  created_at: string;
}

export interface Stats {
  network: string;
  agents: number;
  memories: number;
  verified: number;
  disputed: number;
  pending: number;
  expired: number;
  purchases: number;
  near_distributed: string;
  transactions: Record<string, number>;
  chain: Record<string, unknown>;
}

export interface ScenarioStep {
  title: string;
  agent_id: string;
  execution_id: string;
  status: string;
  started_at: string;
  finished_at?: string;
  result?: Record<string, unknown> | null;
  error?: string | null;
}

export interface ScenarioRun {
  id: string;
  status: "running" | "succeeded" | "failed";
  network: string;
  options: Record<string, unknown>;
  steps: ScenarioStep[];
  summary: Record<string, unknown> | null;
  error: string | null;
  started_at: string;
  finished_at: string | null;
}

export interface EconomyAgent extends Agent {
  claimable_near?: string;
  total_earned_onchain_near?: string;
  wallet_balance_near?: string;
  chain_error?: string;
}

export interface Economy {
  network: string;
  agents: EconomyAgent[];
  reputation_events: { agent_id: string; delta: number; reason: string; memory_id: string | null; onchain_tx_id: string | null; created_at: string }[];
  total_value_moved_near: string;
}

export interface Purchase {
  id: string;
  memory_id: string;
  buyer_account_id: string;
  buyer_agent_id: string | null;
  seller_agent_id: string;
  price_near: string;
  tx_id: string | null;
  network: string;
  created_at: string;
}
