# SPIDER Data Model

All domain schemas are implemented in Pydantic v2 with explicit schema versioning (`schema_version: str = "1.0"`).

## Core Models:
- `Case`: Top-level investigation boundary (`id`, `name`, `tags`, `status`, `created_at`).
- `Target`: Seed observable associated with a case (`observable_type`, `raw_input`, `canonical_value`, `scope_authorized`).
- `NormalizedObservable`: Canonicalized entity representation (`type`, `value`, `canonical_value`, `metadata`).
- `SourceLineage`: Provenance metadata (`case_id`, `run_id`, `task_id`, `provider_id`, `provider_version`, `upstream_source`, `upstream_family`, `raw_artifact_sha256`).
- `RawArtifactRef`: Cryptographic disk artifact pointer (`id`, `sha256`, `byte_size`, `mime_type`, `storage_path`).
- `Observation`: Normalized atomic observation record.
- `Entity`: Materialized Knowledge Graph node.
- `Assertion`: Materialized Knowledge Graph directed edge (`source_entity_id`, `target_entity_id`, `assertion_type`, `confidence`, `source_families`).
- `EvidenceRef`: Link connecting an assertion to an observation and raw artifact SHA-256.
