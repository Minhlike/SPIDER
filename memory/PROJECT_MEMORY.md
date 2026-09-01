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
