use super::*;
use near_sdk::test_utils::{VMContextBuilder, get_logs};
use near_sdk::{PromiseResult, RuntimeFeesConfig, test_vm_config, testing_env};

const ONE_NEAR: u128 = 10u128.pow(24);
const PRICE: u128 = ONE_NEAR / 100; // 0.01 NEAR

fn acc(s: &str) -> AccountId {
    s.parse().unwrap()
}
fn owner() -> AccountId {
    acc("swarm.testnet")
}
fn researcher() -> AccountId {
    acc("researcher.testnet")
}
fn verifier() -> AccountId {
    acc("verifier.testnet")
}
fn developer() -> AccountId {
    acc("developer.testnet")
}
fn outsider() -> AccountId {
    acc("mallory.testnet")
}
fn h(c: char) -> String {
    std::iter::repeat_n(c, 64).collect()
}

fn ctx(predecessor: AccountId, deposit: u128, ts_secs: u64) -> VMContextBuilder {
    let mut b = VMContextBuilder::new();
    b.current_account_id(owner())
        .predecessor_account_id(predecessor.clone())
        .signer_account_id(predecessor)
        .attached_deposit(NearToken::from_yoctonear(deposit))
        .block_timestamp(ts_secs * 1_000_000_000)
        .account_balance(NearToken::from_near(100));
    b
}

fn as_caller(who: AccountId) {
    testing_env!(ctx(who, 0, 1_000).build());
}
fn as_caller_at(who: AccountId, ts: u64) {
    testing_env!(ctx(who, 0, ts).build());
}
fn as_payer(who: AccountId, deposit: u128) {
    testing_env!(ctx(who, deposit, 1_000).build());
}

/// Contract with three registered agents and one paid memory "mem_1" by the researcher.
fn setup() -> SwarmMemory {
    as_caller(owner());
    let mut c = SwarmMemory::new(owner());
    as_caller(researcher());
    c.register_agent(AgentRole::Researcher);
    as_caller(verifier());
    c.register_agent(AgentRole::Verifier);
    as_caller(developer());
    c.register_agent(AgentRole::Developer);
    as_caller(researcher());
    c.publish_memory("mem_1".into(), h('a'), h('b'), "swarm://memories/mem_1".into(), U128(PRICE));
    c
}

// ---------------------------------------------------------------- registration

#[test]
fn register_agent_records_identity_and_role() {
    let c = setup();
    let a = c.get_agent(researcher()).unwrap();
    assert_eq!(a.role, AgentRole::Researcher);
    assert_eq!(a.reputation, 0);
    assert_eq!(a.memories_published, 1);
    assert_eq!(c.get_stats().agents, 3);
}

#[test]
#[should_panic(expected = "Agent already registered")]
fn duplicate_registration_rejected() {
    let mut c = setup();
    as_caller(researcher());
    c.register_agent(AgentRole::Developer);
}

// ---------------------------------------------------------------- publication

#[test]
fn publish_memory_starts_pending_with_hashes() {
    let c = setup();
    let m = c.get_memory("mem_1".into()).unwrap();
    assert_eq!(m.status, MemoryStatus::Pending);
    assert_eq!(m.contributor, researcher());
    assert_eq!(m.evidence_hash, h('a'));
    assert_eq!(m.metadata_hash, h('b'));
    assert_eq!(m.price.0, PRICE);
    assert_eq!(m.created_at, 1_000 * 1_000_000_000);
    assert!(get_logs().iter().any(|l| l.contains("memory_published")));
}

#[test]
#[should_panic(expected = "Only registered agents can publish")]
fn unregistered_cannot_publish() {
    let mut c = setup();
    as_caller(outsider());
    c.publish_memory("mem_2".into(), h('a'), h('b'), String::new(), U128(PRICE));
}

#[test]
#[should_panic(expected = "Memory already registered")]
fn duplicate_memory_id_rejected() {
    let mut c = setup();
    as_caller(verifier());
    c.publish_memory("mem_1".into(), h('c'), h('d'), String::new(), U128(PRICE));
}

#[test]
#[should_panic(expected = "evidence_hash must be 64 lowercase hex chars")]
fn malformed_evidence_hash_rejected() {
    let mut c = setup();
    as_caller(researcher());
    c.publish_memory("mem_2".into(), "xyz".into(), h('b'), String::new(), U128(PRICE));
}

#[test]
#[should_panic(expected = "Price above MVP cap")]
fn price_cap_enforced() {
    let mut c = setup();
    as_caller(researcher());
    c.publish_memory("mem_2".into(), h('a'), h('b'), String::new(), U128(6 * ONE_NEAR));
}

// ---------------------------------------------------------------- verification

#[test]
fn independent_verification_updates_status_and_history() {
    let mut c = setup();
    as_caller(verifier());
    let st = c.record_verification("mem_1".into(), VerificationOutcome::Confirmed, h('c'));
    assert_eq!(st, MemoryStatus::Verified);
    let m = c.get_memory("mem_1".into()).unwrap();
    assert_eq!((m.confirmations, m.disputes), (1, 0));
    let hist = c.get_verifications("mem_1".into());
    assert_eq!(hist.len(), 1);
    assert_eq!(hist[0].verifier, verifier());
    assert_eq!(c.get_agent(verifier()).unwrap().verifications_submitted, 1);
}

#[test]
#[should_panic(expected = "Agents cannot verify their own memory")]
fn self_verification_rejected() {
    let mut c = setup();
    as_caller(researcher());
    c.record_verification("mem_1".into(), VerificationOutcome::Confirmed, h('c'));
}

#[test]
#[should_panic(expected = "Only registered agents can verify")]
fn unregistered_cannot_verify() {
    let mut c = setup();
    as_caller(outsider());
    c.record_verification("mem_1".into(), VerificationOutcome::Confirmed, h('c'));
}

#[test]
fn dispute_majority_marks_disputed() {
    let mut c = setup();
    as_caller(verifier());
    c.record_verification("mem_1".into(), VerificationOutcome::Disputed, h('c'));
    assert_eq!(c.get_memory("mem_1".into()).unwrap().status, MemoryStatus::Disputed);
    as_caller(developer());
    // tie (1 confirm vs 1 dispute) stays disputed
    let st = c.record_verification("mem_1".into(), VerificationOutcome::Confirmed, h('d'));
    assert_eq!(st, MemoryStatus::Disputed);
}

#[test]
fn reverification_preserves_history_and_replaces_vote() {
    let mut c = setup();
    as_caller_at(verifier(), 1_000);
    c.record_verification("mem_1".into(), VerificationOutcome::Disputed, h('c'));
    as_caller_at(verifier(), 1_000 + 61);
    let st = c.record_verification("mem_1".into(), VerificationOutcome::Confirmed, h('d'));
    assert_eq!(st, MemoryStatus::Verified);
    let m = c.get_memory("mem_1".into()).unwrap();
    assert_eq!((m.confirmations, m.disputes), (1, 0));
    assert_eq!(c.get_verifications("mem_1".into()).len(), 2, "history must be append-only");
}

#[test]
#[should_panic(expected = "Verifier must wait before re-verifying this memory")]
fn reverification_cooldown_enforced() {
    let mut c = setup();
    as_caller_at(verifier(), 1_000);
    c.record_verification("mem_1".into(), VerificationOutcome::Confirmed, h('c'));
    as_caller_at(verifier(), 1_010);
    c.record_verification("mem_1".into(), VerificationOutcome::Confirmed, h('c'));
}

#[test]
fn expired_memory_revalidated_by_new_verification() {
    let mut c = setup();
    as_caller(owner());
    c.mark_expired("mem_1".into());
    assert_eq!(c.get_memory("mem_1".into()).unwrap().status, MemoryStatus::Expired);
    as_caller(verifier());
    assert_eq!(
        c.record_verification("mem_1".into(), VerificationOutcome::Confirmed, h('c')),
        MemoryStatus::Verified
    );
}

#[test]
#[should_panic(expected = "Only the owner can call this")]
fn only_owner_can_expire() {
    let mut c = setup();
    as_caller(verifier());
    c.mark_expired("mem_1".into());
}

// ---------------------------------------------------------------- payments

#[test]
fn purchase_grants_access_and_credits_contributor() {
    let mut c = setup();
    assert!(!c.has_access("mem_1".into(), developer()));
    as_payer(developer(), PRICE);
    assert!(c.purchase_memory("mem_1".into()));
    assert!(c.has_access("mem_1".into(), developer()));
    assert!(c.has_access("mem_1".into(), researcher()), "contributor always has access");
    assert_eq!(c.get_earnings(researcher()).0, PRICE);
    assert_eq!(c.get_total_earned(researcher()).0, PRICE);
    let s = c.get_stats();
    assert_eq!((s.purchases, s.total_volume.0), (1, PRICE));
    assert_eq!(c.get_purchases(None, None)[0].buyer, developer());
    assert_eq!(c.get_memory("mem_1".into()).unwrap().purchase_count, 1);
}

#[test]
fn overpayment_credits_only_price() {
    let mut c = setup();
    as_payer(developer(), PRICE * 3);
    c.purchase_memory("mem_1".into());
    assert_eq!(c.get_earnings(researcher()).0, PRICE);
}

#[test]
fn wallet_user_can_buy_without_registering() {
    let mut c = setup();
    as_payer(outsider(), PRICE);
    c.purchase_memory("mem_1".into());
    assert!(c.has_access("mem_1".into(), outsider()));
}

#[test]
#[should_panic(expected = "Insufficient payment")]
fn insufficient_payment_rejected() {
    let mut c = setup();
    as_payer(developer(), PRICE - 1);
    c.purchase_memory("mem_1".into());
}

#[test]
#[should_panic(expected = "Already purchased")]
fn duplicate_purchase_rejected() {
    let mut c = setup();
    as_payer(developer(), PRICE);
    c.purchase_memory("mem_1".into());
    as_payer(developer(), PRICE);
    c.purchase_memory("mem_1".into());
}

#[test]
#[should_panic(expected = "Contributors cannot buy their own memory")]
fn self_purchase_rejected() {
    let mut c = setup();
    as_payer(researcher(), PRICE);
    c.purchase_memory("mem_1".into());
}

#[test]
#[should_panic(expected = "Unknown memory")]
fn purchase_unknown_memory_rejected() {
    let mut c = setup();
    as_payer(developer(), PRICE);
    c.purchase_memory("nope".into());
}

#[test]
#[should_panic(expected = "Disputed memories cannot be purchased")]
fn disputed_memory_not_purchasable() {
    let mut c = setup();
    as_caller(verifier());
    c.record_verification("mem_1".into(), VerificationOutcome::Disputed, h('c'));
    as_payer(developer(), PRICE);
    c.purchase_memory("mem_1".into());
}

#[test]
#[should_panic(expected = "Memory is free; no purchase needed")]
fn free_memory_needs_no_purchase() {
    let mut c = setup();
    as_caller(researcher());
    c.publish_memory("mem_free".into(), h('a'), h('b'), String::new(), U128(0));
    assert!(c.has_access("mem_free".into(), outsider()));
    as_payer(developer(), PRICE);
    c.purchase_memory("mem_free".into());
}

// ---------------------------------------------------------------- withdrawals

fn with_earnings() -> SwarmMemory {
    let mut c = setup();
    as_payer(developer(), PRICE);
    c.purchase_memory("mem_1".into());
    c
}

fn callback_ctx(result: PromiseResult) {
    testing_env!(
        ctx(owner(), 0, 1_000).build(),
        test_vm_config(),
        RuntimeFeesConfig::test(),
        Default::default(),
        vec![result]
    );
}

#[test]
fn withdraw_zeroes_balance_and_locks_until_callback() {
    let mut c = with_earnings();
    as_caller(researcher());
    let _ = c.withdraw_rewards();
    assert_eq!(c.get_earnings(researcher()).0, 0, "balance zeroed before transfer");
    assert!(c.is_withdrawal_pending(researcher()));

    callback_ctx(PromiseResult::Successful(vec![]));
    assert!(c.on_withdraw_complete(researcher(), U128(PRICE), Ok(())));
    assert!(!c.is_withdrawal_pending(researcher()));
    assert_eq!(c.get_earnings(researcher()).0, 0);
    assert_eq!(c.get_stats().total_withdrawn.0, PRICE);
}

#[test]
fn failed_transfer_restores_balance() {
    let mut c = with_earnings();
    as_caller(researcher());
    let _ = c.withdraw_rewards();
    callback_ctx(PromiseResult::Failed);
    assert!(!c.on_withdraw_complete(researcher(), U128(PRICE), Err(PromiseError::Failed)));
    assert_eq!(c.get_earnings(researcher()).0, PRICE);
    assert!(!c.is_withdrawal_pending(researcher()));
    assert_eq!(c.get_stats().total_withdrawn.0, 0);
}

#[test]
#[should_panic(expected = "No pending withdrawal")]
fn callback_without_pending_withdrawal_rejected() {
    let mut c = with_earnings();
    callback_ctx(PromiseResult::Failed);
    // a forged "failed transfer" must not mint earnings
    c.on_withdraw_complete(researcher(), U128(PRICE * 1000), Err(PromiseError::Failed));
}

#[test]
#[should_panic(expected = "Withdrawal already in progress")]
fn double_withdraw_blocked_while_pending() {
    let mut c = with_earnings();
    as_caller(researcher());
    let _ = c.withdraw_rewards();
    // new earnings arrive while the first transfer is in flight
    as_payer(outsider(), PRICE);
    c.purchase_memory("mem_1".into());
    as_caller(researcher());
    let _ = c.withdraw_rewards();
}

#[test]
#[should_panic(expected = "Nothing to withdraw")]
fn withdraw_with_zero_balance_rejected() {
    let mut c = setup();
    as_caller(verifier());
    let _ = c.withdraw_rewards();
}

#[test]
#[should_panic(expected = "Method on_withdraw_complete is private")]
fn callback_is_private() {
    let mut c = with_earnings();
    testing_env!(
        ctx(researcher(), 0, 1_000).build(),
        test_vm_config(),
        RuntimeFeesConfig::test(),
        Default::default(),
        vec![PromiseResult::Failed]
    );
    c.on_withdraw_complete(researcher(), U128(PRICE * 1000), Err(PromiseError::Failed));
}

// ---------------------------------------------------------------- reputation / permissions

#[test]
fn owner_updates_reputation_with_history() {
    let mut c = setup();
    as_caller(owner());
    assert_eq!(c.update_reputation(researcher(), 5, "memory_confirmed".into(), Some("mem_1".into())), 5);
    assert_eq!(c.update_reputation(researcher(), -8, "memory_disputed".into(), None), -3);
    assert_eq!(c.get_agent(researcher()).unwrap().reputation, -3);
    let hist = c.get_reputation_history(None, None);
    assert_eq!(hist.len(), 2);
    assert_eq!(hist[1].new_score, -3);
}

#[test]
#[should_panic(expected = "Only the owner can call this")]
fn non_owner_cannot_change_reputation() {
    let mut c = setup();
    as_caller(researcher());
    c.update_reputation(researcher(), 50, "self_promotion".into(), None);
}

#[test]
#[should_panic(expected = "Invalid delta")]
fn reputation_delta_bounded() {
    let mut c = setup();
    as_caller(owner());
    c.update_reputation(researcher(), 1000, "too_much".into(), None);
}

#[test]
#[should_panic(expected = "Unknown agent")]
fn reputation_requires_registered_agent() {
    let mut c = setup();
    as_caller(owner());
    c.update_reputation(outsider(), 1, "x".into(), None);
}
