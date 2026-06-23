import networkx as nx
from dataclasses import asdict
from typing import List, Tuple, Set
from .models import CodeNode, CodeEdge

class CodeGraph:
    def __init__(self):
        # We use a DiGraph (Directed Graph) because imports and function calls go in a specific direction
        self.g = nx.DiGraph()
        self.metrics = {}
    
    @classmethod
    def from_payload(cls, payload: dict) -> "CodeGraph":
        """
        Rehydrates a CodeGraph object from the LangGraph state dictionary.
        """
        instance = cls()
        
        # 1. Rebuild the NetworkX Graph from the nodes and edges
        for node in payload.get("nodes", []):
            instance.g.add_node(node["id"], **node)
            
        for edge in payload.get("edges", []):
            instance.g.add_edge(edge["src"], edge["dst"], **edge)
            
        # 2. Restore the pre-calculated metrics (PageRank, Communities)
        instance.metrics = payload.get("metrics", {})
        
        return instance
    
    def add_nodes(self, nodes: List[CodeNode]) -> None:
        for n in nodes:
            # We store all the dataclass properties inside the graph node itself
            self.g.add_node(n.id, **asdict(n))

    def add_edges(self, edges: List[CodeEdge]) -> None:
        for e in edges:
            self.g.add_edge(e.src, e.dst, kind=e.kind, label=e.label)

    def core_abstractions(self, k: int = 15) -> List[CodeNode]:
        """Finds the Top-K architecturally important INTERNAL nodes."""
        if self.g.number_of_nodes() == 0:
            return []
        pr = nx.pagerank(self.g)
        internal_nodes = {
            node_id: score 
            for node_id, score in pr.items() 
            if "kind" in self.g.nodes[node_id]
        }
        top_k_items = sorted(internal_nodes.items(), key=lambda x: -x[1])[:k]
        top_k_nodes = []
        for node_id, score in top_k_items:

            node_data = self.g.nodes[node_id]
            top_k_nodes.append(CodeNode(**node_data))
            
        return top_k_nodes
    def communities(self) -> List[Set['CodeNode']]:
        """Groups tightly coupled internal files into natural chapter groupings."""
        internal_nodes = [n for n, attr in self.g.nodes(data=True) if "kind" in attr]
        internal_subgraph = self.g.subgraph(internal_nodes).to_undirected()
        if internal_subgraph.number_of_nodes() == 0:
            return []
            
        comms = nx.community.louvain_communities(internal_subgraph, seed=42)
        node_communities = []
        for community in comms:
            node_set = set()
            for node_id in community:
                node_data = self.g.nodes[node_id]
                node_set.add(CodeNode(**node_data))
            node_communities.append(node_set)
        return node_communities

    def chapter_order_indices(self, abstraction_ids: List[str]) -> List[int]:
        """Creates a linear teaching order (Prerequisites first)."""
        sub = self.g.subgraph(abstraction_ids).copy()
        pr = nx.pagerank(sub)
        
        # We might have circular imports or mutual recursive calls (A calls B, B calls A)
        # We must break these cycles before we can establish a linear tutorial order.
        for _ in range(1000):
            try:
                cyc = nx.find_cycle(sub)
            except nx.NetworkXNoCycle:
                break
            
            # Remove the edge connecting the least important nodes in the cycle
            edge = min(cyc, key=lambda e: pr.get(e[0], 0) + pr.get(e[1], 0))
            sub.remove_edge(*edge[:2])
            
        sorted_nodes = list(nx.topological_sort(sub))[::-1]
        return [abstraction_ids.index(n) for n in sorted_nodes]

    def sliced_context(self, anchor_ids: List[str], radius: int = 2, max_nodes: int = 50) -> List[str]:
        """Finds the exact files needed for a specific chapter."""
        nodes = set()
        for a in anchor_ids:
            # ego_graph gets the anchor node and everything within 'radius' arrows of it
            nodes.update(nx.ego_graph(self.g, a, radius=radius).nodes)
            
        sub = self.g.subgraph(nodes)
        pr = nx.pagerank(sub)
        
        # Keep only the top `max_nodes` most important files in this slice to stay under token budget
        keep = set(n for n, _ in sorted(pr.items(), key=lambda x: -x[1])[:max_nodes])
        
        # Return unique file paths for these nodes
        return sorted({self.g.nodes[n]["file"] for n in keep if "file" in self.g.nodes[n]})
