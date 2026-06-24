from pydantic import BaseModel, Field
from typing import List, Any
from codebase_kb.extract.graph import CodeGraph
from codebase_kb.observability.logging import get_logger
from codebase_kb.llm.router import get_provider_for_user
from codebase_kb.prompts.render import render_prompt
from langchain_core.messages import HumanMessage, SystemMessage
from codebase_kb.utils.json_parse import extract_json_array

log = get_logger(__name__)

class Abstraction(BaseModel):
    name: str = Field(..., description="The name of the abstraction.")
    description: str = Field(..., description="A description of the abstraction.")
    anchor_modules: List[str] = Field(default_factory=list)

TOP_K_MULTIPLIER = 2
MAX_FUNCTIONS_PER_MODULE = 5
MAX_CLASSES_PER_MODULE = 3

def _build_candidate_view(code_graph_payload: dict, max_abstractions: int) -> dict:
    """Reduce the full graph to a small, ranked, LLM-friendly view."""
    g = CodeGraph.from_payload(code_graph_payload)

    # 1) Top modules by PageRank
    module_nodes = [n for n, d in g.g.nodes(data=True) if d.get("kind") == "module"]
    module_pr = [(n, g.g.nodes[n].get("pagerank", 0.0)) for n in module_nodes]
    module_pr.sort(key=lambda x: -x[1])

    top_k = max_abstractions * TOP_K_MULTIPLIER
    top_modules = []
    for node_id, pr in module_pr[:top_k]:
        attrs = g.g.nodes[node_id]
        # top functions: highest in-degree within this module
        functions = sorted(
            [n for n in g.g.predecessors(node_id) if g.g.nodes[n].get("kind") == "function"],
            key=lambda n: -g.g.in_degree(n),
        )[:MAX_FUNCTIONS_PER_MODULE]
        classes = [
            n for n in g.g.nodes
            if g.g.nodes[n].get("kind") == "class"
            and g.g.nodes[n].get("file") == attrs.get("file")
        ][:MAX_CLASSES_PER_MODULE]
        top_modules.append({
            "path": attrs.get("file", node_id),
            "pagerank": pr,
            "in_degree_functions": [g.g.nodes[f].get("name", f) for f in functions],
            "classes": [g.g.nodes[c].get("name", c) for c in classes],
        })

    # 2) Communities with their top modules
    communities = g.communities()
    community_views = []
    for comm in communities:
        mods_in_comm = [n for n in comm if g.g.nodes[n].get("kind") == "module"]
        mods_sorted = sorted(mods_in_comm, key=lambda n: -g.g.nodes[n].get("pagerank", 0.0))[:5]
        community_views.append({
            "pagerank_sum": sum(g.g.nodes[n].get("pagerank", 0.0) for n in mods_in_comm),
            "top_modules": [
                {
                    "path": g.g.nodes[n].get("file", n),
                    "top_functions": sorted(
                        [p for p in g.g.predecessors(n) if g.g.nodes[p].get("kind") == "function"],
                        key=lambda p: -g.g.in_degree(p),
                    )[:3],
                    "top_classes": [
                        c for c in g.g.nodes
                        if g.g.nodes[c].get("kind") == "class"
                        and g.g.nodes[c].get("file") == g.g.nodes[n].get("file")
                    ][:2],
                }
                for n in mods_sorted
            ],
        })

    return {
        "top_k": top_k,
        "community_count": len(communities),
        "communities": community_views,
        "top_modules": top_modules,
    }

from langchain_core.runnables import RunnableConfig

async def identify_abstractions_node(state: dict, config: RunnableConfig) -> dict:
    log.info("identify_abstractions.start, run_id=%s", state.get("run_id"))
    user_id = state.get("user_id", "anonymous")
    provider_name = state.get("provider", "gemini")
    max_abstractions = state.get("max_abstractions", 15)
    language = state.get("language", "english")

    db_session = config.get("configurable", {}).get("db_session")
    if db_session is None:
        raise ValueError("db_session missing from config['configurable']")
    
    provider = await get_provider_for_user(user_id, provider_name, db_session);
    view = _build_candidate_view(state["code_graph"], max_abstractions)
    prompt = render_prompt(
        "identify",
        top_k=view["top_k"],
        community_count=view["community_count"],
        communities=view["communities"],
        top_modules=view["top_modules"],
        max_abstractions=max_abstractions,
        language=language,
    )

    response = await provider.ainvoke([HumanMessage(content=prompt)])
    raw = response.content if isinstance(response.content, str) else str(response.content)

    items = extract_json_array(raw)
    if items is None:
        log.error("identify_abstractions.parse_failed, raw=%s", raw[:500])
        raise ValueError("identify_abstractions: LLM did not return a JSON array")
    
    file_index_by_path = {f["path"]: i for i, f in enumerate(state.get("files", []))}
    abstractions: list[dict[str, Any]] = []
    for item in items:
        try:
            abs_ = Abstraction.model_validate(item)
        except Exception as e:
            log.warning("identify_abstractions.skip_invalid, item=%s, error=%s", item, str(e))
            continue
        # Validate anchor_modules against state["files"]
        known = [m for m in abs_.anchor_modules if m in file_index_by_path]
        if not known:
            log.warning("identify_abstractions.skip_unknown_anchors, name=%s, anchors=%s", abs_.name, abs_.anchor_modules)
            continue
        abstractions.append({
            "name": abs_.name,
            "description": abs_.description,
            "anchor_node_ids": [f"mod:{m}" for m in known],
            "file_indices": sorted({file_index_by_path[m] for m in known}),
        })

    # Enforce bounds
    abstractions = abstractions[:max_abstractions]
    if len(abstractions) < 5:
        log.warning("identify_abstractions.too_few, count=%s", len(abstractions))

    log.info("identify_abstractions.done, count=%s", len(abstractions))
    return {"abstractions": abstractions}