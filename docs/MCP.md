# Model Context Protocol (MCP) Integration

SPIDER is **MCP-ready but 100% MCP-independent**.

## Architecture
```
AI Agent / LLM Client (Analyst)
        │ (MCP Protocol)
        ▼
[SpiderMCPServer] (Optional Adapter)
        │ (Python API)
        ▼
[SpiderService] (Unified Service Boundary)
        │
[SPIDER Core Orchestration Engine]
```

## Semantic MCP Tools
- `collect`: Collects OSINT for a target.
- `get_entity`: Retrieves entity details.
- `explain_assertion`: Explains knowledge graph assertion evidence trail.
- `query_case`: Queries case intelligence summary.
- `rebuild_case`: Rebuilds case from observation log.
