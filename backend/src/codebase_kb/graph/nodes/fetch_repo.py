import asyncio
from src.codebase_kb.crawler.github import get_output

async def fetch_repo_node(state: dict) -> dict:
    """Node 1: downloads the code from github"""
    return {"files":get_output(state["repo_url"],state["client_id"])}