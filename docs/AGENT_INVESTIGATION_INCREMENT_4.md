# Investigation increment 4 — stable reads

Baseline: `069fa49a2b9eb500f1fa150775547d3851d2b509`. This increment advances
M1 only. It does not change providers, credentials, browser behavior, identity
labels, or the completed M3 scheduler/data plane.

## FACT — implemented

- `case_digest` now issues an opaque, integrity-protected snapshot scoped to
  case, target and question. Evidence and task-history continuations reject a
  cursor from a different scope or snapshot.
- `case_delta` reads observations recorded after a prior digest snapshot and
  freezes its own page set. An empty delta never means a source or account has
  disappeared.
- `compare_runs` now exposes a paged, snapshot-scoped change list in addition
  to its compatibility summary arrays. The observed/not-observed distinction
  remains explicitly non-conclusive.
- `graph_neighbors` has matching scoped snapshot pagination. The output stays
  limited to typed entity IDs, assertion IDs and transform contracts; no raw
  browser content, artifact, cookie, credential, or query URL is added.
- Seed reachability now queries only children of already reachable typed
  identities and fetches only matching entities, instead of loading unrelated
  case entities or unreachable seed branches before filtering.
- Cursors are process-local and deliberately expire after service restart. This
  prevents a stale cursor from silently mixing different in-memory key epochs;
  callers request a new digest instead.

## EXPERIMENT RESULT

The existing synthetic digest benchmark remains the only measured latency/byte
baseline: 20 samples, 200-account fixture, no network, reported in increment 1.
This increment adds correctness regression coverage, not a speed claim.

## Validation

- A synthetic regression appends evidence after the first digest snapshot. The
  old cursor remains stable, while `case_delta` returns exactly the new evidence.
- Cross-target use of a snapshot is rejected. Existing scoped evidence, graph,
  lifecycle and official stdio checks remain in the offline suite.

## NOT YET VERIFIED / next work

- M1 remains **PARTIAL**: a very large reachable branch can still require a
  complete traversal. No claim of hard bounded full-projection cost is made.
- M4 browser workflow, M5 PHONE public candidates and M6 reasoning/UX remain
  planned. No real-person target, provider key or production listener was used.
