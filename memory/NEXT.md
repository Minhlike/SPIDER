# NEXT ACTIONS — PHASE 2: SPIDERFOOT INTEGRATION

1. Set up SpiderFoot v4.0 integration:
   - SpiderFoot as broad OSINT provider (capability `BROAD_OSINT`, `DNS_INTELLIGENCE`, etc.).
   - Implement `SpiderFootAdapter` behind strict boundary in `src/spider/providers/spiderfoot/adapter.py`.
   - Support headless execution mode and structured export parsing (JSON/SQLite).
2. Create frozen contract fixtures in `tests/fixtures/spiderfoot/v4.0_sample.json`.
3. Implement contract tests (`tests/contract/test_spiderfoot.py`).
4. Implement integration tests and verify full test suite passes.
5. Proceed to Phase 3 (Maigret).
