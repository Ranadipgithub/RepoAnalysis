import networkx as nx
from typing import Any
from langchain_core.runnables import RunnableConfig
from codebase_kb.observability.logging import get_logger

log = get_logger(__name__)

def _build_abstraction_graph(abstractions: list[dict[str, Any]], relationships: list[dict[str, Any]]) -> nx.DiGraph:
    # construct a directed graph using abstraction names
    g = nx.DiGraph()
    abs_names = {a["name"] for a in abstractions}
    for name in abs_names:
        g.add_node(name)
    
    for r in relationships:
        f, t = r.get("from"), r.get("to")
        if f not in abs_names or t not in abs_names:
            continue
        if f == t:
            # self-loop placeholder — we don't need it for ordering.
            continue
        if g.has_edge(f, t):
            continue
        g.add_edge(f, t, label=r.get("label", "uses"), kind=r.get("kind", "semantic"))
        
    return g

def _topo_with_cycle_break(abs_g: nx.DiGraph) -> list[str]:
    # topologically sort, breaking cycles with a deterministic tiebreaker
    if abs_g.number_of_nodes() == 0:
        return []

    work = abs_g.copy()
    # bounded loop — every iteration removes at least one edge, so this
    # terminates after at most E iterations.
    for _ in range(10_000):
        try:
            cycle = nx.find_cycle(work)
        except nx.NetworkXNoCycle:
            break

        edge = max(cycle, key=lambda e: (e[0], e[1]))
        work.remove_edge(*edge[:2])

    return list(reversed(list(nx.topological_sort(work))))

def _build_chapter_order(abstractions: list[dict[str, Any]], relationships: list[dict[str, Any]]) -> list[int]:
    # Topo-sort the macroscopic abstraction graph into a chapter order
    abs_g = _build_abstraction_graph(abstractions, relationships)
    sorted_names = _topo_with_cycle_break(abs_g)

    name_to_idx = {a["name"]: i for i, a in enumerate(abstractions)}

    # Names that participate in at least one edge — these are the "core
    # path" abstractions and get topo-sorted. Names absent from this set are
    # orphans and get pushed to the end.
    wired_names = {
        name
        for name, idx in name_to_idx.items()
        if abs_g.degree(name) > 0
    }

    order: list[int] = []
    seen: set[int] = set()

    for name in sorted_names:
        if name not in wired_names:
            continue
        idx = name_to_idx[name]
        if idx not in seen:
            order.append(idx)
            seen.add(idx)
    # Orphans appended at the end (preserves their input order for stability).
    for i, _ in enumerate(abstractions):
        if i not in seen:
            order.append(i)
    return order

async def order_chapters_node(state: dict, config: RunnableConfig) -> dict:
    log.info("order_chapters.start, run_id=%s", state.get("run_id"))
    abstractions = state.get("abstractions") or []
    relationships = state.get("relationships") or []
    if not abstractions:
        log.warning("order_chapters.empty_abstractions, run_id=%s", state.get("run_id"))
        return {"chapter_order": []}
    
    chapter_order = _build_chapter_order(abstractions, relationships)
    log.info("order_chapters.done, run_id=%s, length=%s", state.get("run_id"), len(chapter_order))
    return {"chapter_order": chapter_order}