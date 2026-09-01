# NEXT ACTIONS — PHASE 4: UNCOVER INTEGRATION

1. Implement Uncover adapter (`src/spider/providers/uncover/adapter.py`):
   - Capability: `INTERNET_INTELLIGENCE`
   - Accepts: `[DOMAIN, IP_ADDRESS, ORGANIZATION]`
   - Produces: `[IP_ADDRESS, HOSTNAME, URL, CERTIFICATE]`
   - Missing credential state handling: If API keys (Shodan, Censys, etc.) are missing, transition state to `MISSING_CREDENTIAL` or `DEGRADED` without causing SPIDER or the case to fail.
2. Create frozen contract fixture in `tests/fixtures/uncover/v1.2.1_sample.jsonl`.
3. Create contract tests (`tests/contract/test_uncover.py`).
4. Run full test suite and verify 100% pass.
5. Proceed to Phase 5 (CLI, MCP Server, Docs, Final Audit).
