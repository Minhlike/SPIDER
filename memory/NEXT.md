# Current development pointer

Updated: 11/09/2026.

The only active development plan is
`docs/MASTER_INVESTIGATION_ENGINE_PLAN_VI.md`. Historical handoffs, increment
reports, ADRs and test reports remain evidence of earlier work; they are not
competing backlogs.

Current verified baseline before this work: `2ccf544116f7c30b15345a83c8cd4eb8d0e802c3`.

Current slice:

- audit and plan consolidation complete;
- nullable total time/request budgets, P0-A browser correctness and Phase P0-B
  durable Stop/checkpoint/resume implemented; P0-C versioned direct-edge rule
  registry, question/gap projection, claim lifecycle and scoped justification
  DAG, deterministic plan preview and source-specific DNS TTL revalidation
  implemented; full suite 486 tests PASS in 227.55 seconds on 11/09/2026;
- provider quotas, rate limits, per-action timeout, concurrency, dedup and policy
  remain enforced in unlimited mode;
- final diff/document review completed; the suite included its existing public/
  reserved live-smoke targets, but no user identifier, API secret or personal
  Cốc Cốc profile was used;
- Phase P0-A browser correctness is implemented on fixtures: exact profile
  routes, access-state precedence, query-echo rejection, separate search leads
  and per-origin failures. Live Cốc Cốc version/session reliability remains
  NOT YET VERIFIED.
- Per-run Stop retains committed evidence and leaves SPIDER running. Versioned
  typed frontier and cumulative ledger survive clean stop/process restart;
  resume creates one linked child and skips prior terminal/uncertain receipts.
  UI, HTTP and target-scoped MCP resume are covered by fixtures. Live Cốc Cốc
  long-run crash recovery remains NOT YET VERIFIED.
- P0-C now records rule provenance, evaluates versioned target questions/gaps,
  exposes scoped `explain_claim` DAGs through MCP/Web, and gives graph transforms
  typed basis, target/entity scope and required evidence context. Conflicting
  registries fail at load; missing or old evidence remains OPEN/UNKNOWN and
  temporal status is NOT_INFERRED without a source-specific expiry rule. Rebuild
  reproduces the same materialized proof DAG in the vertical fixture. A relevant
  account now leaves a question PARTIAL until its registered capabilities finish;
  `plan_preview` reproduces the same candidate plan/fingerprint from the same
  scoped snapshot and never dispatches. DNS TTL now marks revalidation due
  without claiming disappearance; malformed/cross-provider rules fail closed.
  P0-C is PASS on fixtures. Next: Phase P1-A USERNAME vertical slice; retain the
  live/manual holdout gates before any parity claim.

Do not claim manual-investigation parity, live browser reliability, provider
adoption or the full reasoning engine complete without the master plan gates.
Do not inspect or commit `.env.local`, DPAPI contents, user databases, runtime
artifacts or personal browser state.
