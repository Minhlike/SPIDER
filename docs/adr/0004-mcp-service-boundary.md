# ADR 0004: Decoupled SpiderService & Optional MCP Layer

## Context
SPIDER must be Model Context Protocol (MCP) ready but strictly zero-dependent on AI or MCP in its core execution path.

## Decision
1. Core business logic is encapsulated in SpiderService.
2. CLI and test suites call SpiderService directly.
3. MCP server is an optional adapter (src/spider/mcp/server.py) exposing typed semantic tools (collect, expand_entity, get_entity, get_evidence, explain_assertion, query_case) backed exclusively by SpiderService.
4. MCP package is optional extra (spider[mcp]). Core runs 100% without MCP installed.

## Consequences
- Clean architecture with zero AI runtime dependency.
- Seamless compatibility with AI agents as an external analyst tool.
