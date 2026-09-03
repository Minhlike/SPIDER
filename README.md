# SPIDER — Evidence-First OSINT Orchestration Engine for Windows

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Platform: Windows](https://img.shields.io/badge/Platform-Windows%20x64-brightgreen.svg)]()
[![Python: 3.12](https://img.shields.io/badge/Python-3.12-blue.svg)]()
[![Tests: 29 Passed](https://img.shields.io/badge/Tests-29%20Passed-success.svg)]()

**SPIDER** is a high-assurance, deterministic, capability-driven OSINT orchestration engine built natively for Windows. It integrates heterogeneous open-source intelligence providers behind strict adapter boundaries into an evidence-first data plane with append-only provenance, conservative entity resolution, explainable assertions, and graph rebuildability.

---

## 🎯 Key Invariants
1. **Core Independence**: Core orchestration does not hard-code tool names or CLI flags. Tools connect through standardized capability adapters.
2. **Immutable Evidence as Single Source of Truth**: All raw provider outputs are saved to disk with SHA-256 hashes. Normalized observations are append-only. The materialized Knowledge Graph can be completely rebuilt offline without network requests.
3. **No AI / MCP Runtime Dependency**: Runs 100% offline and locally on Windows. Model Context Protocol (MCP) is an optional semantic interface calling `SpiderService`.
4. **Conservative Entity Resolution**: Matching usernames emit `SHARES_USERNAME` or `POSSIBLY_SAME_IDENTITY` assertions, never assuming physical identity (`SAME_PERSON`).
5. **Deterministic Scheduling**: Priority scheduler strictly enforces depth, entity, and request budgets to prevent graph explosion.

---

## 🏗️ Architecture Overview

```
External OSINT Tools (Subfinder, Metabigor, SpiderFoot, Maigret, Uncover)
   │
   ▼
[Provider Adapters] ──> Raw Artifact Store (SHA-256)
   │
   ▼
[Ingest Queue] ──> [Single DB Writer] ──> SQLite (WAL Mode)
                                                │
[Observation Log (Immutable Source of Truth)] ◄─┘
   │
   ▼
[Entity Resolution Engine]
   │
   ├─► Materialized Entities & Assertions
   ├─► Explain Engine (Evidence & Lineage Trails)
   └─► NetworkX Analytical Projections (On-Demand)
```

---

## 🚀 Quick Start: Local Web UI & CLI

### Launching Local Web UI (Recommended)
Simply double-click or run:
`cmd
run_spider.bat
`
This automatically starts the backend on 127.0.0.1:8765 and opens your default browser.
The launcher waits for database readiness, reuses the verified backend PID, and refuses to touch an unrelated port occupant. `start_spider.bat` remains a compatibility alias.
To stop the server cleanly:
`cmd
stop_spider.bat
`

### CLI Commands (For Automation & Power Users)

### Diagnostics & Doctor
```powershell
runtime\venv\Scripts\python.exe -m spider.cli.main doctor
```

### Run an Investigation
```powershell
runtime\venv\Scripts\python.exe -m spider.cli.main investigate example.com
```

### Trace & Explain Assertions
```powershell
runtime\venv\Scripts\python.exe -m spider.cli.main explain <ASSERTION_ID>
```

### Rebuild Knowledge Graph from Observation Log
```powershell
runtime\venv\Scripts\python.exe -m spider.cli.main rebuild <CASE_ID>
```

### Provider List & Health Check
```powershell
runtime\venv\Scripts\python.exe -m spider.cli.main provider list
runtime\venv\Scripts\python.exe -m spider.cli.main provider health
```

---

## 📦 Supported OSINT Providers

| Provider | Pinned Version | License | Capability | Delivery |
|---|---|---|---|---|
| **Subfinder** | `v2.16.0` | MIT | `SUBDOMAIN_DISCOVERY` | Native Win64 (.exe) |
| **Metabigor** | `v2.2.0` | MIT | `INFRASTRUCTURE_DISCOVERY` | Native Win64 (.exe) |
| **SpiderFoot** | `v4.0` | MIT | `BROAD_OSINT` | Python 3 Adapter |
| **Maigret** | `v0.6.5` | MIT | `USERNAME_DISCOVERY` | Python 3 Adapter |
| **Uncover** | `v1.2.1` | MIT | `INTERNET_INTELLIGENCE` | Native Win64 (.exe) |

---

## 📚 Complete Documentation
- [Architecture & Design](docs/ARCHITECTURE.md)
- [Architecture Review & Self-Critique](docs/ARCHITECTURE_REVIEW.md)
- [Data Model & Versioning](docs/DATA_MODEL.md)
- [Provenance & Independent Source Families](docs/PROVENANCE.md)
- [Network Policy & Safety](docs/POLICY.md)
- [Provider Research & Verification](docs/PROVIDER_RESEARCH.md)
- [Threat Model & Security](docs/THREAT_MODEL.md)
- [Model Context Protocol (MCP)](docs/MCP.md)
- [Testing & Verification](docs/TESTING.md)
- [Runbook & Operations](docs/RUNBOOK.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)
- [Licenses](docs/LICENSES.md)
- [Roadmap](docs/ROADMAP.md)
