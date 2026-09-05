# Research upgrade implementation handoff — 2026-09-04

## State

- HEAD: `b78ac038a65c5c0b215322de3acfa49e3b3fd25a`; working tree intentionally uncommitted.
- Continued from `HANDOFF_P0_DEV_PAUSED.md` without redoing V2 Core/Product or touching API-key/DPAPI code.
- No SPIDER backend/listener was launched. No real person, account, email, username, `.env.local`, user database, or paid API was used.

## Implemented and verified on synthetic fixtures

- Typed entity identity and typed seed lineage; safe legacy migration/rebuild and single-seed backfill.
- Request/entity accounting at HTTP, DNS, Maigret control/retry/redirect, cache and ingest boundaries.
- Fail-closed provider verification plus versioned canary quarantine/recovery.
- Global loopback Host/Origin/Sec-Fetch and WebSocket boundary checks.
- Per-run pseudonymous data-egress ledger and UI disclosure state.
- Target/question-scoped evidence projection, coverage/unknown accounting and no cross-seed insight reuse.
- Explicit public-link proofs, contradiction/dependency review, temporal evidence, and deterministic allowlisted evidence bundles.
- Pinned upstream research/license manifest and offline OVERLAP vs HOLEHE_ONLY scoring protocol.
- NetworkX constrained to the range required by bundled Maigret 0.6.5; project-local editable runtime reinstalled.

## Gates

- Final offline suite: `284 passed, 1 deselected in 74.01s`.
- Chromium in-process UI: `10 passed in 27.75s`.
- Focused evidence/scope/migration/security: `73 passed in 20.39s`.
- `pip check`, compileall, `git diff --check`, and tracked secret/runtime artifact scan: PASS.
- Synthetic 7-site benchmark: SPIDER precision/recall 1.0/1.0 and decision coverage 0.75; this is not an Internet superiority claim.

## Deliberate limits

- `tests/e2e` was not run because it starts a listener; live smoke/email/DNS tests were not run because they contact external services.
- Uncover private runner `secure2` now exports a validated one-request journal and is admitted through the request/egress ledger on offline fixtures. Other opaque subprocess providers without reliable accounting remain fail-closed as `UNMETERED_PROVIDER`; live Uncover credentials/search are not verified.
- Holehe/Socialscan/WhatsMyName, passive sources, and Cost-Aware Scheduler remain deferred until license/TOS, consented holdout, drift and value gates pass.
- Review is required before commit/push; neither was performed.
