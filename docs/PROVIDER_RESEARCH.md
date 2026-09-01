# SPIDER Provider Research & Verification Matrix

| Provider | Upstream Repository | Target Version | License | Windows Support | Delivery Mechanism | Input/Output Format |
|---|---|---|---|---|---|---|
| **Subfinder** | projectdiscovery/subfinder | v2.16.0 | MIT | Native Win64 (.exe) | Pinned binary zip with checksums | Input: -d <domain>, Output: JSONL (-oJ -silent) |
| **Metabigor** | j3ssie/metabigor | v2.2.0 | MIT | Native Win64 (.exe) | Pinned binary zip with checksums | Input: Subcommands (
et, sn), Output: Plain text/JSON |
| **Uncover** | projectdiscovery/uncover | v1.2.1 | MIT | Native Win64 (.exe) | Pinned binary zip with checksums | Input: -q <query>, Output: JSONL (-oJ -silent) |
| **Maigret** | soxoj/maigret | v0.6.5 | MIT | Native Python (pip/isolated) | Python package / module | Input: <username> --json raw, Output: JSON report |
| **SpiderFoot**| smicallef/spiderfoot | v4.0 | MIT | Native Python (isolated venv) | Headless CLI / sf.py -s <target> | Input: CLI args, Output: CSV/JSON/SQLite export |

## Verification Details
1. **Subfinder (v2.16.0)**:
   - Checksum asset: subfinder_2.16.0_checksums.txt
   - Windows AMD64 asset: subfinder_2.16.0_windows_amd64.zip
   - Exit codes: 0 on success.
   - Capability: SUBDOMAIN_DISCOVERY.

2. **Metabigor (v2.2.0)**:
   - Checksum asset: checksums.txt
   - Windows AMD64 asset: metabigor_v2.2.0_windows_amd64.zip
   - Capability: INFRASTRUCTURE_DISCOVERY.

3. **Uncover (v1.2.1)**:
   - Checksum asset: uncover_1.2.1_checksums.txt
   - Windows AMD64 asset: uncover_1.2.1_windows_amd64.zip
   - State handling: Requires API keys (Shodan, Censys, etc.) to perform queries. When keys are absent, reports MISSING_CREDENTIAL and exits gracefully.
   - Capability: INTERNET_INTELLIGENCE.

4. **Maigret (v0.6.5)**:
   - Python 3.10+ async engine.
   - Outputs rich JSON reports with URL proofs for found social accounts.
   - Capability: USERNAME_DISCOVERY.

5. **SpiderFoot (v4.0)**:
   - OSINT automation platform with ~200 modules.
   - Runs in headless CLI mode (python sf.py -s <target> -m <modules> -o json).
   - Capability: BROAD_OSINT.
