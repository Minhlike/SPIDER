# Current development pointer

Updated: 10/09/2026.

The only active development plan is
`docs/MASTER_INVESTIGATION_ENGINE_PLAN_VI.md`. Historical handoffs, increment
reports, ADRs and test reports remain evidence of earlier work; they are not
competing backlogs.

Current verified baseline before this work: `2ccf544116f7c30b15345a83c8cd4eb8d0e802c3`.

Current slice:

- audit and plan consolidation complete;
- nullable total time/request budgets, P0-A browser correctness and Phase P0-B
  durable Stop/checkpoint/resume implemented; full suite 478 tests PASS in
  231.19 seconds on 10/09/2026;
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
- Next: Phase P0-C versioned rule registry, questions/gaps and justification DAG.

Do not claim manual-investigation parity, live browser reliability, provider
adoption or the full reasoning engine complete without the master plan gates.
Do not inspect or commit `.env.local`, DPAPI contents, user databases, runtime
artifacts or personal browser state.
