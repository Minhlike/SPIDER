# SPIDER v2.0.0 — release hardening complete

Do not redo V2 Core/Product work or create a new roadmap. Current release handoff: `docs/RELEASE_V2_0_0.md`; baseline `96ebba7`; release reference `v2.0.0`.

Security PASS (Windows DPAPI); pytest 81 passed; separate E2E 2 passed; Windows duplicate-launch/PID/clean-stop verification PASS. Start with `run_spider.bat`, stop with `stop_spider.bat`, web `http://127.0.0.1:8765`.

For future authorized work, read release limitations first. Settings credential-to-provider wiring, portable runtime packaging and interrupted-run recovery remain outside this release. No additional feature work is authorized by this handoff.
