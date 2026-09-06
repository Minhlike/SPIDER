# Investigation increment 2 — 2026-09-06

Baseline for this increment: `ae23c81` (shared reader-friendly reports).
Original plan baseline `069fa49a`; A–E preserved. This is not full M1–M6 completion.

## FACT — implemented

- MCP now supports choosing one graph transform, durable action admission,
  progress receipts and scoped cancellation. Repeated UUIDs do not repeat I/O;
  changed arguments fail. At most 16 queued/running actions, executed serially.
- Derived pivots require a reachable observation with matching type, namespace
  and canonical value. Policy permission never transfers by association.
  Capability, question, provider contract and metering checks precede dispatch.
- Provider ingest rejects foreign case/run/task/provider/seed lineage. For these
  actions, evidence and graph resolution commit atomically. Cancellation preserves
  committed data and marks only the owned task/run; completed runs remain completed.
- Restart uncertainty is explicit. A detached run is not replayed automatically.
  Status returns fixed states and persisted counts, not provider diagnostics,
  raw artifacts, credentials or arbitrary exception text.
- Agent can discover case and target IDs; evidence pages expose scoped entity IDs
  so graph navigation works without copying IDs from the UI.
- Evidence annotations have durable UUID receipts. Retrying an old annotation
  cannot undo a newer review. Seed input remains excluded from evidence reviews.
- Fifteen official stdio tools; service/CLI still have no embedded AI runtime.
  Shared report vocabulary also explains detached-run uncertainty in VI/EN.

## EXPERIMENT RESULT

Synthetic action gates cover simultaneous identical submissions, changed retries,
cross-seed/type/namespace rejection, bounded queue, active/queued cancellation,
committed evidence retention, shutdown/restart, foreign provider lineage and
annotation ordering. A separate official MCP client/process exercises dispatch,
status, retry, discovery, graph navigation, annotation and no-op cancellation.
All action fixtures use the offline fake provider; no provider credits are spent.

Final aggregate gate is recorded in `memory/NEXT.md` and `memory/STATE.json`.
No latency improvement or live identification accuracy is claimed from these tests.

## NOT YET VERIFIED / remaining plan

- M1: snapshot/delta and history/graph continuation, bounded full projection cost.
- M2: API fixture gates implemented; production provider actions not live-verified.
  UI graph controls and fresh-case creation via MCP are not part of this increment.
- M3: atomic pre-I/O reservations for Uncover/Maigret before enabling general
  concurrency; global/provider/origin limits, pooling/coalescing and replay remain.
  Per-action caps and serial admission do not solve shared multi-run accounting.
- M4: owned browser tabs, step provenance and resume. Existing browser provider
  is retained; cancellation does not guarantee saving unreturned worker results.
- M5: PHONE public candidates, temporal competing hypotheses, consented holdout.
- M6: full investigation UX, measured scheduling, useful evidence/request metrics.

No new provider adopted. No production backend or real-person investigation started.
Credentials and settings schema unchanged. Optional SDK/runtime remains project-local.
