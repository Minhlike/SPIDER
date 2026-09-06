# Current work: Agent investigation increment 2 (2026-09-06)

Repository: `D:\PhanMem_Tools\SPIDER`; original baseline `069fa49a`.
Report language commit: `ae23c81`. Current increment and limits:
`docs/AGENT_INVESTIGATION_INCREMENT_2.md`; plan `docs/AGENT_INVESTIGATION_PLAN_VI.md`.
User authorized implementation and commit/push; verify live HEAD and remote.

Verified full offline suite: **415 passed, 1 deselected in 105.37s**. Includes
14 Chromium in-process UI tests and two real official MCP stdio client tests.
No production listener or live-provider/personal-target search was started.
No real credentials used or changed. The prior supplied phone was only normalized
in the previous increment; its value remains absent from these artifacts.

Implemented: shared VI/EN report language across UI/export/CLI and MCP explanation;
15 stdio tools including case/target discovery, scoped entity IDs, one-capability
pivot, durable UUID receipts, status, owned cancellation and evidence annotations.
Exact typed/namespace/seed proof required; seed input excluded from evidence reviews.
Cancellation preserves committed evidence and graph atomically. Old annotation
retries do not undo newer reviews. Detached runs never automatically replay.

M2 fixture gate passed; external-provider actions remain NOT YET VERIFIED LIVE.
Full M1-M6 is not complete. Next: atomic pre-I/O reservations for Uncover/Maigret,
then global/provider/origin bounded concurrency and deterministic ingest benchmark.
Do not equate post-dispatch receipts with reservations. Existing actions are serial
within their queue, not a global multi-run scheduler. Continue M1 snapshot/delta,
M4 owned browser workflow, M5 PHONE candidates/consented holdout and M6 graph UX.
Do not claim speedup or identification accuracy from synthetic tests.

## Historical notes (superseded status; retain for traceability)

# Current work: research-plan fixture implementation complete (2026-09-04)

Repository: `D:\PhanMem_Tools\SPIDER`. HEAD remains `b78ac038a65c5c0b215322de3acfa49e3b3fd25a`; all research-plan changes are uncommitted for review. Historical pause context is `memory/HANDOFF_P0_DEV_PAUSED.md`; completion handoff is `memory/HANDOFF_RESEARCH_PLAN_IMPLEMENTED.md`.

Milestones A-E in `docs/RESEARCH_UPGRADE_PLAN_VI.md` now have conservative fixture implementations and regression coverage. Milestone F remains `DEFER / NOT YET VERIFIED`: no live consented holdout, per-service TOS/drift evidence, or adoption gate exists, so no new provider or cost-aware scheduler was added.

Final offline gate: **284 passed, 1 deselected in 74.01s**. It excludes `tests/e2e` because it opens a SPIDER listener, two live integration files, and the one external DNS test. Chromium in-process UI: **10 passed**. `pip check`, compile, diff whitespace, tracked-secret/runtime-artifact hygiene: PASS. No production backend, real target, `.env.local`, user database, or real credential was used.

Next authorized action is review and commit/push. Do not infer an Internet accuracy claim from the 7-site synthetic benchmark, and do not ADOPT Milestone F without its documented gates.

## IP intelligence development (2026-09-05)

WhatIsMyIP v1 is now integrated as a credentialed `IP_ENRICHMENT` provider. The UI stores its key in DPAPI, verifies it without exposing it, can fill the current public IPv4/IPv6 only after the user selects the target type, and renders a sourced report combining WhatIsMyIP geolocation/proxy data with global RDAP, BGP and reverse DNS. Credentialed requests bypass replay cache and are recorded as credentialed egress; private/reserved IP addresses never leave the machine.

Verification: **362 passed, 1 deselected in 87.87s** for the complete offline suite; real Chromium UI was included. Project-local `pip check`, Python compile, Go bridge tests, diff whitespace, ignored-secret and tracked-runtime scans passed. A minimal live check using `.env.local` returned `VALID`, and a documentation IP lookup completed with two accounted requests and three observations. No local backend was started, no personal IP was printed, and no credential was written to a tracked file. The separate listener-opening E2E and unrelated live-provider tests were deliberately not run.
