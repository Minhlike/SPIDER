# SPIDER Architecture

## 1. Discrete Graph Model
SPIDER maintains three distinct graph representations:
- **Control Graph (DAG)**: Defines capabilities, prerequisites, routing rules, execution policies, budgets, and workflow templates.
- **Execution Graph**: Tracks runs, task instances, provider states, retries, timing, and errors.
- **Knowledge Graph (Multi-di-graph)**: Models observables, entities, assertions, relationships, and evidence pointers.

## 2. Single DB Writer Pattern
To avoid SQLite lock contention during parallel provider execution:
1. Worker coroutines push observations and raw artifact metadata to an asynchronous `IngestQueue`.
2. A single `SingleDBWriter` coroutine consumes the queue and performs atomic batch transactions on SQLite with Write-Ahead Logging (`WAL`) enabled.
3. Read operations run concurrently using async read-only sessions.

## 3. Evidence-First Data Flow
- Providers execute in isolated subprocesses.
- Raw outputs are hashed with SHA-256 and stored in `data/runs/<run-id>/<artifact-id>.raw`.
- Observations record upstream source, family, and cryptographic raw artifact hash.
- Entities and Assertions are materialized derived views.
