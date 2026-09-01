import pytest
from spider.web.api.graph import get_case_graph

@pytest.mark.asyncio
async def test_graph_truncation_limits():
    # Test that requesting a graph with max_nodes truncates cleanly
    # and sets the 'truncated' flag to protect browser memory
    from unittest.mock import AsyncMock, patch
    from spider.cli.main import get_service

    service = get_service()
    # Mock get_case_entities returning 1000 synthetic entities
    mock_entities = [{"id": f"ent-{i}", "type": "HOSTNAME", "canonical_name": f"host{i}.com", "observation_count": 1, "first_seen": "2026-09-01T12:00:00"} for i in range(1000)]
    mock_assertions = [{"id": f"asrt-{i}", "source_entity_id": f"ent-{i}", "target_entity_id": f"ent-{i+1}", "assertion_type": "SUBDOMAIN_OF", "confidence": 0.9, "source_families": ["DNS"]} for i in range(999)]

    with patch.object(service, "get_case_entities", new=AsyncMock(return_value=mock_entities)),          patch.object(service, "get_case_assertions", new=AsyncMock(return_value=mock_assertions)),          patch("spider.web.api.graph.get_service", return_value=service):

        res = await get_case_graph(case_id="case-bench", max_nodes=100)
        assert res["total_nodes"] == 1000
        assert res["returned_nodes"] == 100
        assert res["truncated"] is True
        assert len(res["elements"]) > 0
