//! SwarmMemory contract — the identity, ownership, payment and economic
//! coordination layer for the SwarmMemory agent network.
//!
//! What lives on-chain: agent identities, memory registrations (ids, contributor,
//! evidence hash, metadata hash, price, status), verification records,
//! purchase entitlements, contributor earnings and reputation history.
//!
//! What stays off-chain: memory text, evidence files, embeddings.

use near_sdk::json_types::U128;
use near_sdk::serde_json::json;
use near_sdk::store::{IterableMap, LookupMap, LookupSet, Vector};
use near_sdk::{
    AccountId, BorshStorageKey, Gas, NearToken, PanicOnDefault, Promise, PromiseError, env, near,
    require,
};

pub const MAX_ID_LEN: usize = 64;
pub const MAX_REF_LEN: usize = 256;
pub const MAX_REASON_LEN: usize = 64;
pub const MAX_REPUTATION_DELTA: i64 = 100;
/// Max price per memory in the MVP: 5 NEAR.
pub const MAX_PRICE: u128 = 5 * 10u128.pow(24);
/// A verifier may re-submit for the same memory (revalidation) after this cooldown.
pub const REVERIFY_COOLDOWN_NS: u64 = 60 * 1_000_000_000;
pub const GAS_FOR_WITHDRAW_CALLBACK: Gas = Gas::from_tgas(10);

#[near(serializers = [borsh, json])]
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum AgentRole {
    Researcher,
    Verifier,
    Developer,
}

#[near(serializers = [borsh, json])]
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum MemoryStatus {
    Pending,
    Verified,
    Disputed,
    Expired,
}

#[near(serializers = [borsh, json])]
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum VerificationOutcome {
    Confirmed,
    Disputed,
}

#[near(serializers = [borsh, json])]
#[derive(Clone, Debug)]
pub struct Agent {
    pub account_id: AccountId,
    pub role: AgentRole,
    pub registered_at: u64,
    pub reputation: i64,
    pub memories_published: u32,
    pub verifications_submitted: u32,
}

#[near(serializers = [borsh, json])]
#[derive(Clone, Debug)]
pub struct MemoryRecord {
    pub memory_id: String,
    pub contributor: AccountId,
    pub evidence_hash: String,
    pub metadata_hash: String,
    pub content_ref: String,
    pub price: U128,
    pub created_at: u64,
    pub status: MemoryStatus,
    pub confirmations: u32,
    pub disputes: u32,
    pub purchase_count: u32,
}

#[near(serializers = [borsh, json])]
#[derive(Clone, Debug)]
pub struct VerificationRecord {
    pub memory_id: String,
    pub verifier: AccountId,
    pub outcome: VerificationOutcome,
    pub evidence_hash: String,
    pub recorded_at: u64,
}

#[near(serializers = [borsh, json])]
#[derive(Clone, Debug)]
pub struct PurchaseRecord {
    pub memory_id: String,
    pub buyer: AccountId,
    pub contributor: AccountId,
    pub amount: U128,
    pub purchased_at: u64,
}

#[near(serializers = [borsh, json])]
#[derive(Clone, Debug)]
pub struct ReputationChange {
    pub agent: AccountId,
    pub delta: i64,
    pub new_score: i64,
    pub reason: String,
    pub memory_id: Option<String>,
    pub recorded_at: u64,
}

#[near(serializers = [borsh])]
#[derive(Clone, Copy)]
struct LatestVerification {
    outcome: VerificationOutcome,
    at: u64,
}

#[near(serializers = [json])]
pub struct Stats {
    pub agents: u32,
    pub memories: u32,
    pub verifications: u32,
    pub purchases: u32,
    pub total_volume: U128,
    pub total_withdrawn: U128,
}

#[near]
#[derive(BorshStorageKey)]
enum StorageKey {
    Agents,
    Memories,
    Verifications,
    VerificationIndex,
    LatestVerification,
    Entitlements,
    Earnings,
    TotalEarned,
    PendingWithdrawals,
    Purchases,
    ReputationHistory,
}

#[near(contract_state)]
#[derive(PanicOnDefault)]
pub struct SwarmMemory {
    owner_id: AccountId,
    agents: IterableMap<AccountId, Agent>,
    memories: IterableMap<String, MemoryRecord>,
    verifications: Vector<VerificationRecord>,
    /// memory_id -> indices into `verifications` (full history, never overwritten)
    verification_index: LookupMap<String, Vec<u32>>,
    /// "memory_id|verifier" -> latest outcome of that verifier (used for the tally)
    latest_verification: LookupMap<String, LatestVerification>,
    /// "memory_id|buyer"
    entitlements: LookupSet<String>,
    /// claimable balance per contributor
    earnings: LookupMap<AccountId, u128>,
    total_earned: LookupMap<AccountId, u128>,
    pending_withdrawals: LookupSet<AccountId>,
    purchases: Vector<PurchaseRecord>,
    reputation_history: Vector<ReputationChange>,
    total_volume: u128,
    total_withdrawn: u128,
}

fn emit(event: &str, data: near_sdk::serde_json::Value) {
    env::log_str(&format!(
        "EVENT_JSON:{}",
        json!({"standard": "swarmmemory", "version": "1.0.0", "event": event, "data": [data]})
    ));
}

fn valid_id(id: &str) -> bool {
    !id.is_empty()
        && id.len() <= MAX_ID_LEN
        && id
            .bytes()
            .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'_' || b == b'-')
}

fn valid_hash(h: &str) -> bool {
    h.len() == 64 && h.bytes().all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
}

fn pair_key(memory_id: &str, account: &AccountId) -> String {
    format!("{memory_id}|{account}")
}

#[near]
impl SwarmMemory {
    #[init]
    pub fn new(owner_id: AccountId) -> Self {
        Self {
            owner_id,
            agents: IterableMap::new(StorageKey::Agents),
            memories: IterableMap::new(StorageKey::Memories),
            verifications: Vector::new(StorageKey::Verifications),
            verification_index: LookupMap::new(StorageKey::VerificationIndex),
            latest_verification: LookupMap::new(StorageKey::LatestVerification),
            entitlements: LookupSet::new(StorageKey::Entitlements),
            earnings: LookupMap::new(StorageKey::Earnings),
            total_earned: LookupMap::new(StorageKey::TotalEarned),
            pending_withdrawals: LookupSet::new(StorageKey::PendingWithdrawals),
            purchases: Vector::new(StorageKey::Purchases),
            reputation_history: Vector::new(StorageKey::ReputationHistory),
            total_volume: 0,
            total_withdrawn: 0,
        }
    }

    // ------------------------------------------------------------------ identity

    /// Register the caller as an agent with a role. One registration per account.
    pub fn register_agent(&mut self, role: AgentRole) -> Agent {
        let account_id = env::predecessor_account_id();
        require!(!self.agents.contains_key(&account_id), "Agent already registered");
        let agent = Agent {
            account_id: account_id.clone(),
            role,
            registered_at: env::block_timestamp(),
            reputation: 0,
            memories_published: 0,
            verifications_submitted: 0,
        };
        self.agents.insert(account_id.clone(), agent.clone());
        emit("agent_registered", json!({"account_id": account_id, "role": role}));
        agent
    }

    // ------------------------------------------------------------------ memories

    /// Register a memory capsule. Only hashes and a content reference go on-chain.
    pub fn publish_memory(
        &mut self,
        memory_id: String,
        evidence_hash: String,
        metadata_hash: String,
        content_ref: String,
        price: U128,
    ) -> MemoryRecord {
        let contributor = env::predecessor_account_id();
        require!(self.agents.contains_key(&contributor), "Only registered agents can publish");
        require!(valid_id(&memory_id), "Invalid memory_id");
        require!(valid_hash(&evidence_hash), "evidence_hash must be 64 lowercase hex chars");
        require!(valid_hash(&metadata_hash), "metadata_hash must be 64 lowercase hex chars");
        require!(content_ref.len() <= MAX_REF_LEN, "content_ref too long");
        require!(price.0 <= MAX_PRICE, "Price above MVP cap");
        require!(!self.memories.contains_key(&memory_id), "Memory already registered");
        if let Some(agent) = self.agents.get_mut(&contributor) {
            agent.memories_published += 1;
        }

        let record = MemoryRecord {
            memory_id: memory_id.clone(),
            contributor: contributor.clone(),
            evidence_hash,
            metadata_hash,
            content_ref,
            price,
            created_at: env::block_timestamp(),
            status: MemoryStatus::Pending,
            confirmations: 0,
            disputes: 0,
            purchase_count: 0,
        };
        self.memories.insert(memory_id.clone(), record.clone());
        emit(
            "memory_published",
            json!({"memory_id": memory_id, "contributor": contributor, "price": price}),
        );
        record
    }

    // ------------------------------------------------------------------ verification

    /// Record an independent verification outcome. Contributors cannot verify their own
    /// memories. History is append-only; the status tally uses each verifier's latest result.
    pub fn record_verification(
        &mut self,
        memory_id: String,
        outcome: VerificationOutcome,
        evidence_hash: String,
    ) -> MemoryStatus {
        let verifier = env::predecessor_account_id();
        require!(self.agents.contains_key(&verifier), "Only registered agents can verify");
        require!(valid_hash(&evidence_hash), "evidence_hash must be 64 lowercase hex chars");
        let now = env::block_timestamp();
        let key = pair_key(&memory_id, &verifier);
        let previous = self.latest_verification.get(&key).copied();
        if let Some(prev) = previous {
            require!(
                now >= prev.at + REVERIFY_COOLDOWN_NS,
                "Verifier must wait before re-verifying this memory"
            );
        }

        let memory = self.memories.get_mut(&memory_id);
        require!(memory.is_some(), "Unknown memory");
        let memory = memory.unwrap();
        require!(memory.contributor != verifier, "Agents cannot verify their own memory");

        // Replace this verifier's previous vote in the tally (if any).
        if let Some(prev) = previous {
            match prev.outcome {
                VerificationOutcome::Confirmed => memory.confirmations -= 1,
                VerificationOutcome::Disputed => memory.disputes -= 1,
            }
        }
        match outcome {
            VerificationOutcome::Confirmed => memory.confirmations += 1,
            VerificationOutcome::Disputed => memory.disputes += 1,
        }
        memory.status = if memory.confirmations > memory.disputes {
            MemoryStatus::Verified
        } else {
            MemoryStatus::Disputed
        };
        let status = memory.status;

        let idx = self.verifications.len();
        self.verifications.push(VerificationRecord {
            memory_id: memory_id.clone(),
            verifier: verifier.clone(),
            outcome,
            evidence_hash,
            recorded_at: now,
        });
        let mut list = self.verification_index.get(&memory_id).cloned().unwrap_or_default();
        list.push(idx);
        self.verification_index.insert(memory_id.clone(), list);
        self.latest_verification.insert(key, LatestVerification { outcome, at: now });
        if let Some(agent) = self.agents.get_mut(&verifier) {
            agent.verifications_submitted += 1;
        }
        emit(
            "memory_verified",
            json!({"memory_id": memory_id, "verifier": verifier, "outcome": outcome, "status": status}),
        );
        status
    }

    /// Owner marks a memory as expired (needs revalidation). A new verification revalidates it.
    pub fn mark_expired(&mut self, memory_id: String) {
        self.assert_owner();
        let memory = self.memories.get_mut(&memory_id);
        require!(memory.is_some(), "Unknown memory");
        memory.unwrap().status = MemoryStatus::Expired;
        emit("memory_expired", json!({"memory_id": memory_id}));
    }

    // ------------------------------------------------------------------ marketplace

    /// Buy access to a memory. Requires deposit >= price; excess is refunded.
    /// The contributor's claimable earnings are credited (pull-payment pattern).
    #[payable]
    pub fn purchase_memory(&mut self, memory_id: String) -> bool {
        let buyer = env::predecessor_account_id();
        let deposit = env::attached_deposit().as_yoctonear();
        let memory = self.memories.get_mut(&memory_id);
        require!(memory.is_some(), "Unknown memory");
        let memory = memory.unwrap();
        let price = memory.price.0;
        require!(price > 0, "Memory is free; no purchase needed");
        require!(memory.contributor != buyer, "Contributors cannot buy their own memory");
        require!(memory.status != MemoryStatus::Disputed, "Disputed memories cannot be purchased");
        let key = pair_key(&memory_id, &buyer);
        require!(!self.entitlements.contains(&key), "Already purchased");
        require!(deposit >= price, "Insufficient payment");

        memory.purchase_count += 1;
        let contributor = memory.contributor.clone();
        self.entitlements.insert(key);
        let bal = self.earnings.get(&contributor).copied().unwrap_or(0);
        self.earnings.insert(contributor.clone(), bal + price);
        let tot = self.total_earned.get(&contributor).copied().unwrap_or(0);
        self.total_earned.insert(contributor.clone(), tot + price);
        self.total_volume += price;
        self.purchases.push(PurchaseRecord {
            memory_id: memory_id.clone(),
            buyer: buyer.clone(),
            contributor: contributor.clone(),
            amount: U128(price),
            purchased_at: env::block_timestamp(),
        });

        let refund = deposit - price;
        if refund > 0 {
            // Detached refund; state above is already final regardless of its outcome.
            let _ = Promise::new(buyer.clone()).transfer(NearToken::from_yoctonear(refund));
        }
        emit(
            "memory_purchased",
            json!({"memory_id": memory_id, "buyer": buyer, "contributor": contributor, "amount": U128(price)}),
        );
        true
    }

    /// Withdraw all claimable earnings. The balance is zeroed *before* the transfer and
    /// the account is locked until the callback runs; on failure the balance is restored.
    pub fn withdraw_rewards(&mut self) -> Promise {
        let account = env::predecessor_account_id();
        require!(!self.pending_withdrawals.contains(&account), "Withdrawal already in progress");
        let amount = self.earnings.get(&account).copied().unwrap_or(0);
        require!(amount > 0, "Nothing to withdraw");
        self.earnings.insert(account.clone(), 0);
        self.pending_withdrawals.insert(account.clone());
        Promise::new(account.clone())
            .transfer(NearToken::from_yoctonear(amount))
            .then(
                Self::ext(env::current_account_id())
                    .with_static_gas(GAS_FOR_WITHDRAW_CALLBACK)
                    .on_withdraw_complete(account, U128(amount)),
            )
    }

    #[private]
    pub fn on_withdraw_complete(
        &mut self,
        account_id: AccountId,
        amount: U128,
        #[callback_result] result: Result<(), PromiseError>,
    ) -> bool {
        // #[private] guards the Wasm entry point; repeat the check so the invariant is
        // explicit, and only settle withdrawals that are actually in flight.
        require!(
            env::predecessor_account_id() == env::current_account_id(),
            "Method on_withdraw_complete is private"
        );
        require!(self.pending_withdrawals.remove(&account_id), "No pending withdrawal");
        if result.is_ok() {
            self.total_withdrawn += amount.0;
            emit("rewards_withdrawn", json!({"account_id": account_id, "amount": amount}));
            true
        } else {
            let bal = self.earnings.get(&account_id).copied().unwrap_or(0);
            self.earnings.insert(account_id.clone(), bal + amount.0);
            emit("withdraw_failed", json!({"account_id": account_id, "amount": amount}));
            false
        }
    }

    // ------------------------------------------------------------------ reputation

    /// Only the contract owner (the SwarmMemory reputation oracle) may record reputation
    /// changes. Every change is appended to a public history.
    pub fn update_reputation(
        &mut self,
        agent_id: AccountId,
        delta: i64,
        reason: String,
        memory_id: Option<String>,
    ) -> i64 {
        self.assert_owner();
        require!(delta != 0 && delta.abs() <= MAX_REPUTATION_DELTA, "Invalid delta");
        require!(!reason.is_empty() && reason.len() <= MAX_REASON_LEN, "Invalid reason");
        if let Some(m) = &memory_id {
            require!(self.memories.contains_key(m), "Unknown memory");
        }
        let agent = self.agents.get_mut(&agent_id);
        require!(agent.is_some(), "Unknown agent");
        let agent = agent.unwrap();
        agent.reputation += delta;
        let new_score = agent.reputation;
        self.reputation_history.push(ReputationChange {
            agent: agent_id.clone(),
            delta,
            new_score,
            reason: reason.clone(),
            memory_id,
            recorded_at: env::block_timestamp(),
        });
        emit(
            "reputation_updated",
            json!({"agent": agent_id, "delta": delta, "new_score": new_score, "reason": reason}),
        );
        new_score
    }

    // ------------------------------------------------------------------ views

    pub fn get_owner(&self) -> AccountId {
        self.owner_id.clone()
    }

    pub fn get_agent(&self, account_id: AccountId) -> Option<Agent> {
        self.agents.get(&account_id).cloned()
    }

    pub fn get_agents(&self, from_index: Option<u32>, limit: Option<u32>) -> Vec<Agent> {
        self.agents
            .values()
            .skip(from_index.unwrap_or(0) as usize)
            .take(limit.unwrap_or(50).min(100) as usize)
            .cloned()
            .collect()
    }

    pub fn get_memory(&self, memory_id: String) -> Option<MemoryRecord> {
        self.memories.get(&memory_id).cloned()
    }

    pub fn get_memories(&self, from_index: Option<u32>, limit: Option<u32>) -> Vec<MemoryRecord> {
        self.memories
            .values()
            .skip(from_index.unwrap_or(0) as usize)
            .take(limit.unwrap_or(50).min(100) as usize)
            .cloned()
            .collect()
    }

    /// True when `account_id` may read paid content: the contributor or a buyer.
    pub fn has_access(&self, memory_id: String, account_id: AccountId) -> bool {
        match self.memories.get(&memory_id) {
            None => false,
            Some(m) if m.contributor == account_id || m.price.0 == 0 => true,
            Some(_) => self.entitlements.contains(&pair_key(&memory_id, &account_id)),
        }
    }

    pub fn get_verifications(&self, memory_id: String) -> Vec<VerificationRecord> {
        self.verification_index
            .get(&memory_id)
            .map(|ids| ids.iter().filter_map(|i| self.verifications.get(*i).cloned()).collect())
            .unwrap_or_default()
    }

    pub fn get_earnings(&self, account_id: AccountId) -> U128 {
        U128(self.earnings.get(&account_id).copied().unwrap_or(0))
    }

    pub fn get_total_earned(&self, account_id: AccountId) -> U128 {
        U128(self.total_earned.get(&account_id).copied().unwrap_or(0))
    }

    pub fn is_withdrawal_pending(&self, account_id: AccountId) -> bool {
        self.pending_withdrawals.contains(&account_id)
    }

    pub fn get_purchases(&self, from_index: Option<u32>, limit: Option<u32>) -> Vec<PurchaseRecord> {
        let from = from_index.unwrap_or(0);
        let lim = limit.unwrap_or(50).min(100);
        (from..self.purchases.len().min(from.saturating_add(lim)))
            .filter_map(|i| self.purchases.get(i).cloned())
            .collect()
    }

    pub fn get_reputation_history(
        &self,
        from_index: Option<u32>,
        limit: Option<u32>,
    ) -> Vec<ReputationChange> {
        let from = from_index.unwrap_or(0);
        let lim = limit.unwrap_or(50).min(100);
        (from..self.reputation_history.len().min(from.saturating_add(lim)))
            .filter_map(|i| self.reputation_history.get(i).cloned())
            .collect()
    }

    pub fn get_stats(&self) -> Stats {
        Stats {
            agents: self.agents.len(),
            memories: self.memories.len(),
            verifications: self.verifications.len(),
            purchases: self.purchases.len(),
            total_volume: U128(self.total_volume),
            total_withdrawn: U128(self.total_withdrawn),
        }
    }

    fn assert_owner(&self) {
        require!(env::predecessor_account_id() == self.owner_id, "Only the owner can call this");
    }
}

#[cfg(test)]
mod tests;
