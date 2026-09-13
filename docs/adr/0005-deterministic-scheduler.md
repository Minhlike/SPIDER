# ADR 0005: Deterministic Priority Scheduler & Budget Ledger

## Context
OSINT recursive expansion can spiral out of control (graph explosion) without strict limits. Non-deterministic scheduling leads to non-reproducible test failures.

## Decision
1. Implement a deterministic priority scheduler using a weighted scoring formula based on expected yield, relevance, novelty, and provider cost.
2. Maintain a traversal ledger keyed by (entity_id, capability, provider, config_hash).
3. Enforce deterministic budget cutoffs (max_depth, max_entities, max_requests, max_provider_calls, diminishing_returns_cutoff).
4. Dispatch independent providers through a bounded sliding window. A released
   execution slot admits the next task immediately; entity admission and graph
   writes still commit in scheduler order.

## Consequences
- Given identical inputs and initial state, scheduling, budget decisions and
  committed evidence order are deterministic. Network completion timing may vary.
- A slow provider no longer creates a fixed-batch barrier for unrelated network
  work. Per-run, per-provider, global and per-origin bounds remain enforced.
