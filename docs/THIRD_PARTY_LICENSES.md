# SPIDER Third-Party Licenses & Architectural Boundaries

## 1. Overview & Compliance Philosophy
SPIDER is licensed under the permissive **MIT License**. To maintain strict legal compliance, security boundaries, and modularity:
- External OSINT tools and dependencies are classified by license and execution mode.
- Any copyleft software (e.g. GPL) is strictly isolated as an **independent external process** communicating exclusively across standard OS boundaries (stdin/stdout/stderr via JSON over subprocess pipes).
- SPIDER core never links, imports, or bundles copyleft code within its Python package.

---

## 2. Integrated OSINT Tools License Matrix

| Tool | Version | License / SPDX | Upstream Repository | Execution Isolation Mechanism |
|---|---|---|---|---|
| **Subfinder** | `v2.16.0` | MIT | `github.com/projectdiscovery/subfinder` | Standalone Win64 binary (`tools/subfinder/subfinder.exe`) |
| **Metabigor** | `v2.2.0` | MIT | `github.com/j3ssie/metabigor` | Standalone Win64 binary (`tools/metabigor/metabigor.exe`) |
| **Uncover** | `v1.2.1` | MIT | `github.com/projectdiscovery/uncover` | Standalone Win64 binary (`tools/uncover/uncover.exe`) |
| **Maigret** | `v0.6.5` | MIT | `github.com/soxoj/maigret` | Subprocess CLI (`python -m maigret`) |
| **SpiderFoot** | `v4.0.0` | **GPL-2.0** | `github.com/smicallef/spiderfoot` | **Strict External Subprocess (`sf.py -s ... -o json`)** |

---

## 3. GPL Isolation Guarantees for SpiderFoot
SpiderFoot is released under the **GNU General Public License v2.0 (GPL-2.0)**. 
SPIDER adheres to the Free Software Foundation (FSF) guidelines on process-level separation:
1. **No Source Linking**: SPIDER core does not import `spiderfoot`, `sflib`, or `sfp_*` modules into its Python process space.
2. **Standard Subprocess Interface**: Communication occurs strictly through `asyncio.create_subprocess_exec()` executing `tools/spiderfoot/sf.py` as an independent CLI tool.
3. **Data Plane Decoupling**: Data exchange is performed via standard output JSON streams. SPIDER normalizes and stores raw output with SHA-256 hashes independently.

---

## 4. Core Python Dependencies

| Package | Version | License | Primary Purpose |
|---|---|---|---|
| `pydantic` | `>=2.10.0` | MIT | Strict domain data models & validation |
| `sqlalchemy` | `>=2.0.0` | MIT | Asynchronous database ORM & metadata |
| `aiosqlite` | `>=0.20.0` | MIT | Asynchronous SQLite interface |
| `dnspython` | `>=2.8.0` | ISC | Native zero-key DNS enumeration |
| `networkx` | `>=3.2.1` | BSD-3-Clause | Graph projections & topology analytics |
| `fastapi` | `>=0.110.0` | MIT | Local REST & WebSocket API |
| `uvicorn` | `>=0.30.0` | BSD-3-Clause | ASGI web server |
| `typer` / `rich` | `>=0.12.0` | MIT | High-density Windows CLI & diagnostics |
| `pytest` | `>=8.0.0` | MIT | Automated testing framework |