import asyncio
import json
import logging
from typing import Dict, Any, List, Optional
from spider.service.service import SpiderService
from spider.models.enums import ObservableType
from spider.cli.main import infer_observable_type, get_service

logger = logging.getLogger(__name__)

class SpiderMCPServer:
    """
    Semantic Model Context Protocol (MCP) Server for SPIDER.
    Zero dependency in core: calls SpiderService.
    Exposes narrow, typed OSINT intelligence tools to external AI analysts.
    """
    def __init__(self, service: Optional[SpiderService] = None):
        self.service = service or get_service()

    async def handle_tool_call(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        await self.service.start()
        try:
            if tool_name == "collect":
                target = arguments["target"]
                case_id = arguments.get("case_id")
                authorized = arguments.get("authorized_scope", False)
                profile = arguments.get("policy_profile")
                
                if not case_id:
                    case_res = await self.service.create_case(name=f"MCP Investigation: {target}")
                    case_id = case_res["id"]
                
                obs_type = infer_observable_type(target)
                await self.service.add_target(case_id, target, obs_type, scope_authorized=authorized)
                run_res = await self.service.investigate(case_id, policy_profile=profile)
                entities = await self.service.get_case_entities(case_id)
                assertions = await self.service.get_case_assertions(case_id)
                
                return {
                    "case_id": case_id,
                    "target": target,
                    "status": run_res["status"],
                    "entities_count": len(entities),
                    "assertions_count": len(assertions),
                    "entities": entities,
                    "assertions": assertions
                }

            elif tool_name == "get_entity":
                entity_id = arguments["entity_id"]
                # Look up entity across cases or by id
                # Return entity details
                return {"entity_id": entity_id, "status": "RETRIEVED"}

            elif tool_name == "explain_assertion":
                assertion_id = arguments["assertion_id"]
                explanation = await self.service.explain_assertion(assertion_id)
                return explanation or {"error": f"Assertion {assertion_id} not found"}

            elif tool_name == "query_case":
                case_id = arguments["case_id"]
                entities = await self.service.get_case_entities(case_id)
                assertions = await self.service.get_case_assertions(case_id)
                summary = await self.service.get_graph_summary(case_id)
                return {
                    "case_id": case_id,
                    "summary": summary,
                    "entities": entities,
                    "assertions": assertions
                }

            elif tool_name == "rebuild_case":
                case_id = arguments["case_id"]
                return await self.service.rebuild_case(case_id)

            else:
                return {"error": f"Unknown tool: {tool_name}"}
        finally:
            await self.service.stop()

def create_mcp_server(service: Optional[SpiderService] = None) -> SpiderMCPServer:
    return SpiderMCPServer(service=service)
