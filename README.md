# SPIDER — Evidence-First OSINT Orchestration Engine for Windows

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Platform: Windows](https://img.shields.io/badge/Platform-Windows%20x64-brightgreen.svg)]()
[![Python: 3.12](https://img.shields.io/badge/Python-3.12-blue.svg)]()
[![Tests](https://img.shields.io/badge/Tests-pytest-blue.svg)](docs/TESTING.md)

**SPIDER** is a high-assurance, deterministic, capability-driven OSINT orchestration engine built natively for Windows. It integrates heterogeneous open-source intelligence providers behind strict adapter boundaries into an evidence-first data plane with append-only provenance, conservative entity resolution, explainable assertions, and graph rebuildability.

---

## 🎯 Key Invariants
1. **Core Independence**: Core orchestration does not hard-code tool names or CLI flags. Tools connect through standardized capability adapters.
2. **Immutable Evidence as Single Source of Truth**: All raw provider outputs are saved to disk with SHA-256 hashes. Normalized observations are append-only. The materialized Knowledge Graph can be completely rebuilt offline without network requests.
3. **No AI / MCP Runtime Dependency**: Runs locally on Windows. Public lookups require network access; stored evidence and graph rebuilds remain available offline. Model Context Protocol (MCP) is an optional semantic interface calling `SpiderService`.
4. **Conservative Entity Resolution**: Matching usernames emit `SHARES_USERNAME` or `POSSIBLY_SAME_IDENTITY` assertions, never assuming physical identity (`SAME_PERSON`).
5. **Bounded Scheduling**: The scheduler enforces depth, runtime and provider-call limits. Username coverage has an explicit site limit; a site lookup can involve redirects or an additional control request.

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
```cmd
run_spider.bat
```
This automatically starts the backend on 127.0.0.1:8765 and opens your default browser.
The launcher waits for database readiness, reuses the verified backend PID, and refuses to touch an unrelated port occupant. `start_spider.bat` remains a compatibility alias.
To stop the server cleanly:
```cmd
stop_spider.bat
```

### Public profile development after v2.0.0

Username searches now offer 50, 500 or all eligible catalogue sites, public
page titles/descriptions, per-site coverage and partial results. Positive
status-only checks use a random control to detect generic pages that claim
every username exists. Email lookup checks exact email values in public GitHub
profiles and can follow the published handle at the next depth. Neither a
matching handle nor a public page title establishes a person's identity.

See the [development plan](docs/PUBLIC_FOOTPRINT_PLAN.md) and the
[implementation report in Vietnamese](docs/PUBLIC_FOOTPRINT_REPORT_VI.md), with the
[reproducible benchmark protocol](benchmarks/README.md). The v2.0.0 release tag
does not include these subsequent local development changes.


See the [source audit and research-based upgrade plan](docs/RESEARCH_UPGRADE_PLAN_VI.md).
Ambiguous inputs now require a type choice before execution; API and MCP clients
can pass `target_type`, and CLI users can pass `--type USERNAME` or `--type DOMAIN`.

### CLI Commands (For Automation & Power Users)

### Diagnostics & Doctor
```powershell
runtime\venv\Scripts\python.exe -m spider.cli.main doctor
```

### Run an Investigation
```powershell
runtime\venv\Scripts\python.exe -m spider.cli.main investigate example.com --type DOMAIN
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
