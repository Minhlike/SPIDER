# SPIDER Testing Suite

## Test Suites (29 Tests Total)
- **Unit Tests (`tests/unit/`)**: Canonicalization, schemas, policies, budget exhaustion, deterministic scheduling, CLI/MCP inference.
- **Contract Tests (`tests/contract/`)**: Versioned fixture parsing and health checks for Subfinder, Metabigor, SpiderFoot, Maigret, and Uncover.
- **Integration Tests (`tests/integration/`)**: Full vertical slice (`DOMAIN` -> `HOSTNAME` -> `IP` -> `ASN` -> `CIDR` -> `ORGANIZATION`).
- **Resilience Tests (`tests/resilience/`)**: Timeout handling, failure isolation.
- **Security Tests (`tests/security/`)**: Command injection sanitization.
- **Data Integrity & Rebuild Tests (`tests/integrity/`)**: Full knowledge graph wipe and 100% deterministic reconstruction from observation log.
