import asyncio
from src.codebase_kb.crawler.github import get_output
from src.codebase_kb.graph.nodes.state import KnowledgeBuilderState
from typing import Dict,List,Any

async def fetch_repo_node(state: KnowledgeBuilderState) -> Dict[str,List[Any]]:
    """Node 1: downloads the code from github"""
    return {"files":get_output(state["repo_url"],state["client_id"])}