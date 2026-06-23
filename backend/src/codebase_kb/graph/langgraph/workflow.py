from langgraph.graph import StateGraph, START, END
from langgraph.constants import Send
from typing import List, TypedDict

from src.codebase_kb.graph.models import KnowledgeBuilderState
# Assuming you will create these node functions next in src/codebase_kb/graph/nodes/
from src.codebase_kb.graph.nodes import fetch_repo_node
from src.codebase_kb.graph.nodes import build_code_graph_node
from src.codebase_kb.graph.nodes import identify_abstractions_node
from src.codebase_kb.graph.nodes import analyze_relationships_node
from .nodes.order_chapters import order_chapters_node
from .nodes.write_chapters import write_chapter_single
from .nodes.combine_tutorial import combine_tutorial_node

class WriteChapterInput(TypedDict):
    """Payload sent to individual parallel chapter workers."""
    abstraction_index: int
    # We will pass the necessary sliced context/graph data here later

def route_to_chapter_writers(state: KnowledgeBuilderState) -> List[Send]:
    """
    Dynamic routing: Spawns a parallel write_chapter_single node 
    for every index in the chapter_order list.
    """
    sends = []
    for idx in state.get("chapter_order", []):
        sends.append(
            Send(
                "write_chapter_single", 
                WriteChapterInput(abstraction_index=idx)
            )
        )
    return sends

def build_graph():
    g = StateGraph(KnowledgeBuilderState)
    g.add_node("fetch_repo", fetch_repo_node)
    g.add_node("build_code_graph", build_code_graph_node)
    g.add_node("identify_abstractions", identify_abstractions_node)
    g.add_node("analyze_relationships", analyze_relationships_node)
    g.add_node("order_chapters", order_chapters_node)
    g.add_node("write_chapter_single", write_chapter_single)
    g.add_node("combine_tutorial", combine_tutorial_node)
    g.add_edge(START, "fetch_repo")
    g.add_edge("fetch_repo", "build_code_graph")
    g.add_edge("build_code_graph", "identify_abstractions")
    g.add_edge("identify_abstractions", "analyze_relationships")
    g.add_edge("analyze_relationships", "order_chapters")
    g.add_conditional_edges(
        "order_chapters",
        route_to_chapter_writers,
        ["write_chapter_single"],
    )
    g.add_edge("write_chapter_single", "combine_tutorial")
    g.add_edge("combine_tutorial", END)
    
    return g.compile()