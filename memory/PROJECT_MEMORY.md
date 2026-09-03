# SPIDER — PROJECT MEMORY

## 1. Core Purpose
SPIDER is an Evidence-First, deterministic, capability-driven OSINT orchestration engine designed natively for Windows. It integrates heterogeneous OSINT tools (Subfinder, Metabigor, SpiderFoot, Maigret, Uncover) into a unified data plane with immutable observation logs, cryptographic raw artifacts (SHA-256), conservative entity resolution, explainable knowledge graph, and deterministic priority scheduling.

## 2. Invariants
- Core is completely decoupled from specific providers and tools.
- Raw evidence / observation logs are the single source of truth.
- Knowledge graph is a materialized projection rebuildable from observation logs.
- Zero AI / LLM / MCP dependency in core execution path. MCP is an optional semantic interface calling SpiderService.
- Windows-first, local-first: Runs natively on Windows without Docker or WSL.
- Conservative entity resolution: Same usernames across services emit SHARES_USERNAME / POSSIBLY_SAME_IDENTITY, never automatic SAME_PERSON.

## 3. Tech Stack
- Python 3.12.8 native on Windows
- Pydantic v2 (versioned data models)
- SQLite with WAL + SQLAlchemy 2.0 (single DB writer architecture)
- Alembic for database migrations
- NetworkX for on-demand graph algorithms & analytical projections
- Typer & Rich for high-clarity CLI
- PyYAML for capability registry & policy configuration
- pytest + pytest-asyncio for multi-layer testing

## 4. v2.0.0 release hardening (2026-09-03)

Baseline `96ebba7`; release reference `v2.0.0`. Completed V2 Core/Product work is preserved. Current handoff: `docs/RELEASE_V2_0_0.md`; operation: `run_spider.bat` / `stop_spider.bat` at `127.0.0.1:8765`.

Security gate: current-user Windows DPAPI in `data/api-keys.dpapi`; non-secret `data/settings.json` separate. Both are ignored. Never write credential values into Git, logs, API responses, memory or handoffs. Tests isolate settings and use synthetic key values only.

Final gates: 81 pytest passed; separate Chromium E2E 2 passed. Browser tests use real API/DB/core with a fixed external DNS boundary. PID/creation-time identity, duplicate-launch prevention and graceful stop verified on Windows. No new providers/frameworks/features. Remaining limits are recorded in the release notes; do not interpret stored Settings keys as automatically configured provider credentials.
