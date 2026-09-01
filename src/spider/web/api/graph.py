from fastapi import APIRouter, HTTPException, Query, Request, Depends
from typing import Dict, Any, List, Optional
from spider.service.service import SpiderService
from spider.core.factory import create_spider_service

router = APIRouter(prefix="/cases/{case_id}/graph", tags=["Knowledge Graph"])

def get_srv(request: Request) -> SpiderService:
    from spider.web.app import get_service
    return get_service(request)

@router.get("", response_model=Dict[str, Any])
async def get_case_graph(
    case_id: str,
    entity_type: Optional[str] = None,
    assertion_type: Optional[str] = None,
    min_confidence: float = 0.0,
    search: Optional[str] = None,
    max_nodes: int = 250,
    center_node_id: Optional[str] = None,
    service: SpiderService = Depends(get_srv)
):
    is_temp = False
    if not service.db_manager:
        await service.start()
        is_temp = True
    try:
        all_entities = await service.get_case_entities(case_id)
        all_assertions = await service.get_case_assertions(case_id)
        
        # 1. Filter Entities
        filtered_entities = all_entities
        if entity_type and isinstance(entity_type, str):
            filtered_entities = [e for e in filtered_entities if e["type"].upper() == entity_type.upper()]
        if search and isinstance(search, str):
            search_lower = search.lower()
            filtered_entities = [e for e in filtered_entities if search_lower in e["canonical_name"].lower()]

        entity_id_set = {e["id"] for e in filtered_entities}

        # 2. Filter Assertions
        filtered_assertions = []
        min_conf_val = float(min_confidence) if isinstance(min_confidence, (int, float)) else 0.0
        for a in all_assertions:
            if a["confidence"] < min_conf_val:
                continue
            if assertion_type and isinstance(assertion_type, str) and a["assertion_type"].upper() != assertion_type.upper():
                continue
            if a["source_entity_id"] in entity_id_set or a["target_entity_id"] in entity_id_set:
                filtered_assertions.append(a)

        # 3. Neighborhood Expansion if center_node_id requested
        if center_node_id and isinstance(center_node_id, str):
            neighbor_ids = {center_node_id}
            for a in all_assertions:
                if a["source_entity_id"] == center_node_id:
                    neighbor_ids.add(a["target_entity_id"])
                elif a["target_entity_id"] == center_node_id:
                    neighbor_ids.add(a["source_entity_id"])
            filtered_entities = [e for e in all_entities if e["id"] in neighbor_ids]
            entity_id_set = {e["id"] for e in filtered_entities}
            filtered_assertions = [a for a in all_assertions if a["source_entity_id"] in entity_id_set and a["target_entity_id"] in entity_id_set]

        # 4. Limit nodes to prevent browser freeze
        total_matching_nodes = len(filtered_entities)
        max_n = int(max_nodes) if isinstance(max_nodes, (int, float)) else 250
        truncated = False
        if len(filtered_entities) > max_n:
            filtered_entities = filtered_entities[:max_n]
            entity_id_set = {e["id"] for e in filtered_entities}
            filtered_assertions = [a for a in filtered_assertions if a["source_entity_id"] in entity_id_set and a["target_entity_id"] in entity_id_set]
            truncated = True

        # Cytoscape elements formatting
        elements = []
        for ent in filtered_entities:
            elements.append({
                "group": "nodes",
                "data": {
                    "id": ent["id"],
                    "label": ent["canonical_name"],
                    "type": ent["type"],
                    "observation_count": ent["observation_count"],
                    "first_seen": ent["first_seen"]
                }
            })

        for asrt in filtered_assertions:
            elements.append({
                "group": "edges",
                "data": {
                    "id": asrt["id"],
                    "source": asrt["source_entity_id"],
                    "target": asrt["target_entity_id"],
                    "label": asrt["assertion_type"],
                    "type": asrt["assertion_type"],
                    "confidence": asrt["confidence"],
                    "source_families": asrt.get("source_families", [])
                }
            })

        return {
            "case_id": case_id,
            "total_nodes": total_matching_nodes,
            "returned_nodes": len(filtered_entities),
            "total_edges": len(filtered_assertions),
            "truncated": truncated,
            "elements": elements
        }
    finally:
        if is_temp:
            await service.stop()
