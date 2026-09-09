# Current work: Agent investigation increment 3 (2026-09-06)

Repository: `D:\PhanMem_Tools\SPIDER`; original baseline `069fa49a`.
Increment baseline: `7e92711`. Report: `docs/AGENT_INVESTIGATION_INCREMENT_3.md`.
Plan: `docs/AGENT_INVESTIGATION_PLAN_VI.md`. User authorized implementation,
commit and push; verify live HEAD/remote before continuing.

Final offline gate after the browser-report regression fix: **441 passed, 1 deselected in 132.36s**.
Includes 14 Chromium in-process UI tests and two official MCP stdio client tests.
Go private-runner tests/build, pip check, compile and diff whitespace: PASS.
No production listener, real-person investigation or real-credential test started.
Credential/settings schema unchanged; local runtime binary rebuilt and stays ignored.

Browser/report regression fixed: coverage now accepts legacy list-valued provider
outcomes instead of crashing the case-insights endpoint. Personal-target preflight
states that the primary action opens Cốc Cốc. Browser launch failures now distinguish
profile-in-use, missing runtime, browser closed and generic startup failure without
exposing profile paths or Playwright diagnostics. A controlled local browser check
for a user-supplied public username returned Instagram and Threads candidates; this
is a candidate result, not identity verification.

Implemented M3: parent permits before every Maigret/Uncover HTTP attempt,
shared per-run atomic cap, task attribution, global/provider/origin limits,
ordered entity admission/atomic ingest, cancellation/drain, bounded HTTP pools,
anonymous run-scoped replay/coalescing, bounded TTL/cache and 429 backoff.
General runs default to 2 independent providers (1-4 configurable), global 4,
per-provider 1, request global 8 and per-hostname 2. MCP action queue stays serial.

Controlled benchmark: 20 trials at each width, same synthetic evidence/graph,
wall p50 685.521/505.342/403.211 ms at 1/2/4; request attempts 4 for each.
This is not Internet speed, UI latency or identification-accuracy evidence.
Full metrics and restrictions are in the increment report. M3 PASS FIXTURE;
not a universal graph-equality claim when sources compete for the final permits.

M1 snapshot/delta and history/graph continuation are implemented in increment 4;
their cursors are scope-bound and process-local. Projection now follows reachable
branches only; run-comparison continuation is also implemented. Next P0:
hard-bound/replay reachable projection. M4 owned-tab workflow trace and M5 public
candidate digest are fixture-complete but live/holdout gates remain. Next M6
evidence reasoning/telemetry/graph UX, then M4 live navigation/pivot and M5
consented holdout.
Then M4 owned browser workflow, M5 PHONE public candidates/consented holdout,
M6 evidence reasoning/telemetry/graph UX. Full M1-M6 remains incomplete.
Keep seed input excluded from findings/evidence, deterministic core independent
of AI, uncertainty explicit, and no extra provider without adoption evidence.

## Historical notes (superseded status; retain for traceability)

# Current work: research-plan fixture implementation complete (2026-09-04)

Repository: `D:\PhanMem_Tools\SPIDER`. HEAD remains `b78ac038a65c5c0b215322de3acfa49e3b3fd25a`; all research-plan changes are uncommitted for review. Historical pause context is `memory/HANDOFF_P0_DEV_PAUSED.md`; completion handoff is `memory/HANDOFF_RESEARCH_PLAN_IMPLEMENTED.md`.

Milestones A-E in `docs/RESEARCH_UPGRADE_PLAN_VI.md` now have conservative fixture implementations and regression coverage. Milestone F remains `DEFER / NOT YET VERIFIED`: no live consented holdout, per-service TOS/drift evidence, or adoption gate exists, so no new provider or cost-aware scheduler was added.

Final offline gate: **284 passed, 1 deselected in 74.01s**. It excludes `tests/e2e` because it opens a SPIDER listener, two live integration files, and the one external DNS test. Chromium in-process UI: **10 passed**. `pip check`, compile, diff whitespace, tracked-secret/runtime-artifact hygiene: PASS. No production backend, real target, `.env.local`, user database, or real credential was used.

Next authorized action is review and commit/push. Do not infer an Internet accuracy claim from the 7-site synthetic benchmark, and do not ADOPT Milestone F without its documented gates.

## IP intelligence development (2026-09-05)

WhatIsMyIP v1 is now integrated as a credentialed `IP_ENRICHMENT` provider. The UI stores its key in DPAPI, verifies it without exposing it, can fill the current public IPv4/IPv6 only after the user selects the target type, and renders a sourced report combining WhatIsMyIP geolocation/proxy data with global RDAP, BGP and reverse DNS. Credentialed requests bypass replay cache and are recorded as credentialed egress; private/reserved IP addresses never leave the machine.

Verification: **362 passed, 1 deselected in 87.87s** for the complete offline suite; real Chromium UI was included. Project-local `pip check`, Python compile, Go bridge tests, diff whitespace, ignored-secret and tracked-runtime scans passed. A minimal live check using `.env.local` returned `VALID`, and a documentation IP lookup completed with two accounted requests and three observations. No local backend was started, no personal IP was printed, and no credential was written to a tracked file. The separate listener-opening E2E and unrelated live-provider tests were deliberately not run.
