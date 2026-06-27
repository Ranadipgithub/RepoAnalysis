import re
import asyncio

from codebase_kb.extract.graph import CodeGraph
from codebase_kb.utils.tokens import estimate_token, truncate_to_tokens
from codebase_kb.observability.logging import get_logger
from codebase_kb.llm.router import get_provider_for_user
from codebase_kb.prompts.render import render_prompt

from langchain_core.runnables import RunnableConfig
from langchain_core.messages import HumanMessage

log = get_logger(__name__)

TOKEN_BUDGET = 15000

# generate a slug for the chapter naming
def _slug(name: str) -> str:
    s = re.sub(r"[^A-Za-z0-9_]+", "_", name).strip("_").lower()
    return s or "chapter"

def _neighbors(abstraction_name: str, relationships: list[dict]) -> list[str]:
    out, seen = [], set()
    for r in relationships:
        if r.get("from") == r.get("to"):
            continue
        if r.get('from') == abstraction_name and r.get("to") not in seen:
            out.append(r["to"]); seen.add(r["to"])
        elif r.get("to") == abstraction_name and r.get("from") not in seen:
            out.append(r["from"]); seen.add(r["from"])
    
    return out

def _build_relevant_code_block(code_graph: CodeGraph, abstraction: dict, files_by_path: dict[str, str], token_budget: int) -> tuple[str, list[str]]:
    paths = code_graph.sliced_context(abstraction["anchor_node_ids"], radius=2, max_nodes=50)
    used = 0
    pieces, used_paths = [], []
    for p in paths:
        content = files_by_path.get(p, "")
        if not content: 
            continue
        cost = estimate_token(content)
        if used + cost <= token_budget:
            pieces.append(f"# {p}\n```\n{content}\n```")
            used_paths.append(p)
            used += cost
            continue
        remaining = token_budget - used
        if remaining < 200:
            break
        pieces.append(f"# {p} (truncated)\n```\n{truncate_to_tokens(content, remaining)}\n```")
        used_paths.append(p)
        used += remaining
        break
    return ("\n\n".join(pieces) if pieces else "(no relevant files found)"), used_paths

def _build_sequence_diagram(abstraction: dict, relationships: list[dict]) -> str:
    try:
        from codebase_kb.output.mermaid import build_chapter_sequence
        return build_chapter_sequence(abstraction, relationships)
    except Exception as e:
        log.warning("chapter_seq_diagram.skipped, abstraction=%s, error=%s", abstraction["name"], e)
        return ""
    
MAX_RETRIES = 2

async def _invoke_llm_with_retries(provider, prompt: str) -> str:
    last_err = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            r = await provider.ainvoke([HumanMessage(content=prompt)])
            content = r.content if isinstance(r.content, str) else str(r.content)
            if content and content.lstrip().startswith("#"):
                return content
            raise ValueError("LLM response missing top-level heading")
        except Exception as e:
            last_err = e
            log.warning("write_chapter.retry, attempt=%s, error=%s", attempt + 1, e)
            await asyncio.sleep(0.5 * (attempt + 1))
    raise last_err 

def _skeleton_markdown(abstraction: dict, err: Exception, paths: list[str]) -> str:
    return (
        f"# {abstraction['name']}\n\n"
        f"_{abstraction.get('description', '').strip()}_\n\n"
        f"## Motivation\n\n"
        f"This chapter covers **{abstraction['name']}**. Auto-generation failed ({type(err).__name__}: {err}).\n\n"
        f"## Relevant files\n\n" +
        "\n".join(f"- `{p}`" for p in paths) +
        "\n\n## Key Takeaways\n\n"
        f"- See anchor files above for the implementation of `{abstraction['name']}`.\n"
    )

async def write_chapter_single(payload: dict, config: RunnableConfig) -> dict:
    idx = payload["abstraction_index"]
    abstraction = payload["abstraction"]
    log.info("write_chapter.start, idx=%s, name=%s", idx, abstraction["name"])
    
    code_graph = CodeGraph.from_payload(payload["code_graph"])
    files_by_path = payload["files_by_path"]

    relevant_block, used_paths = _build_relevant_code_block(
        code_graph, abstraction, files_by_path, token_budget=TOKEN_BUDGET
    )
    neighbors = _neighbors(abstraction["name"], payload.get("relationships", []))
    db_session = config.get("configurable", {}).get("db_session")
    provider = await get_provider_for_user(
        user_id=payload.get("user_id", "anonymous"),
        requested_provider=payload.get("provider") or "gemini",
        db_session=db_session
    )
    prompt = render_prompt(
        "write_chapter",
        abstraction=abstraction,
        relevant_code=relevant_block,
        neighbors=neighbors,
        language=payload.get("language", "english"),
    )

    try:
        markdown = await _invoke_llm_with_retries(provider, prompt)
        seq = _build_sequence_diagram(abstraction, payload.get("relationships", []))
        if seq:
            markdown = re.sub(
                r"(## Key Code Excerpts.*?)(\n## |\Z)",
                lambda m: m.group(1) + "\n```mermaid\n" + seq + "\n```\n" + m.group(2),
                markdown, count=1, flags=re.DOTALL,
            )
        markdown = markdown.rstrip() + "\n\nNext: TBD\n"
    except Exception as e:
        log.error("write_chapter.skeleton, idx=%s, name=%s, error=%s", idx, abstraction["name"], e)
        markdown = _skeleton_markdown(abstraction, e, used_paths) + "\nNext: TBD\n"
    
    fname = f"{idx + 1:02d}_{_slug(abstraction['name'])}.md"
    
    log.info("write_chapter.done, idx=%s", idx)
    
    # FIX 3: Do not write to the file system here. Return the data to the State Reducer.
    return {"chapters": [{
        "index": idx,
        "name": abstraction["name"],
        "markdown": markdown,
        "filename": fname 
    }]}