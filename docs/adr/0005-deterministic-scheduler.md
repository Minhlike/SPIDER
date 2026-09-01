# ADR 0005: Deterministic Priority Scheduler & Budget Ledger

## Context
OSINT recursive expansion can spiral out of control (graph explosion) without strict limits. Non-deterministic scheduling leads to non-reproducible test failures.

## Decision
1. Implement a deterministic priority scheduler using a weighted scoring formula based on expected yield, relevance, novelty, and provider cost.
2. Maintain a traversal ledger keyed by (entity_id, capability, provider, config_hash).
3. Enforce deterministic budget cutoffs (max_depth, max_entities, max_requests, max_provider_calls, diminishing_returns_cutoff).

## Consequences
- Given identical inputs and initial state, execution path and decisions are 100% deterministic and reproducible.
