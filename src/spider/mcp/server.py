from spider.models.budget import ExecutionBudget
import asyncio
import json
import logging
from typing import Dict, Any, Optional
from spider.service.service import SpiderService
from spider.core.factory import create_spider_service
from spider.models.classifier import TargetClassifier, ClassificationError

logger = logging.getLogger(__name__)

class SpiderMCPServer:
    """
    Model Context Protocol (MCP) Adapter for SPIDER.
    Exposes semantic OSINT tools to AI agents while maintaining zero MCP dependency in core.
    """
    def __init__(self, service: Optional[SpiderService] = None):
        self.service = service or create_spider_service(mode="production")
        self._call_lock = asyncio.Lock()

    async def handle_tool_call(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        # Serialize dispatcher-owned lifecycle until an explicit MCP session owns it.
        async with self._call_lock:
            result = await self._handle_tool_call(tool_name, arguments)
            if tool_name not in {"collect", "query_case", "explain_assertion", "rebuild_case"}:
                result.setdefault("schema_version", "1")
            return result

    async def _handle_tool_call(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        if tool_name not in {"collect", "explain_assertion", "query_case", "rebuild_case",
                             "case_digest", "case_delta", "get_evidence", "input_catalogue", "graph_neighbors",
                             "compare_runs", "run_coverage", "browser_trace", "phone_candidate_digest", "telemetry", "create_hypothesis", "list_hypotheses",
                             "run_capability", "action_status", "cancel_run", "annotate_evidence",
                             "resume_run",
                             "list_cases", "list_targets"}:
            return {"error": "Unknown tool"}
        if tool_name in {"run_capability", "cancel_run", "resume_run"} and not self.service.is_running:
            return {"error": {"code": "SESSION_REQUIRED"}}
        if tool_name == "collect":
            try:
                classification = TargetClassifier.resolve(arguments.get("target", ""), arguments.get("target_type"))
            except ClassificationError as exc:
                return {"error": exc.detail()}
        owned_lifecycle = not self.service.is_running
        await self.service.start()
        try:
            if tool_name == "resume_run":
                from spider.service.resume import prepare_resume, ResumeError
                if set(arguments) != {"case_id", "target_id", "run_id"}:
                    return {"error": {"code": "INVALID_SCOPE_OR_ARGUMENT"}}
                try:
                    spec = await prepare_resume(self.service, arguments["run_id"],
                        case_id=arguments["case_id"], target_id=arguments["target_id"])
                except ResumeError as exc:
                    return {"error": {"code": str(exc)}}

                async def execute_resume():
                    try:
                        await self.service.investigate(spec.case_id, budget=spec.budget,
                            policy_profile=spec.policy_profile, run_id=spec.run_id,
                            investigation_mode=spec.investigation_mode,
                            browser_assisted=spec.browser_assisted,
                            resume_from_run_id=spec.source_run_id)
                    except asyncio.CancelledError:
                        return
                    except Exception:
                        from spider.models.base import utc_now
                        from spider.storage.schema import ProviderRunRecord
                        async def fail(session):
                            row = await session.get(ProviderRunRecord, spec.run_id)
                            if row and row.status in {"QUEUED", "RUNNING"}:
                                row.status, row.completed_at = "FAILED", utc_now()
                        await self.service.db_writer.submit(fail)
                task = asyncio.create_task(execute_resume(), name=f"spider-run:{spec.run_id}")
                self.service.background_tasks.add(task)
                task.add_done_callback(self.service.background_tasks.discard)
                return {"case_id": spec.case_id, "target_id": arguments["target_id"],
                        "run_id": spec.run_id, "resumed_from_run_id": spec.source_run_id,
                        "status": "QUEUED", "automatic_replay": False}
            if tool_name in {"run_capability", "action_status", "cancel_run", "annotate_evidence"}:
                from spider.service.actions import RunCapabilityInput, CancelRunInput, EvidenceAnnotationInput, ActionError
                try:
                    if tool_name == "action_status":
                        if set(arguments) != {"case_id", "target_id", "action_id"}:
                            raise ValueError("Invalid arguments")
                        return await self.service.actions.status(arguments["case_id"],
                            arguments["target_id"], arguments["action_id"])
                    model = {"run_capability": RunCapabilityInput, "cancel_run": CancelRunInput,
                             "annotate_evidence": EvidenceAnnotationInput}[tool_name]
                    request = model.model_validate({k: v for k, v in arguments.items() if k != "case_id"})
                    return await getattr(self.service.actions, tool_name)(arguments["case_id"], request)
                except ActionError as exc:
                    return {"error": {"code": str(exc)}}
                except (ValueError, KeyError, TypeError):
                    return {"error": {"code": "INVALID_SCOPE_OR_ARGUMENT"}}
                except Exception:
                    return {"error": {"code": "ACTION_STORAGE_OR_EXECUTION_ERROR"}}
            if tool_name in {"create_hypothesis", "list_hypotheses"}:
                from spider.service.hypothesis import HypothesisInput, create_hypothesis, list_hypotheses
                try:
                    if tool_name == "create_hypothesis":
                        request = HypothesisInput.model_validate({k: v for k, v in arguments.items() if k != "case_id"})
                        return await self.service.db_writer.submit(lambda session:
                            create_hypothesis(session, arguments["case_id"], request))
                    limit = arguments.get("limit", 20)
                    if type(limit) is not int or not 1 <= limit <= 100:
                        raise ValueError("Invalid limit")
                    async with self.service.db_manager.session_factory() as session:
                        return await list_hypotheses(session, arguments["case_id"], arguments["target_id"], limit)
                except (ValueError, KeyError):
                    return {"error": {"code": "INVALID_HYPOTHESIS_OR_SCOPE"}}
            if tool_name in {"input_catalogue", "graph_neighbors", "compare_runs", "run_coverage", "browser_trace", "phone_candidate_digest", "telemetry",
                             "list_cases", "list_targets"}:
                from spider.service import investigation_api as api
                try:
                    if tool_name == "input_catalogue":
                        return {"inputs": api.input_catalogue(self.service)}
                    async with self.service.db_manager.session_factory() as session:
                        if tool_name in {"list_cases", "list_targets"}:
                            return await api.list_context(session,
                                arguments["case_id"] if tool_name == "list_targets" else None,
                                arguments.get("limit", 20), arguments.get("after"))
                        scope = (session, arguments["case_id"], arguments["target_id"])
                        if tool_name == "graph_neighbors":
                            return await api.graph_neighbors(session, self.service, arguments["case_id"],
                                arguments["target_id"], arguments["entity_id"], arguments.get("limit", 20),
                                arguments.get("after"), arguments.get("snapshot"))
                        if tool_name == "compare_runs":
                            return await api.compare_runs(*scope, arguments["before_id"],
                                arguments["after_id"], arguments.get("limit", 20), arguments.get("after"),
                                arguments.get("snapshot"))
                        if tool_name == "run_coverage":
                            return await api.run_coverage(*scope, arguments["run_id"])
                        if tool_name == "browser_trace":
                            return await api.browser_trace(*scope, arguments["run_id"])
                        if tool_name == "phone_candidate_digest":
                            return await api.phone_candidate_digest(*scope)
                        return await api.telemetry(*scope)
                except (ValueError, KeyError, TypeError):
                    return {"error": {"code": "INVALID_SCOPE_OR_ARGUMENT"}}
            if tool_name in {"case_digest", "case_delta", "get_evidence"}:
                from spider.service.digest import case_delta, case_digest, get_evidence
                try:
                    async with self.service.db_manager.session_factory() as session:
                        if tool_name == "case_digest":
                            return await case_digest(session, arguments["case_id"],
                                arguments.get("target_id"), arguments.get("question", "all"),
                                arguments.get("limit", 20), arguments.get("after"),
                                arguments.get("snapshot"), arguments.get("history_after"))
                        if tool_name == "case_delta":
                            return await case_delta(session, arguments["case_id"], arguments.get("target_id"),
                                arguments["since_snapshot"], arguments.get("question", "all"),
                                arguments.get("limit", 20), arguments.get("after"), arguments.get("snapshot"))
                        return await get_evidence(session, arguments["case_id"],
                            arguments.get("target_id"), arguments["observation_id"])
                except (ValueError, KeyError):
                    return {"error": {"code": "INVALID_SCOPE_OR_ARGUMENT",
                                      "message": "Check case, target, evidence, cursor and page limit"}}
            if tool_name == "collect":
                target = arguments["target"]
                case_id = arguments.get("case_id")
                authorized = arguments.get("authorized_scope", False)
                profile = arguments.get("policy_profile")
                
                if not case_id:
                    case_res = await self.service.create_case(name=f"MCP Investigation: {target}")
                    case_id = case_res["id"]
                
                obs_type = classification.detected_type
                await self.service.add_target(case_id, target, obs_type, scope_authorized=authorized,
                    canonical_value=classification.canonical_value,
                    metadata={"classification": classification.model_dump(mode="json")})
                budget = ExecutionBudget(max_depth=arguments.get("max_depth", 1), max_entities=arguments.get("max_entities", 20))
                run_res = await self.service.investigate(case_id, budget=budget, policy_profile=profile)
                entities = await self.service.get_case_entities(case_id)
                assertions = await self.service.get_case_assertions(case_id)
                
                return {
                    "case_id": case_id,
                    "target": target,
                    "detected_type": obs_type.value,
                    "status": run_res["status"],
                    "entities_count": len(entities),
                    "assertions_count": len(assertions),
                    "entities": entities,
                    "assertions": assertions
                }

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
            if owned_lifecycle:
                await self.service.stop()

def create_mcp_server(service: Optional[SpiderService] = None) -> SpiderMCPServer:
    return SpiderMCPServer(service=service)
