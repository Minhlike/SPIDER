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

## Tools exposed over stdio (schema version 1)

| Tool | Effect |
| --- | --- |
| `input_catalogue` | Registered, metered input contracts; not proof of live availability |
| `case_digest` | Scoped evidence page, counts, unknowns, recent task history |
| `get_evidence` | Scoped provenance, versions and artifact hash; no raw page payload |
| `graph_neighbors` | Scoped edges, typed entities and potential transforms; no dispatch |
| `compare_runs` | Added identities and identities not observed in the later run |
| `run_coverage` | Outcomes and gaps for one target and run |
| `telemetry` | Measured latency and request sample counts; missing measurements stay unknown |
| `create_hypothesis` | Store a hypothesis with scoped supporting/contradicting/unknown evidence IDs |
| `list_hypotheses` | Bounded recent hypothesis list |

New tools return `schema_version: "1"`; errors have a stable code. The SDK
publishes typed argument schemas and read/write annotations. Hypotheses require
a UUID `action_id`: an identical retry returns the same receipt; a conflicting
retry is rejected. Evidence IDs must belong to the selected seed. Hypotheses
never modify observations or establish ownership. Tool/source text is untrusted
data, not instructions for an Agent.

The existing Python dispatcher retains `collect`, `query_case`,
`explain_assertion`, and `rebuild_case` for compatibility. These legacy tools
are not exposed by the new stdio entry point. In particular, network capability
dispatch/pivot and run cancellation remain pending their policy, lineage and
idempotency gates. A caller currently supplies case/target IDs from the UI/API.

## Scope and bounded output

`case_digest` accepts `case_id`, `target_id`, `question` (`all`,
`public_profiles`, `infrastructure`), `limit` (1–100, default 20), and `after`
(the final evidence ID of the previous page). Follow `next_cursor` while `more`
is true. A foreign seed's evidence/cursor is rejected. User seed observations
are lineage metadata and are excluded from findings/evidence. The HTTP read is
`GET /api/cases/{case_id}/digest` with the same query parameters.

This is pagination, not a snapshot or change feed: concurrent insertions and
review edits are not a supported delta protocol. History, graph edges, run
comparison and hypotheses explicitly flag truncation; they have no continuation
cursor yet. Graph transforms list contracts, not authorization to execute them.
Missing observations are never labelled disappeared. Reliability and useful
evidence/request remain uncalibrated; telemetry does not control scheduling.

Projection filters observations by seed in SQL, but still traverses that seed's
complete evidence and reads case entities. A small response is not proof of
bounded database cost. See `AGENT_INVESTIGATION_INCREMENT_1.md` for measurements.

## References

- [Official MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
- [Phone metadata library](https://github.com/daviddrysdale/python-phonenumbers)
- [Number portability limitations](https://github.com/google/libphonenumber/blob/master/FAQ.md)
