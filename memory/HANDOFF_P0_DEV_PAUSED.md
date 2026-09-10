# P0 development — PAUSED at user's request, 2026-09-03

## Scope and operating boundaries

- Repository: `D:\PhanMem_Tools\SPIDER`; HEAD: `b78ac038a65c5c0b215322de3acfa49e3b3fd25a`.
- Latest instruction: “tạm dừng công việc đúng cách và an toàn”. Stop development; wait for explicit resumption.
- Development was authorized by “bắt đầu dev theo plan”; the historical source plan is frozen at [baseline 2ccf544](https://github.com/Minhlike/SPIDER/blob/2ccf544116f7c30b15345a83c8cd4eb8d0e802c3/docs/RESEARCH_UPGRADE_PLAN_VI.md). Current work is governed by `docs/MASTER_INVESTIGATION_ENGINE_PLAN_VI.md`.
- All new code/tests remain in the working tree, unstaged and uncommitted. No commit, push or tag in this development turn.
- No production backend/browser launched. No real subject investigation, credential file read, account validation or paid query in this turn. No edits to Uncover credential files, DPAPI/settings implementation or real credentials.
- At pause, the scoped process inspection found no running project Python, pytest or Maigret worker process. The only test command launched in this turn finished with exit code 1. Nothing needed termination.

## Implemented in working tree — NOT a completed release

1. Typed entity identity: case/type/namespace/canonical composite identity and unique index; typed parent lineage, target namespace, scope/frontier comparisons, observation metadata and hashes retained for rebuild. Resolver uses two passes and rejects foreign-case observations; untyped parents do not create guessed edges. Several adapters now supply typed intermediate parents; a compatibility guard clears stale parent types when older adapters replace only the parent string.
2. SQLite startup migration in `storage/migrations.py` and `database.py`: additive columns, replace old unique index, rebuild old materialized graphs from observations inside a transaction. **Migration tests were just added and have NOT run.** It can remove legacy edges lacking typed parent evidence. Do not start against the user's database before reviewing/testing migration and recovery on a temporary copy.
3. Request/entity ledger: admission before normalized observation ingest, persisted run metadata, HTTP transport dispatch counting, explicit DNS UDP/TCP attempts, Maigret worker middleware journal, global request cap. Failed dispatch attempts count; redirect/retry/control requests re-enter the boundary. No network cache currently; `cache_hits_count` is only reserved metadata, not a tested cache implementation.
4. Opaque adapters without request accounting are currently blocked with `UNMETERED_PROVIDER` and produce PARTIAL. This includes Subfinder, Metabigor, SpiderFoot and Uncover in engine runs. **Material functionality limitation; not release-ready.** API-key validation code itself was left untouched. Further work must coordinate with that integration before adding its metering.
5. Provider health defaults `live_verified`/`contract_verified` false and requires matching versioned evidence for positive claims. Provider API/UI exposes both stages, fixes provider-id rendering, and distinguishes availability from live verification. Existing unsupported positive claims now become false; review compatibility with Uncover's prior contract flag without altering credential work.
6. Global ASGI Host/Origin/Sec-Fetch guard for HTTP and WebSockets. Test-only `testserver` allowlist and temporary settings/database/artifact isolation; production allowlist remains loopback only.

## Actual verification evidence

- Ran project-local Python with pytest for: typed identity, original phase0 integrity lifecycle, local boundary security, provider verification, and username worker integration.
- Result at that earlier snapshot: **60 passed, 2 failed**, 13.75 seconds. This is not a result for the final paused working tree.
- Failure 1: positive WebSocket test used a relative TestClient URL, which resolves to testserver rather than the configured loopback base URL. Patched test to use an absolute loopback WebSocket URL; existing websocket fixture given same-origin Origin. **Not rerun.**
- Failure 2: Maigret fixture reported 6/7 sites (a previously observed intermittent coverage issue). Added explicit UNKNOWN records for selected sites missing an upstream result event after search returns. **Root cause and correctness of this change remain unverified; do not merely weaken the test.**
- After that run, added migration success/rollback tests and transport/entity budget tests, adjusted fixture-only adapters, API budget mapping, default DB isolation and provider UI. **None of those later changes has been tested.**
- Final tracked diff whitespace check reported no errors; Git emitted LF/CRLF notices. New untracked files were not covered by that check.
- Full pytest, browser UI/E2E, live providers and production migration have NOT been run for this working tree. No PASS claim is justified for the P0 release gate.

## Resume order (only after user requests)

1. Re-read current Git status/diff; preserve this work and any subsequent parallel API-key edits. Check repository instructions and this plan; do not reimplement completed V2 work.
2. Review migration transaction/rollback/data preservation first using `tests/fixtures/storage/v2_schema.sql` (immutable synthetic baseline schema generated from b78ac03). Never initialize the user's database as a test side effect.
3. Run focused tests using `runtime\venv\Scripts\python.exe`: `tests/integrity/test_typed_identity.py`, `tests/integrity/test_identity_migration.py`, `tests/integration/test_budget_boundaries.py`, `tests/security/test_local_boundary.py`, `tests/unit/test_provider_verification.py`, `tests/integration/test_username_worker.py`, `tests/integrity/test_phase0_core.py`.
4. Add/verify Maigret request journal vs actual loopback request counts, control/redirect/retry coverage and cancellation accounting; verify cache semantics, entity duplicate/repeat-run accounting and persisted progress. Review the UNKNOWN reconciliation change rather than assuming the previous flaky assertion is fixed.
5. Resolve opaque-provider metering limitation; review all adapter parent references and graph/API callers; ensure health UI does not imply a successful live test. Complete offline UI/regression gates before claiming completion.
6. Existing tests include external live requests: `tests/integration/test_live_smoke.py`, `tests/integration/test_email_pipeline.py`, and `test_native_dns_email_decomposition_and_resolution` in `tests/unit/test_zero_key_baseline.py`. Do not blindly run the entire suite under the no-live-data constraint. `tests/e2e` launches a SPIDER server; prefer existing in-process Chromium fixtures under `tests/ui` unless the user authorizes launching.
7. P1 egress ledger and target/question-scoped projection, then later research milestones, are **not implemented**. Do not claim the whole plan complete or begin Cost-Aware Scheduler research before reliable accounting.

When a shell command yields a session ID, preserve the entire tool result and poll that ID; do not accidentally launch duplicate pytest runs. Central Codex memory was not changed.
