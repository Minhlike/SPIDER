from typing import Dict, Any, List, Optional
import networkx as nx
from sqlalchemy.ext.asyncio import AsyncSession
from spider.storage.repositories.graph_repo import GraphRepository

class AnalyticalGraphProjector:
    """
    Builds on-demand NetworkX projections from SQLite knowledge graph
    for graph algorithms (connected components, shortest paths, centrality, export).
    """
    @staticmethod
    async def build_networkx_graph(session: AsyncSession, case_id: str) -> nx.MultiDiGraph:
        g = nx.MultiDiGraph()
        entities = await GraphRepository.get_entities_for_case(session, case_id)
        assertions = await GraphRepository.get_assertions_for_case(session, case_id)

        for ent in entities:
            g.add_node(
                ent.id,
                canonical_name=ent.canonical_name,
                type=ent.observable_type,
                first_seen=ent.first_seen.isoformat(),
                observation_count=ent.observation_count
            )

        for asrt in assertions:
            g.add_edge(
                asrt.source_entity_id,
                asrt.target_entity_id,
                key=asrt.id,
                assertion_type=asrt.assertion_type,
                confidence=asrt.confidence,
                independent_source_count=asrt.independent_source_count,
                source_families=asrt.source_families
            )

        return g

    @staticmethod
    def compute_summary_metrics(g: nx.MultiDiGraph) -> Dict[str, Any]:
        return {
            "nodes_count": g.number_of_nodes(),
            "edges_count": g.number_of_edges(),
            "weakly_connected_components": nx.number_weakly_connected_components(g),
            "is_directed_acyclic": nx.is_directed_acyclic_graph(g)
        }
