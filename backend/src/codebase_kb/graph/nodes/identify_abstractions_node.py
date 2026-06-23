import json
import re
from typing import Dict, List, Any
from src.codebase_kb.llm.router import get_provider_for_user
from src.codebase_kb.graph.models.state import KnowledgeBuilderState
from src.codebase_kb.prompts.render import render_prompt
import json
import re
from typing import Any, Dict, List


def identify_abstractions_node(state: KnowledgeBuilderState) -> Dict[str, Any]:
    llm = get_provider_for_user(state["user_id"], requested_provider=state["provider"])
    code_graph = state["code_graph"]

    top_k_nodes = code_graph.core_abstractions(k=50) 
    communities_sets = code_graph.communities()
    formatted_communities = []
    for comm in communities_sets:
        modules_map = {}
        for node in comm:
            if node.file not in modules_map:
                modules_map[node.file] = {"functions": [], "classes": []}
            if node.kind in ["function", "method"]:
                modules_map[node.file]["functions"].append(node.name)
            elif node.kind == "class":
                modules_map[node.file]["classes"].append(node.name)
        
        top_mods = [
            {
                "path": file_path,
                "top_functions": data["functions"][:5],
                "top_classes": data["classes"][:5]
            }
            for file_path, data in modules_map.items()
        ]
        formatted_communities.append({
            "pagerank_sum": len(comm), 
            "top_modules": top_mods
        })
    formatted_top_modules = []
    top_modules_map = {}
    for node in top_k_nodes:
        if node.file not in top_modules_map:
            top_modules_map[node.file] = {"functions": [], "classes": []}
        if node.kind in ["function", "method"]:
            top_modules_map[node.file]["functions"].append(node.name)
        elif node.kind == "class":
            top_modules_map[node.file]["classes"].append(node.name)

    for file_path, data in list(top_modules_map.items())[:15]: 
        formatted_top_modules.append({
            "path": file_path,
            "pagerank": 1.0,
            "in_degree_functions": data["functions"][:5],
            "classes": data["classes"][:5]
        })

    prompt = render_prompt(
        "identify.md",
        top_k=len(formatted_top_modules),
        community_count=len(formatted_communities),
        communities=formatted_communities,
        top_modules=formatted_top_modules,
        max_abstractions=state.get("max_abstractions", 10),
        language=state.get("language", "English")
    )
    response_text = llm.invoke(prompt)
    if hasattr(response_text, "content"):
        response_text = response_text.content
    abstractions = _extract_json_from_markdown(response_text)
    return {"abstractions": abstractions}


def _extract_json_from_markdown(text: str) -> List[Dict[str, Any]]:
    """Safely extract a JSON array from a markdown code block."""
    # Look for ```json ... ``` first
    match = re.search(
        r"```json\s*(.*?)\s*```",
        text,
        flags=re.DOTALL | re.IGNORECASE,
    )
    if match:
        json_text = match.group(1)
    else:
        array_match = re.search(r"(\[\s*.*\s*\])", text, flags=re.DOTALL)
        if not array_match:
            raise ValueError("No JSON block found in LLM output")
        json_text = array_match.group(1)
    try:
        data = json.loads(json_text)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON returned by LLM: {e}") from e
    if not isinstance(data, list):
        raise ValueError("Expected top-level JSON array")
    if not all(isinstance(item, dict) for item in data):
        raise ValueError("Expected array of objects")

    return data