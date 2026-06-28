from langgraph.graph import StateGraph, START, END
from langgraph.constants import Send
from codebase_kb.graph.state import KnowledgeBuilderState
from codebase_kb.graph.nodes.fetch_repo import fetch_repo_node
from codebase_kb.graph.nodes.build_code_graph_node import build_code_graph_node
from codebase_kb.graph.nodes.identify_abstractions_node import identify_abstractions_node
from codebase_kb.graph.nodes.analyze_relationships import analyze_relationships_node
from codebase_kb.graph.nodes.order_chapters import order_chapters_node
from codebase_kb.graph.nodes.write_chapters_single import write_chapter_single
from codebase_kb.graph.nodes.combine_tutorial import combine_tutorial_node

def continue_to_chapters(state: KnowledgeBuilderState):
    chapter_order = state.get("chapter_order", [])
    abstractions = state.get("abstractions", [])
    
    # We will send a payload to "write_chapter_single" for each chapter in the order
    sends = []
    
    # recreate a simple files mapping for the payload
    files = state.get("files", [])
    files_by_path = {f["path"]: f["content"] for f in files}
    
    for idx in chapter_order:
        if idx < len(abstractions):
            payload = {
                "abstraction_index": idx,
                "abstraction": abstractions[idx],
                "code_graph": state.get("code_graph"),
                "files_by_path": files_by_path,
                "relationships": state.get("relationships", []),
                "user_id": state.get("user_id"),
                "provider": state.get("provider"),
                "language": state.get("language", "english")
            }
            sends.append(Send("write_chapter_single", payload))
            
    if not sends:
        return END
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
    g.add_conditional_edges("order_chapters", continue_to_chapters, ["write_chapter_single", END])
    g.add_edge("write_chapter_single", "combine_tutorial")
    g.add_edge("combine_tutorial", END)

    return g.compile()