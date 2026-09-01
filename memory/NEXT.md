# NEXT ACTIONS — PHASE 3: MAIGRET INTEGRATION

1. Implement Maigret adapter (`src/spider/providers/maigret/adapter.py`):
   - Capability: `USERNAME_DISCOVERY`
   - Accepts: `USERNAME`
   - Produces: `ACCOUNT`, `URL`
   - Strict conservative resolution: Emits `SHARES_USERNAME` or `POSSIBLY_SAME_IDENTITY` assertions with explicit confidence, never automatic `SAME_PERSON`.
2. Create frozen contract fixture in `tests/fixtures/maigret/v0.6.5_sample.json`.
3. Create contract and conservative resolution tests (`tests/contract/test_maigret.py`, `tests/unit/test_conservative_resolution.py`).
4. Run full test suite and verify 100% pass.
5. Proceed to Phase 4 (Uncover).
