# NEXT ACTIONS — PHASE 5: CLI, MCP ADAPTER, DOCS & FINAL AUDIT

1. Implement full-featured Windows CLI (`src/spider/cli/main.py`):
   - `spider doctor`
   - `spider investigate <target>`
   - `spider collect <target> --capability <cap>`
   - `spider case show <case-id>`
   - `spider run show <run-id>`
   - `spider entity show <id>`
   - `spider evidence <id>`
   - `spider explain <assertion-id>`
   - `spider graph <case-id>`
   - `spider provider list`
   - `spider provider health`
   - `spider rebuild <case-id>`
   - Support both human-readable Rich table/tree output and machine-readable `--json` output.
2. Implement optional MCP server adapter (`src/spider/mcp/server.py`):
   - Exposes semantic tools (`collect`, `expand_entity`, `get_entity`, `get_evidence`, `explain_assertion`, `query_case`, `rebuild_case`).
   - Zero MCP dependency in core; calls `SpiderService`.
3. Complete full documentation in `docs/` and `README.md`:
   - `README.md`
   - `docs/ARCHITECTURE.md`
   - `docs/INSTALLATION.md`
   - `docs/PROVIDER_MATRIX.md`
   - `docs/DATA_MODEL.md`
   - `docs/PROVENANCE.md`
   - `docs/POLICY.md`
   - `docs/THREAT_MODEL.md`
   - `docs/MCP.md`
   - `docs/TESTING.md`
   - `docs/RUNBOOK.md`
   - `docs/TROUBLESHOOTING.md`
   - `docs/LICENSES.md`
   - `docs/ROADMAP.md`
4. Run full test suite and verify 100% pass.
5. Generate Final Compliance Audit Report.
