# Investigation increment 5 — browser trace and public-phone candidates

This increment implements fixture-safe parts of M4 and M5. It adds no provider,
does not query a real person, and does not use credentials.

## FACT

- Cốc Cốc closes its initial SPIDER-owned tab before direct checks, then opens at
  most three direct-check tabs. Search runs after those tabs close. It closes all
  tabs/context it created and never attaches to a user's existing browser tabs.
- Browser results now carry a bounded workflow trace: action reference, parent
  evidence reference, sanitized URL, capture timestamp, content hash, source,
  result state and reason. MCP `browser_trace` scopes the trace to one target/run
  and removes query strings. Cookies, tokens and page text are never returned.
- Browser partial results require a new explicit action to resume; no automatic
  browser replay occurs after cancellation, block, restart or ambiguity.
- `phone_candidate_digest` projects only structured, literal public phone
  mentions already present in scoped evidence. It returns candidate facts,
  provenance IDs, evidence classes, mirror-aware independence, recency and
  competing candidates. It never produces a subscriber/owner assertion.
- The PHONE intelligence card says “publicly evidenced links”, shows ranking
  reasons and calls out competition. Free-form text cannot manufacture a phone
  link; collector data must provide matching `phone_e164` and an allowed evidence
  class.

## VALIDATION

- 24 focused fixture tests passed: browser limits/trace sanitization, MCP scope,
  candidate competition, explicit literal-phone requirement and existing action
  integrity. No browser executable, provider key, listener or real target used.

## NOT YET VERIFIED

- M4 remains **PARTIAL**: the fixture verifies owned-tab lifecycle and trace,
  not live session navigation or a one-versus-three-tab Internet benchmark.
- M5 remains **PARTIAL**: there is no adopted phone collector or consented
  holdout; live precision, false attribution and freshness are not claimed.

## M6 follow-up — FACT

- Coverage now has a deterministic, non-dispatching next-best-action with a
  recorded basis and cost class. It never chooses a provider or retries a
  network request automatically.
- Telemetry reports useful evidence count and useful-evidence/request only from
  newly observed, sourced, scoped identities. Seed input, duplicate identities
  and replay cache hits do not inflate the metric. Reliability remains explicitly
  uncalibrated until a separately audited dataset exists.
