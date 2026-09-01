# ADR 0003: Single DB Writer Queue for SQLite Concurrency

## Context
SQLite with multiple concurrent writer threads/processes frequently encounters sqlite3.OperationalError: database is locked.

## Decision
Adopt a Single-Writer Architecture:
1. Enable WAL mode on SQLite (PRAGMA journal_mode=WAL;).
2. Concurrent workers publish events and observations to an in-memory IngestQueue.
3. A single asynchronous DB writer coroutine consumes the queue and performs batched atomic transactions.
4. Read queries use read-only database sessions with WAL concurrency.

## Consequences
- Zero lock contention during high concurrency fan-outs.
- High ingestion throughput.
