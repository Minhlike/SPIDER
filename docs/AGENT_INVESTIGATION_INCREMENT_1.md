# Investigation increment 1 — 2026-09-05

Baseline: `069fa49a2b9eb500f1fa150775547d3851d2b509`. This is an incremental
implementation of the retired historical plan (frozen at [baseline 2ccf544](https://github.com/Minhlike/SPIDER/blob/2ccf544116f7c30b15345a83c8cd4eb8d0e802c3/docs/AGENT_INVESTIGATION_PLAN_VI.md)), not completion of M1–M6. Current work is governed by `MASTER_INVESTIGATION_ENGINE_PLAN_VI.md`.

## FACT — implemented

- Optional official MCP SDK stdio transport with typed discovery and nine tools.
  Scoped digest, evidence, graph neighborhood, run comparison/coverage and measured
  telemetry reuse service code. Existing Python dispatcher tools remain compatible.
- Persistent competing hypotheses with scoped evidence roles and UUID idempotency.
  Conflicting action retries and foreign evidence are rejected. No ownership promotion.
- SQL selects observations for the chosen seed before reachability traversal.
  User-supplied seeds remain excluded from findings and evidence.
- Task request receipts replace subtraction of shared global counts. Overlapping
  fixture tasks consuming 1 and 2 requests persist 1 and 2, with a shared cap of 3.
  Missing telemetry measurements remain unknown rather than zero.
- DB write queue bounded to 128, with queue/transaction counters and timings.
  Shutdown rejects new writes and drains accepted transactions before stopping.
- PHONE normalized with pinned `phonenumbers==9.0.38`, including Vietnamese national
  format when explicitly selected and international parenthesized country codes.
  Both Target and NormalizedObservable reject inconsistent canonical overrides.
  Raw seed preserved. Number allocation metadata never verifies the current carrier
  or subscriber. User-authorized phone normalization passed without network access;
  the actual number is absent from this repository's new artifacts.
- UI reads the backend input catalogue. URL/CIDR/ACCOUNT/PHONE choices currently
  lack a metered collection workflow and are disabled, including an automatic-input
  dispatch guard. ORGANIZATION has explicit syntax validation. IPv6 capability and
  DNS acceptance mismatch fixed. Coverage safely handles a provider's list-valued status.

## EXPERIMENT RESULT — local read benchmark

Reproduce: `runtime\venv\Scripts\python.exe benchmarks/agent_digest.py`.
Python 3.12.8, AMD64, synthetic 200-account fixture, 20 samples per path, zero
network requests. Paths run in fixed order; first iteration is included. This
compares the old full-graph response with a new 20-evidence page, not equivalent
queries or complete cold/warm before/after application workloads.

| Path | p50 ms | p95 ms | response bytes |
| --- | ---: | ---: | ---: |
| Existing full graph | 6.248 | 7.377 | 47,489 |
| Scoped first-page digest | 8.663 | 31.299 | 4,716 |

The digest response is about 90% smaller for this different output scope, but
was slower. No speedup, token saving, Internet accuracy, UI latency improvement,
or coverage improvement is claimed. Initial pre-filter run was 6.474/8.363 ms
for full graph and 9.282/16.599 ms for digest (p50/p95); these single-process
measurements are insufficient to isolate an optimization effect.

## Validation

- Complete offline gate: **380 passed, 1 deselected in 85.00s**; includes
  13 real Chromium UI tests using the in-process API, and official MCP client
  initialize/discovery/read/create/retry/list over stdio.
- Command: `runtime\venv\Scripts\python.exe -m pytest tests --ignore=tests/e2e --ignore=tests/integration/test_live_smoke.py --ignore=tests/integration/test_email_pipeline.py --deselect=tests/unit/test_zero_key_baseline.py::test_native_dns_email_decomposition_and_resolution -q`.
- Listener-opening E2E, two live integration files and external DNS test were
  excluded. No production web server or real provider search was started.
- Targeted gates cover cross-seed rejection, canonical override rejection,
  idempotency conflict, real stdio hypothesis creation, concurrent task receipts,
  request hard cap and DB drain under backpressure.
- `pip check`, Python compile, diff whitespace, local credential-content scan and
  tracked-runtime/secret-artifact scan: PASS. Only the empty `data/runs/.gitkeep`
  marker is tracked under the raw-artifact directory. Credentials were not used
  for queries, changed or printed. Real phone input is not in committed fixtures.
- Application speed, live PHONE accuracy and complete M1–M6 acceptance: NOT YET VERIFIED.

## NOT YET VERIFIED / next work

1. M1: snapshot/delta protocol, continuation for truncated history/graph/comparison,
   and bounded DB projection cost. The current digest is not a change feed.
2. M2: evidence-linked run-capability/pivot, annotations, cancellation and action
   receipts for every mutation; context discovery for case/target IDs.
3. M3: atomic runner request reservation before I/O, then bounded execution with
   global/provider/origin limits, deterministic ingest and cancellation benchmark.
   Uncover/worker post-dispatch journaling is not atomic shared reservation.
   No default provider concurrency, pooling/coalescing or integrated replay cache yet.
4. M4: browser session/tab provenance, ownership-safe close, linked pivots/resume
   and one-versus-three-tab benchmark. The existing browser implementation is retained.
5. M5: public PHONE candidate extraction, competing identity/temporal evidence,
   ranking reasons and consented ground-truth benchmark. One authorized input and
   offline normalization do not establish identification accuracy.
6. M6: measured scheduling, useful evidence/request, richer deterministic reasoning
   and full investigation UX. No additional provider was adopted.
