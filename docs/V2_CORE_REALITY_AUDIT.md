# SPIDER V2 CORE REALITY AUDIT & ROOT CAUSE ANALYSIS

- **Audit Date**: 2026-09-01
- **Auditor**: Principal Software Architect & OSINT Platform Lead
- **Target Repository**: `D:\PhanMem_Tools\SPIDER`
- **Audit Baseline Commit**: `c4bb653519d3a040ea8c5bf9d5084d24633c4365`

---

## 1. Executive Summary & Reality Check

While SPIDER V1.0/V1.1 established a rigorous data model (Pydantic v2 schemas, SQLite WAL with Single DB Writer, cryptographic SHA-256 artifact storage, immutable observation logging, and 100% deterministic offline graph rebuilding), a deep runtime audit of the provider layer revealed critical structural deficiencies:

1. **False Health Claims & Phantom Success**: Several adapters hardcoded `health() -> ProviderState.READY` and returned `exit_code=0` with `[]` empty observations when executables or Python packages were absent.
2. **Missing Zero-Key Native OSINT**: The engine was completely dependent on external CLI binaries for basic lookups. When binaries lacked API keys or failed to run, lookups returned 0 enrichment.
3. **EMAIL Observable Dead-End**: Seed emails produced 1 entity and 0 assertions because no provider accepted `ObservableType.EMAIL` and no email decomposition pipeline existed.
4. **Hardcoded Fake Providers in Production**: `FakeProviderA` and `FakeProviderB` were registered by default in production CLI and Web compositions.
5. **SpiderFoot Upstream Schema Disconnect**: The adapter assumed `source` was the module name (instead of parent event data) and hardcoded an artificial 80% confidence score not present in upstream JSON.
6. **Synchronous Web Execution**: Web API ran investigations synchronously, blocking HTTP requests and creating/destroying `SpiderService` per request instead of maintaining a clean application lifespan.

---

## 2. Bug Classification Matrix (P0 / P1 / P2)

| Issue ID | Severity | Component | Summary | Status |
|---|---|---|---|---|
| **BUG-01** | **P0** | `SpiderFootAdapter` | Fake health check & silent empty return on missing script | QUEUED FOR FIX |
| **BUG-02** | **P0** | `MaigretAdapter` | Fake health check & uninstalled Python package | QUEUED FOR FIX |
| **BUG-03** | **P0** | `EmailPipeline` | EMAIL seed observable is a dead-end (0 assertions) | QUEUED FOR FIX |
| **BUG-04** | **P0** | `ZeroKeyEngine` | Missing native DNS, RDAP, and Certificate Transparency | QUEUED FOR FIX |
| **BUG-05** | **P1** | `CompositionRoot` | Fake providers registered in production CLI & Web UI | QUEUED FOR FIX |
| **BUG-06** | **P1** | `TargetClassifier` | Misclassification of `.vn`/`.io` emails and frontend regex duplication | QUEUED FOR FIX |
| **BUG-07** | **P1** | `ServiceLifespan` | Web server creates/destroys DB connections per HTTP request | QUEUED FOR FIX |
| **BUG-08** | **P1** | `BackgroundExec` | Investigation blocks HTTP request; Conflated case/run states | QUEUED FOR FIX |
| **BUG-09** | **P1** | `Metrics & Explain` | Lack of granular provider contribution & empty result explainability | QUEUED FOR FIX |
| **BUG-10** | **P2** | `Licenses` | Incomplete third-party license audit & boundary documentation | QUEUED FOR FIX |

---

## 3. Detailed Bug Analysis & Remediation Strategy

### BUG-01 [P0]: SpiderFoot Adapter Fake Health & Schema Disconnect
- **Symptom**: `spider doctor` reported SpiderFoot as `READY` even when `tools/spiderfoot/sf.py` was absent. Investigations on domains silently produced 0 SpiderFoot observations with `exit_code=0`.
- **Root Cause**: `health()` returned hardcoded `READY`. `execute()` caught missing file and returned `raw=b"[]"`, `exit_code=0`. Parser assumed `entry["source"]` was module name and invented `confidence=80%`.
- **Fix**:
  1. Inspect upstream SpiderFoot v4.0 CLI and JSON schema.
  2. Implement honest `health()`: checks python executable and `sf.py` presence; returns `MISSING_RUNTIME` if absent.
  3. Support safe public profiles (`SF_DOMAIN_PUBLIC`, `SF_EMAIL_PUBLIC`, `SF_IP_PUBLIC`, `SF_USERNAME_PUBLIC`) with explicit module lists.
  4. Parse real upstream JSON schema (`module`, `data`, `source_event_hash`).
- **Regression Test**: `tests/contract/test_spiderfoot_reality.py`.

### BUG-02 [P0]: Maigret Adapter Fake Health & Missing Package
- **Symptom**: `spider doctor` reported Maigret as `READY` when `maigret` was not in `pip list`.
- **Root Cause**: `health()` returned hardcoded `READY` without invoking `python -m maigret --version`.
- **Fix**:
  1. Install `maigret` in `runtime/venv`.
  2. Implement subprocess-based `health()` checking real version output; return `MISSING_RUNTIME` if package fails.
  3. Execute real passive username search with conservative entity resolution rules.
- **Regression Test**: `tests/contract/test_maigret_reality.py`.

### BUG-03 [P0]: EMAIL Seed Observable Dead-End
- **Symptom**: Entering `target="user@example.com"` resulted in 1 entity and 0 assertions.
- **Root Cause**: No provider declared `accepts = [ObservableType.EMAIL]`.
- **Fix**:
  1. Implement `NativeDnsAdapter` and `EmailIntelligencePipeline` accepting `ObservableType.EMAIL`.
  2. Normalize email, extract domain, query MX/SPF/DMARC/RDAP/CT, and query mail server hostnames/IPs.
  3. Produce structured relationship assertions: `EMAIL -> BELONGS_TO_DOMAIN -> DOMAIN`, `DOMAIN -> HAS_MAIL_SERVER -> HOSTNAME`, `HOSTNAME -> RESOLVES_TO -> IP_ADDRESS`.
- **Regression Test**: `tests/integration/test_email_pipeline.py`.

### BUG-04 [P0]: Missing Zero-Key Native Intelligence Baseline
- **Symptom**: Without external CLI binaries or API keys, SPIDER could not resolve DNS, RDAP, or CT.
- **Root Cause**: Zero native OSINT modules.
- **Fix**:
  1. Add `dnspython` to virtual environment.
  2. Implement `NativeDnsAdapter` (A, AAAA, MX, NS, TXT, CNAME, SOA, PTR).
  3. Implement `NativeRdapAdapter` (ICANN/RIR RDAP for IP, ASN, Domain).
  4. Implement `NativeCertificateTransparencyAdapter` (crt.sh JSON parsing).
  5. Include all zero-key native providers in `FREE_PUBLIC` profile.
- **Regression Test**: `tests/unit/test_zero_key_baseline.py`.

### BUG-05 [P1]: Fake Providers in Production Composition Root
- **Symptom**: `fake_a` and `fake_b` displayed in production UI and CLI doctor.
- **Root Cause**: `get_service()` in `src/spider/cli/main.py` registered test mocks.
- **Fix**:
  1. Implement `src/spider/core/factory.py` with `create_spider_service(mode="production"|"test")`.
  2. Production mode ONLY registers real providers.
  3. Web, CLI, and MCP import exclusively from `spider.core.factory`.
- **Regression Test**: `tests/unit/test_composition_root.py`.

### BUG-06 [P1]: Target Classifier Misclassifications
- **Symptom**: `user@corp.vn` was misclassified as `ACCOUNT` because of `.endswith(".com")`.
- **Root Cause**: Naive string matching.
- **Fix**:
  1. Implement centralized `TargetClassifier` (`src/spider/models/classifier.py`) supporting full RFC 5322 emails, IPv4/IPv6, CIDRs, ASNs, Domains, Hostnames, E.164 Phones, Usernames, URLs.
  2. Expose `service.classify_target(raw_input)` and `POST /api/classify`.
- **Regression Test**: `tests/unit/test_classifier.py`.

### BUG-07 [P1]: Web API Connection Per Request Lifespan Bug
- **Symptom**: Every HTTP request started and stopped `SpiderService` and SQLite connections.
- **Root Cause**: Missing application lifespan context.
- **Fix**:
  1. Implement FastAPI `@asynccontextmanager lifespan(app: FastAPI)` managing a single production `SpiderService`.
  2. Inject `app.state.service` into API route dependencies.
- **Regression Test**: `tests/unit/test_web_lifespan.py`.

### BUG-08 [P1]: Synchronous HTTP Investigation & Conflated States
- **Symptom**: `POST /api/investigate` blocked HTTP requests during multi-hop runs. Case and run states were conflated.
- **Root Cause**: Synchronous execution loop in router.
- **Fix**:
  1. Implement asynchronous background runner returning `{"case_id": "...", "run_id": "...", "status": "QUEUED"}` immediately.
  2. Decouple Case State (`OPEN`, `ARCHIVED`) from Run State (`QUEUED`, `RUNNING`, `PARTIAL`, `COMPLETED`, `FAILED`, `CANCELLED`).
  3. Stream execution events over WebSocket.
- **Regression Test**: `tests/integration/test_background_execution.py`.

### BUG-09 [P1]: Provider Contribution Metrics & Empty Result Explainability
- **Symptom**: Empty results gave no explanation of attempted sources, errors, or rate limits.
- **Root Cause**: Lack of granular provider yield tracking.
- **Fix**:
  1. Track per-task metrics: duration, raw items, accepted observations, duplicates, errors.
  2. Return structured provider contribution table and empty result explanation summary.
- **Regression Test**: `tests/unit/test_provider_contributions.py`.

---

## 4. Verification & Release Gate Criteria
All P0 and P1 bugs must be resolved, verified via live passive smoke tests on real public targets (`DOMAIN`, `EMAIL`, `IP`, `USERNAME`), and validated through 45+ automated tests before declaring `READY_FOR_UI`.