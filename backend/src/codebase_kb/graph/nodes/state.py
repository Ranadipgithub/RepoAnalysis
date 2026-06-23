import operator
from typing import TypedDict, Optional, List, Dict, Any, Annotated

class KnowledgeBuilderState(TypedDict, total=False):
    # --- inputs (set once when run starts) ---
    repo_url: str
    client_id:str
    # local_dir: Optional[str]
    # project_name: str
    # github_token: Optional[str]              
    # output_dir: str
    # include_patterns: List[str]
    # exclude_patterns: List[str]
    # max_file_size: int
    # language: str
    # max_abstractions: int
    # use_cache: bool
    # provider: str
    # model: str

    # --- intermediate ---
    files: List[Dict[str, str]]              
    code_graph: Dict[str, Any]               
    abstractions: List[Dict[str, Any]]       
    relationships: List[Dict[str, Any]]      
    chapter_order: List[int]

    # --- outputs ---
    # The reducer 'operator.add' merges outputs from parallel write_chapter_single nodes
    chapters: Annotated[List[Dict[str, Any]], operator.add] 
    final_output_dir: str
    token_usage: Dict[str, int]