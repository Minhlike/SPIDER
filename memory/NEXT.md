# Current development pointer

Updated: 12/09/2026.

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
  implemented; Phase P1-A now keeps search-index hits as URL leads and reopens
  exact Instagram/Threads/TikTok routes with at most three owned tabs before
  emitting an ACCOUNT candidate. It now extracts only bounded `rel=me` and
  top-level JSON-LD `sameAs` metadata already rendered in that page, strips URL
  query/fragment data, builds namespace-separated ownership hypotheses and
  chooses a non-dispatching evidence-based next action. P1-B now assigns DNS
  roles from exact record types, separates EMAIL account and mail-infrastructure
  questions, and keeps registry, routing, geolocation, datacenter-network and
  physical-facility semantics distinct. The full suite is 496 tests PASS in
  211.88 seconds on 12/09/2026;
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
  P0-C is PASS on fixtures.
- P1-A USERNAME is PASS on fixtures: direct checks remain authoritative;
  Cốc Cốc results cannot promote an ACCOUNT by themselves; a successful exact
  route revalidation records USERNAME → URL → ACCOUNT lineage and keeps
  ownership unverified. Blocked/unopened leads remain URL-only and PARTIAL.
  Coverage and VI/EN UI distinguish revalidated profiles from unverified search
  links. Public self-links create relationship proofs and per-platform ownership
  hypotheses, never verified identity; digest/UI explain the next corroboration
  action. Next: Phase P1-B EMAIL/DOMAIN/IP reasoning. The consented live/manual
  USERNAME holdout remains required before any parity claim.
- P1-B EMAIL/DOMAIN/IP is PASS on fixtures. Reports now state that MX/SPF/DMARC
  cannot identify a person, resolved domain IP can be a CDN edge, RDAP/BGP
  country is not a server location, and IP geolocation/datacenter classification
  does not identify a physical facility. Every structured role/location claim
  carries provider, observation and time context. Physical facility and origin
  stay UNKNOWN because no bundled audited source supports those contracts.
  Next: Phase P1-C PHONE and remaining-input first-class audit.

Do not claim manual-investigation parity, live browser reliability, provider
adoption or the full reasoning engine complete without the master plan gates.
Do not inspect or commit `.env.local`, DPAPI contents, user databases, runtime
artifacts or personal browser state.
