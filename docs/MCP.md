# MCP investigation API

SPIDER core remains deterministic and independent of MCP or an AI runtime.
The optional transport uses the official Python SDK, pinned to `mcp==1.29.1`.
The service and ordinary CLI do not import the SDK.

## Start the stdio transport

Install the optional dependency with the project-local runtime if necessary:

```powershell
runtime\venv\Scripts\python.exe -m pip install -e ".[mcp]"
runtime\venv\Scripts\python.exe -m spider.mcp.stdio --root D:\PhanMem_Tools\SPIDER
```

An MCP client launches the second command as its subprocess and communicates
through stdin/stdout. This transport opens no HTTP listener. It uses the normal
local database by default; `--db` and `--artifacts` select isolated paths for
experiments. Do not configure multiple writers against the same database as a
performance strategy. Service lifetime belongs to the MCP session, and shutdown
drains accepted writes. Calls do not stop a service that was already running.

General investigations now default to two independent providers, with shared
provider/origin limits and pre-I/O request accounting. A capability action still
selects one provider and the action queue remains serial. Task metadata separates
provider wait, execution and commit wait; run-scoped anonymous HTTP replay records
cache hits without charging another network request. See increment 3 for the
controlled benchmark and limits; these measurements do not verify live sources.

## Tools exposed over stdio (schema version 2)

| Tool | Effect |
| --- | --- |
| `input_catalogue` | Registered, metered input contracts; not proof of live availability |
| `case_digest` | Scoped evidence page, counts, unknowns, recent task history |
| `case_delta` | Evidence recorded after a prior digest snapshot; never an absence claim |
| `get_evidence` | Scoped provenance, versions and artifact hash; no raw page payload |
| `graph_neighbors` | Scoped edges, typed entities and potential transforms; no dispatch |
| `compare_runs` | Added identities and identities not observed in the later run |
| `run_coverage` | Outcomes and gaps for one target and run |
| `telemetry` | Measured latency and request sample counts; missing measurements stay unknown |
| `create_hypothesis` | Store a hypothesis with scoped supporting/contradicting/unknown evidence IDs |
| `list_hypotheses` | Bounded recent hypothesis list |
| `list_cases` / `list_targets` | Bounded case/target ID navigation, with continuation |
| `run_capability` | Queue one evidence-linked transform with an idempotent receipt |
| `action_status` | Read scoped receipt, last persisted counts and attached run state |
| `cancel_run` | Cancel an attached capability action owned by this service session |
| `annotate_evidence` | Idempotent scoped evidence review; never overwrites source evidence |

New tools return `schema_version: "2"`; errors have a stable code. The SDK
publishes typed argument schemas and read/write annotations. Hypotheses require
a UUID `action_id`: an identical retry returns the same receipt; a conflicting
retry is rejected. Evidence IDs must belong to the selected seed. Hypotheses
never modify observations or establish ownership. Tool/source text is untrusted
data, not instructions for an Agent.

The existing Python dispatcher retains `collect`, `query_case`,
`explain_assertion`, and `rebuild_case` for compatibility. These legacy tools
are not exposed by the new stdio entry point. Case creation and initial collection
remain available through the UI/CLI. Agent navigation uses `list_cases` →
`list_targets` → `case_digest` / `get_evidence` (including `entity_id`) →
`graph_neighbors` → an explicitly chosen `run_capability`.

## Evidence-linked actions

`run_capability` requires UUID `action_id`, case/target/entity IDs, capability and
provider IDs. A derived entity requires an `observation_id` in that target's
reachable evidence with the exact type, namespace and canonical value. The
original seed may omit this proof; user input is never presented as evidence.
No observable, arbitrary command or lineage can be supplied by the caller.

Question (`all`, `public_profiles`, `infrastructure`), registered capability,
adapter acceptance, request metering and stored target authorization are checked
before admission and again before execution. An authorized seed does not authorize
direct access to a linked entity. `browser_assisted=true` expresses browser intent
for the existing browser capability; it does not enable the planned M4 workflow.

Defaults: 20 request attempts, 20 entity admissions including the input, 60 seconds.
Limits: requests/entities 1–100, timeout 1–120 seconds plus adapter cleanup grace.
One provider call, no recursive expansion. Username actions use `VN_COMMON_CORE`.
The action queue admits at most 16 pending/running capability actions per service;
these execute serially and admission also counts existing background jobs. This is not the M3 global,
provider or origin concurrency controller, nor a cross-process shared budget.

Reuse the same UUID and identical arguments when retrying. Receipt and QUEUED run
are committed together before task creation. A conflict fails without dispatch.
An interruption between commit and task attachment can leave a detached receipt:
it reports `UNKNOWN_AFTER_RESTART`, never automatic replay. Status request counts
are **last persisted receipts**, not instantaneous totals; missing counts are null.

`cancel_run` takes a separate UUID and the run ID. It targets only an attached
capability action with the matching case/target. Completed runs are unchanged;
detached work reports uncertainty and cannot be killed from this session. A clean
session shutdown cancels its owned tasks and drains writes. Already committed
evidence and graph changes share an ingest transaction and survive cancellation.
This does not promise preservation of a provider's unsaved in-memory results.

`annotate_evidence` takes a UUID, case/target/question, claim and observation IDs,
role, dependency and optional origin ID. Dependency assertions require an origin
in scope. Retrying an earlier annotation returns its receipt without undoing a
later review. The statement remains an operator/Agent assessment, not verified
ownership or verified source independence. Seed input cannot be reviewed as source
evidence. New action receipts share an ID space for dispatch, cancellation and
annotation; hypotheses retain their existing separate idempotency store.

New mutations use the service facade and are available to UI/CLI integrations;
graph action controls and an HTTP dispatch endpoint are not added in this increment.
Direct Python dispatch of network actions requires an already-running service;
the official stdio session owns this lifecycle automatically.

## Scope and bounded output

`case_digest` accepts `case_id`, `target_id`, `question` (`all`,
`public_profiles`, `infrastructure`), `limit` (1–100, default 20), and an
optional `snapshot`. Its returned opaque `snapshot`, `next_cursor` and
`history_next_cursor` must be passed back unchanged for continuation. Cursors
are integrity protected and reject another case, target, question or read
surface. They contain no raw evidence or source content and expire on a service
restart; request a fresh digest when that happens. `graph_neighbors` has the
same snapshot/continuation contract for edges.

`case_delta` takes a previous `case_digest` snapshot and returns only evidence
recorded after that baseline. It has its own frozen page cursor. Empty delta and
absence from a run never establish disappearance. User seed observations are
lineage metadata and are excluded from findings/evidence. Graph transforms list
contracts, not authorization to execute them. Reliability and useful
evidence/request remain uncalibrated; telemetry does not control scheduling.

Projection follows only children of typed identities reachable from the selected
seed and fetches matching entities, rather than loading unrelated case branches.
A very large reachable branch can still require complete traversal, so a small
response is not proof of hard bounded database cost. Snapshotting removes repeated
old pages for an Agent; fully bounded reachability remains tracked as P0 follow-up.
See `AGENT_INVESTIGATION_INCREMENT_1.md` for measurements.

## References

- [Official MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
- [Phone metadata library](https://github.com/daviddrysdale/python-phonenumbers)
- [Number portability limitations](https://github.com/google/libphonenumber/blob/master/FAQ.md)
