# SPIDER Architecture Review & Self-Critique

This document critically reviews the SPIDER architectural design against key failure modes, technical challenges, and real-world OSINT orchestration risks.

---

## 1. Tool & Vendor Lock-In
- **Risk**: Hardcoding provider-specific assumptions (e.g., CLI arguments, custom output structures) into core scheduling or resolution logic causes structural rot when tools change.
- **Mitigation**: Core only interacts with *Capabilities* and standardized *Observation* / *RawArtifact* objects. Providers implement strict adapter interfaces (BaseProviderAdapter). Tool-specific logic terminates at the adapter boundary.

## 2. Adapter Rot & Upstream Churn
- **Risk**: Upstream OSINT tools update flags, alter stdout format, or deprecate parameters, causing silent runtime failures.
- **Mitigation**: Pinned versions, checksummed binaries, contract test suites against frozen versioned fixtures (	ests/fixtures/<provider>/), and explicit health checks (health()). If upstream breaks, only the adapter is updated without touching core.

## 3. Schema Evolution & Versioning
- **Risk**: As new observable types or metadata fields emerge, legacy SQLite databases fail to deserialize historical observations.
- **Mitigation**: All Pydantic data models include schema_version. SQLite stores raw JSON alongside indexed columns. Database migrations are managed via Alembic.

## 4. Entity Resolution False Positives
- **Risk**: Over-aggressive correlation (e.g., assuming same username across GitHub and Reddit implies the same physical person) corrupts investigation integrity.
- **Mitigation**: Conservative resolution. Shared usernames emit SHARES_USERNAME or POSSIBLY_SAME_IDENTITY assertions with explicit confidence scores and lineage, never automatic SAME_PERSON.

## 5. Graph Explosion & Infinite Expansion
- **Risk**: Recursive pivoting on broad targets (e.g. pivoting on shared ASNs or common hosting IPs) leads to millions of nodes, exhausting memory and execution time.
- **Mitigation**: Deterministic budget enforcement (max_depth, max_entities, max_requests, max_branch_work, diminishing_returns_cutoff). Traversal ledger tracks (entity_id, capability, provider, config_hash) to prevent duplicate expansions.

## 6. Source Independence & False Consensus
- **Risk**: Three providers reporting the same subdomain may all query Certificate Transparency (crt.sh). Treating them as 3 independent confirmations artificially inflates confidence.
- **Mitigation**: Provenance models track upstream_source_family. Confidence scoring weights distinct upstream families rather than raw provider count.

## 7. SQLite Concurrency & Lock Contention
- **Risk**: Multiple concurrent worker tasks attempting simultaneous writes to SQLite cause database is locked errors.
- **Mitigation**: Single DB Writer architecture. Worker tasks publish observations and events to an in-memory asynchronous IngestQueue. A single dedicated writer process/coroutine writes batches to SQLite with WAL (Write-Ahead Logging) enabled.

## 8. Windows Process Isolation & Shell Safety
- **Risk**: Executing OSINT binaries via shell=True or unescaped string formatting allows command injection from malicious target inputs (e.g. example.com; calc.exe).
- **Mitigation**: Strictly use syncio.create_subprocess_exec() with structured argument lists (argv array), never os.system or shell=True. Strict target canonicalization and input validation.

## 9. Dependency Conflicts in Python Runtimes
- **Risk**: SpiderFoot v4.0 requires legacy packages that conflict with modern libraries (Pydantic v2, SQLAlchemy 2.0).
- **Mitigation**: Runtime isolation. Complex tools run in isolated sub-environments or subprocess boundaries, invoked via CLI/API.

## 10. API Quota & Rate Limiting
- **Risk**: Burst queries rapidly exhaust third-party API quotas, leading to IP bans or dropped observations.
- **Mitigation**: Per-provider rate limiters and graceful state handling (RATE_LIMITED, MISSING_CREDENTIAL, DEGRADED). Missing API keys never crash the engine.

## 11. Reproducibility vs Auditability
- **Risk**: Internet data changes continuously. Re-running a case months later yields different results, invalidating past evidence.
- **Mitigation**: Source of truth is the immutable observation log + raw artifact files (with SHA-256). The knowledge graph can be completely rebuilt from historical logs without touching the network.

## 12. MCP Coupling
- **Risk**: Embedding Model Context Protocol (MCP) constructs into core models pollutes the core with AI-specific constraints.
- **Mitigation**: Core engine exposes pure Python SpiderService. MCP is an optional adapter layer (spider[mcp]) consuming SpiderService. If MCP is uninstalled, SPIDER retains 100% functionality.
