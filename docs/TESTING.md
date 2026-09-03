# SPIDER Testing Suite

## Release gates

Run from the repository root with the existing project-local runtime:

```powershell
runtime\venv\Scripts\python.exe -m pip install "playwright==1.58.0"
$env:PLAYWRIGHT_BROWSERS_PATH = "$PWD\runtime\playwright"
runtime\venv\Scripts\python.exe -m playwright install chromium --only-shell
runtime\venv\Scripts\python.exe -m pytest -q
runtime\venv\Scripts\python.exe -m pytest tests\e2e -q
```

Playwright and its browser live under `runtime/`; no system browser install is needed. The E2E gate is mandatory for release, not silently skipped when dependencies are missing. It launches Chromium, a real Uvicorn server on a free loopback port, and isolated SQLite/settings/artifact files. Only external DNS execution uses fixed responses; classifier, queue, engine, ingestion, provenance, APIs, WebSocket events, DOM and graph rendering are real. This verifies product wiring, not public-provider availability. Existing full-suite live tests still exercise external providers.

The two browser scenarios cover Vietnamese/light defaults, classification, QUEUED response with the same persisted run ID, running/completed progress, summary, source contribution, evidence JSON, graph nodes/edges and provenance, plus an explained empty result. Screenshots and traces are ignored under `test-results/`.

Security regressions exercise real Windows DPAPI, legacy migration, corrupt vaults, failed encryption, masked updates, deletion, and validation errors without reflected secrets. All tests redirect settings to temporary storage. Launcher regressions cover stale/reused PIDs, occupied ports, duplicate starts and readiness. Lifecycle tests verify persisted queued/failure/cancelled states and shutdown before DB closure.

## Test suites
- **Unit Tests (`tests/unit/`)**: Canonicalization, schemas, policies, budget exhaustion, deterministic scheduling, CLI/MCP inference.
- **Contract Tests (`tests/contract/`)**: Versioned fixture parsing and health checks for Subfinder, Metabigor, SpiderFoot, Maigret, and Uncover.
- **Integration Tests (`tests/integration/`)**: Full vertical slice (`DOMAIN` -> `HOSTNAME` -> `IP` -> `ASN` -> `CIDR` -> `ORGANIZATION`).
- **Resilience Tests (`tests/resilience/`)**: Timeout handling, failure isolation.
- **Security Tests (`tests/security/`)**: Command injection sanitization.
- **Data Integrity & Rebuild Tests (`tests/integrity/`)**: Full knowledge graph wipe and 100% deterministic reconstruction from observation log.
