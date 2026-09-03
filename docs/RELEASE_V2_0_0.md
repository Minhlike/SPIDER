# SPIDER v2.0.0 — release hardening

Date: 2026-09-03. Baseline: `96ebba73e0b58d7f097f24e2a5dc83dcc1053210`, initially clean; baseline suite: **62 passed in 112.13s**. Actual root: `D:\PhanMem_Tools\SPIDER` (the supplied `D:\PhanMem\_Tools\SPIDER` path does not exist).

## Security gate: PASS

API keys are stored as current-user Windows DPAPI ciphertext in ignored `data/api-keys.dpapi`. Non-secret preferences remain in ignored `data/settings.json`. Startup migrates legacy keys by encrypting and verifying the vault before removing plaintext fields. There is no plaintext fallback. Corrupt/unavailable storage fails closed. API responses mask keys, validation failures omit rejected input, and input fields are cleared after a save attempt. Tests use isolated settings paths.

The tracked settings file has been removed from Git's index, preserving the local file. Its one historical revision contained only a verified test placeholder; no genuine service credential was found in that history. The release index contains no local settings, encrypted keys, runtime files, databases or raw artifacts. Tracked private-key/GitHub-token/AWS-access-key pattern checks found no matches. This targeted check is not a guarantee against every possible secret format.

## Browser gate: PASS

Two Chromium E2E scenarios run against a real local Uvicorn server, SQLite, classifier, scheduler, ingestion, WebSocket events and UI. Fixed DNS execution responses isolate public-network variability; no API response or DOM is mocked. Verified: Vietnamese/light defaults, classify, investigate/QUEUED, persisted run identity, running/completed progress, summary, sources, observation evidence, graph nodes/edges and node provenance, plus explained empty results.

The gate exposed broken existing UI/API connections. Repairs restore observation/entity/assertion reads and node provenance, read the existing graph `elements` contract, and derive source counts/empty-state source names from actual provider contributions. Queued runs persist before acknowledgement; failed/cancelled background work reaches a terminal status before DB shutdown. No provider, application framework or new investigation feature was added.

## Windows launcher: PASS

`run_spider.bat` uses the project venv, binds `127.0.0.1:8765`, serializes concurrent starts, records the backend's own PID plus creation time and executable identity, waits for database readiness, then opens the default browser. `start_spider.bat` remains an alias. `stop_spider.bat` signals an instance-specific Windows event and lets Uvicorn shut down. It never kills by executable name or forces termination of a foreign process.

Manual Windows verification: two simultaneous repeat starts reused the same backend PID; its PID matched the listening socket and PID file. Stop logged application shutdown completion, removed state, and released the port. The prior idle legacy backend was separately identified and retired once; the new launcher does not adopt arbitrary existing servers.

## Validation

- Full suite after hardening: **81 passed, 0 failed, 0 skipped in 114.11s**.
- Separate browser rerun: **2 passed in 12.23s**.
- Included: 10 protected-settings regressions, 4 launcher regressions, 3 lifecycle/readiness regressions, 2 browser scenarios, and all 62 original tests.
- `git diff --check`: PASS. Browser screenshots visually checked; traces/screenshots remain local under ignored `test-results/`.
- Release reference: annotated tag `v2.0.0`; resolve with `git rev-parse v2.0.0^{}`. The tag and `main` are published together after validation.

## Remaining limitations

- E2E uses fixed external DNS responses. Existing live tests passed, but public provider latency/rate limits can vary.
- Existing provider adapters still use their pre-existing environment/tool credential configuration. Saving a key in Settings protects persistence but does not add automatic provider credential wiring; that feature is outside this mission.
- The existing local venv still depends on its Python 3.12.8 base installation. This release is not a standalone portable Python distribution.
- A provider's already running blocking work may delay graceful exit. The launcher reports a pending shutdown after 45 seconds and never falls back to a forced kill.
- Historical interrupted RUNNING records in the user's database are preserved; this release does not rewrite old investigation evidence or provide crash-resume recovery.

See [runbook](RUNBOOK.md) and [test instructions](TESTING.md).
