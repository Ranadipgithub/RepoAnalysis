from src.codebase_kb.extract.models import CodeEdge
from typing import List
from src.codebase_kb.extract.models import CodeNode
import re

def sanitize_id(raw_id: str) -> str:
    """
    Mermaid crashes if node IDs contain colons, dots, spaces, or hyphens.
    This safely converts 'fn:my_file.py:login' into 'fn_my_file_py_login'.
    """
    # replace anything that is not a letter, number, or underscore with '_'
    return re.sub(r'[^a-zA-Z0-9_]', '_', raw_id)

def generate_flowchart(nodes: List[CodeNode], edges: List[CodeEdge]) -> str:
    """
    Generates a high-level architectural flowchart (flowchart TD) 
    Used for the main index.md overview.
    """
    lines = ["flowchart TD"]

    for node in nodes:
        safe_id = sanitize_id(node.id)
        label = str(node.name).replace('"', "'")
        lines.append(f'    {safe_id}["{label}"]')
    
    for edge in edges:
        safe_src = sanitize_id(edge.src)
        safe_dst = sanitize_id(edge.dst)
        
        if edge.kind == "call":
            lines.append(f'    {safe_src} -->|calls| {safe_dst}')
        elif edge.kind == "import":
            lines.append(f'    {safe_src} -.->|imports| {safe_dst}')
        elif edge.kind == "inherits":
            lines.append(f'    {safe_src} ==>|inherits| {safe_dst}')
        elif edge.kind == "contains":
            lines.append(f'    {safe_src} -->|contains| {safe_dst}')
        elif edge.kind == "decorates":
            lines.append(f'    {safe_src} -.->|decorates| {safe_dst}')
        else:
            lines.append(f'    {safe_src} --> {safe_dst}')
            
    return "\n".join(lines)

def generate_sequence_diagram(nodes: List[CodeNode], edges: List[CodeEdge]) -> str:
    """
    Generates a sequence diagram showing function call chains.
    Used inside individual chapter files to explain complex logic.
    """
    lines = ["sequenceDiagram"]
    
    # In sequence diagrams, we define participants first so they appear in order
    for node in nodes:
        safe_id = sanitize_id(node.id)
        label = str(node.name).replace('"', "'")
        lines.append(f'    participant {safe_id} as {label}')
        
    # Add the arrows for function calls
    for edge in edges:
        if edge.kind == "call":
            safe_src = sanitize_id(edge.src)
            safe_dst = sanitize_id(edge.dst)
            lines.append(f'    {safe_src}->>{safe_dst}: call')
            
    return "\n".join(lines)

class MermaidGenError(Exception):
    pass

def build_chapter_sequence(abstraction: dict, relationships: list[dict]) -> str:
    """
    Builds a sequence diagram for a specific abstraction chapter, showing
    how it interacts with other abstractions based on the relationships list.
    """
    if not abstraction or not isinstance(abstraction, dict):
        raise MermaidGenError("Invalid abstraction provided")
    
    name = abstraction.get("name")
    if not name:
        raise MermaidGenError("Abstraction missing name")
        
    # filter relationships that involve this abstraction
    relevant_rels = []
    for r in relationships:
        if r.get("from") == name or r.get("to") == name:
            if r.get("from") != r.get("to"): # skip self edges for the diagram
                relevant_rels.append(r)
                
    if not relevant_rels:
        return ""
        
    lines = ["sequenceDiagram"]
    
    # ensure this abstraction is first participant
    safe_name = sanitize_id(name)
    label_name = str(name).replace('"', "'")
    lines.append(f'    participant {safe_name} as {label_name}')
    
    participants = set([name])
    
    for r in relevant_rels:
        other = r.get("to") if r.get("from") == name else r.get("from")
        if other not in participants:
            safe_other = sanitize_id(other)
            label_other = str(other).replace('"', "'")
            lines.append(f'    participant {safe_other} as {label_other}')
            participants.add(other)
            
    for r in relevant_rels:
        f = r.get("from")
        t = r.get("to")
        lbl = r.get("label", "calls")
        if not f or not t:
            continue
        safe_f = sanitize_id(f)
        safe_t = sanitize_id(t)
        safe_lbl = str(lbl).replace('"', "'")
        
        lines.append(f'    {safe_f}->>{safe_t}: {safe_lbl}')
        
    return "\n".join(lines)