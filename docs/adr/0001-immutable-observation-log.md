# ADR 0001: Immutable Observation Log as Single Source of Truth

## Context
OSINT data gathered from external network queries is ephemeral and non-reproducible. Storing only a materialized knowledge graph risks permanent loss of evidence if entity resolution rules change.

## Decision
1. All provider outputs are saved as immutable raw artifact files on disk, hashed with SHA-256.
2. Normalized observations are appended to an immutable observation ledger in SQLite.
3. The materialized knowledge graph is a derived view. If resolution logic is upgraded, the knowledge graph can be completely rebuilt from the observation ledger without network requests.

## Consequences
- Requires storage for raw artifacts and observation logs.
- Guarantees 100% auditability, provenance tracking, and offline rebuildability.
