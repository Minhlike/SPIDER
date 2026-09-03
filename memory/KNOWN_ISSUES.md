# Known issues after v2.0.0 release hardening

- Public upstream services can be slow or rate limited; browser E2E uses fixed DNS execution data while the original live tests remain in the full suite.
- Keys saved in Settings are Windows-DPAPI protected; provider adapters retain their existing environment/tool credential configuration. Automatic Settings-to-provider wiring is outside this mission.
- The project venv depends on the existing Python 3.12.8 base installation; it is not a standalone portable distribution.
- Blocking provider work can delay graceful shutdown. No forced-kill fallback is used.
- Historical interrupted RUNNING records remain in the local DB. No evidence/history migration or crash-resume feature was added.

Security persistence and critical browser-flow release gates pass. See `docs/RELEASE_V2_0_0.md` for scope and verification.
