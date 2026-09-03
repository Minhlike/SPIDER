# HANDOFF A2→A1
HEAD: cdbf05a
REMOTE_SYNC: unpushed (origin/main is at 1fa6246, local main ahead by 1 commit)
WORKTREE: clean
VERSION: v2.0.0
RELEASE_GATE: PASS (Core data plane & Product UI fully verified)

## DELTA
- src/spider/service/insights.py (CaseInsightsBuilder) → Aggregates run metrics, provider contributions, explainable empty reason, and type-specific intelligence cards.
- src/spider/web/api/cases.py (GET /api/cases/{case_id}/insights) → Exposes structured insights payload for UI and API consumers.
- src/spider/web/api/investigate.py (POST /api/investigate) → Returns persistent {case_id, run_id, status: "QUEUED"} in <50ms; background task drives async run.
- src/spider/web/api/settings.py (GET/POST /api/settings) → Manages language, theme, default profile, budget, provider toggles, and masked API keys.
- src/spider/web/api/providers.py (POST /api/providers/{provider_id}/test) → Live diagnostic check per provider on demand.
- src/spider/web/app.py (/api/classify) → Supports both GET and POST for TargetClassifier; returns type, detected_type, confidence, canonical_value.
- src/spider/providers/spiderfoot/adapter.py (accepts, parse) → Excluded EMAIL (native DNS/MX resolves it faster); fixed JSON stream/array dual parsing; mapped ASN for BGP_AS_OWNER.
- src/spider/providers/native/ct.py (execute, parse) → Removed wildcard prefix; added 3.5s timeout; capped observations to 50 items.
- src/spider/providers/metabigor/adapter.py (_build_command, parse) → Added -t 3 arg and stdin=DEVNULL; capped BGP/net observations to 50 items.
- src/spider/providers/uncover/adapter.py (execute) → Instant MISSING_CREDENTIAL return in 0.001s when no API keys exist.
- src/spider/scheduler/scheduler.py (schedule_candidate_tasks) → Deduplicated candidate tasks by provider_id per observable.
- src/spider/web/static/index.html → Vietnamese default, 6-tab case workflow, KPI cards, settings modal, and inspector drawer.
- src/spider/web/static/css/style.css → Light Professional theme default, .dark-theme toggle, type-specific cards, bounded graph container.
- src/spider/web/static/js/app.js → Client-side SPA engine with i18n, classification debounce, live progress, provider tests, provenance drawer, and Cytoscape graph.

## CONTRACTS_CHANGED
- POST /api/investigate: Returns {case_id, run_id, status: "QUEUED"} synchronously; run continues in background.
- GET /api/cases/{case_id}/insights: New endpoint returning structured summary, provider contributions, empty_reason, and type-specific pivots.
- GET/POST /api/classify: Accepts query param or JSON body; returns detected observable type and canonical value.
- GET/POST /api/settings: Reads and updates data/settings.json; masks secret values with "********".
- POST /api/providers/{provider_id}/test: Returns {provider_id, state, message} for on-demand live provider verification.

## LIVE_VERIFIED
- EMAIL: admin@example.com → PASS (11.2s; DNS/MX/IP/SPF/DMARC pivots resolved, 8 entities, 8 assertions, 0 dead-end).
- DOMAIN: example.com → PASS (19.3s; subdomains, DNS, CT logs capped, Metabigor BGP capped, 26 entities, 25 assertions).
- IP: 93.184.216.34 → PASS (14.1s; RDAP ASN/CIDR/Org + reverse PTR hostnames resolved).
- USERNAME: octocat → PASS (11.8s; Maigret bounded --top-sites 15 account enumeration).

## TESTS
- command: runtime\venv\Scripts\pytest.exe -v
- passed/failed: 62 passed, 0 failed in 98.76s
- notable coverage: Contract tests for all 8 adapters, live reality tests, engine budget/resilience, web security (CSP, XSS, traversal), and Phase 2 endpoints.

## UX_DELIVERED
- Default interface is Vietnamese with Professional Light Theme; one-click toggle for English and Dark Theme.
- 6-tab case workflow: Summary (Tổng quan) → Live Progress (Tiến trình) → Findings (Phát hiện) → Sources (Nguồn dữ liệu) → Evidence (Bằng chứng) → Graph (Mạng liên kết).
- Target input auto-classifies via TargetClassifier on debounced input.
- Type-specific intelligence cards expose domain/mail/DNS pivots for EMAIL, DOMAIN, IP, USERNAME, PHONE.
- Explainable empty state banner displays executed sources, sources with zero yield, and missing credentials when findings are empty.
- Knowledge graph (Cytoscape) relegated to Tab 6 with bounded canvas and neighborhood expansion.
- Evidence Inspector drawer traces entity provenance to upstream source, task ID, and raw payload via /api/explain.

## SECURITY
- Security headers middleware enforces strict CSP, nosniff, DENY frame options, and blocks untrusted script execution.
- API keys masked with "********" in GET /api/settings and stored locally in data/settings.json.
- All Go and Python CLI adapters execute via parameter lists without shell=True; Windows stdin handle isolated with DEVNULL.

## KNOWN_LIMITATIONS
- Public crt.sh API is prone to external upstream latency/rate-limiting (mitigated by 3.5s timeout isolation).
- Active scanning features require user confirmation of scope authorization.
- SQLite remains the single local database engine (concurrency guarded by serialized writes).

## RISKS_TO_RECHECK
- Verify crt.sh network reachability across different DNS resolvers.
- Verify WebSocket reconnect behavior if uvicorn server restarts during an active browser session.
- Verify Git remote permissions before pushing branch main to GitHub.

## NEXT_FOR_AGENT1
1. Push commit cdbf05a to origin/main (git push origin main).
2. Add end-to-end browser automation tests (Playwright) for the 6-tab UI workflow.
3. Add a Windows one-click desktop shortcut/batch script (run_spider.bat) for non-technical users.

## ENTRYPOINTS
START: runtime\venv\Scripts\python.exe -m uvicorn spider.web.app:create_app --factory --host 127.0.0.1 --port 8765
STOP: Ctrl+C or kill process on port 8765
WEB: http://127.0.0.1:8765
TEST: runtime\venv\Scripts\pytest.exe -v
KEY_FILES:
- src/spider/web/app.py
- src/spider/web/static/index.html
- src/spider/web/static/css/style.css
- src/spider/web/static/js/app.js
- src/spider/service/insights.py
- src/spider/web/api/settings.py
- src/spider/web/api/investigate.py

## DO_NOT_REDO
- Do not rewrite frontend into heavy JS frameworks; current vanilla JS + Cytoscape is lightweight, fast, and passes CSP.
- Do not re-add ObservableType.EMAIL to SpiderFootAdapter.accepts (hangs for 40s without findings).
- Do not uncap parsed observations in NativeCtAdapter or MetabigorAdapter (causes 15,000+ entries to overwhelm SQLite).
- Do not remove stdin=DEVNULL from Go CLI subprocesses on Windows (causes process blocking).