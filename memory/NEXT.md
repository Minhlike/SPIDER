# NEXT ACTIONS — PHASE 1: SUBFINDER + METABIGOR

1. Download pinned official Windows x64 binaries:
   - Subfinder v2.16.0 (MIT) from ProjectDiscovery GitHub releases.
   - Metabigor v2.2.0 (MIT) from j3ssie GitHub releases.
2. Verify SHA-256 checksums against official upstream checksums.txt.
3. Place executables in `tools/subfinder/subfinder.exe` and `tools/metabigor/metabigor.exe`.
4. Create frozen contract fixtures in `tests/fixtures/subfinder/` and `tests/fixtures/metabigor/`.
5. Implement `SubfinderAdapter` and `MetabigorAdapter` adhering to `BaseProviderAdapter`.
6. Write contract tests (`tests/contract/test_subfinder.py`, `tests/contract/test_metabigor.py`).
7. Write vertical slice integration test (`tests/integration/test_subfinder_metabigor_slice.py`):
   `DOMAIN (example.com)` -> `HOSTNAME` -> `IP_ADDRESS` -> `ASN`.
8. Run full test suite and verify 100% pass.
