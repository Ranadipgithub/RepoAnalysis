import ast
from .models import CodeNode, CodeEdge
from typing import List, Tuple

def _dotted(node: ast.expr) -> str:
    """Helper to convert an AST Name/Attribute node into a dotted string (e.g., 'json.dumps')."""
    if isinstance(node, ast.Name):
        return node.id
    elif isinstance(node, ast.Attribute):
        return f"{_dotted(node.value)}.{node.attr}"
    return "unknown"

def _walk_calls(node: ast.AST, src_id: str, edges: List[CodeEdge]):
    """Recursively find all function calls within a function body and create 'call' edges."""
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            try:
                called_name = _dotted(child.func)
                # We prefix with 'call:' to indicate it's an unresolved reference. 
                # Later, the graph can try to link this to actual defined functions.
                edges.append(CodeEdge(src=src_id, dst=f"call:{called_name}", kind="call"))
            except Exception:
                pass

def parse_python_file(path: str, source: str) -> Tuple[List[CodeNode], List[CodeEdge]]:
    """Parse a python file into structural nodes and edges."""
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError:
        # if the file has invalid syntax, skip it.
        return [], []
    nodes: List[CodeNode] = []
    edges: List[CodeEdge] = []
    # Create the Module Node (represents the whole file)
    mod_id = f"mod:{path}"
    nodes.append(CodeNode(
        id=mod_id, kind="module", name=path, file=path, 
        lineno=1, end_lineno=getattr(tree, 'end_lineno', 1),
        signature="", docstring=ast.get_docstring(tree) or ""
    ))
    # Walk the top-level statements in the file
    for stmt in tree.body:
        
        # Identify Imports
        if isinstance(stmt, (ast.Import, ast.ImportFrom)):
            for alias in stmt.names:
                edges.append(CodeEdge(
                    src=mod_id, 
                    dst=f"mod:{alias.name}", 
                    kind="import", 
                    label=alias.asname or alias.name
                ))
                
        # Identify Top-Level Functions
        elif isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            fn_id = f"fn:{path}:{stmt.name}"
            nodes.append(CodeNode(
                id=fn_id, kind="function", name=stmt.name, file=path,
                lineno=stmt.lineno, end_lineno=getattr(stmt, 'end_lineno', stmt.lineno),
                signature=ast.unparse(stmt.args),
                docstring=ast.get_docstring(stmt) or ""
            ))
            # The module "contains" this function
            edges.append(CodeEdge(src=mod_id, dst=fn_id, kind="contains"))
            
            # Find what this function calls
            _walk_calls(stmt, fn_id, edges)
            
            # Find what decorators this function uses
            for d in getattr(stmt, 'decorator_list', []):
                edges.append(CodeEdge(src=fn_id, dst=_dotted(d), kind="decorates"))
                
        # Identify Classes
        elif isinstance(stmt, ast.ClassDef):
            cls_id = f"cls:{path}:{stmt.name}"
            nodes.append(CodeNode(
                id=cls_id, kind="class", name=stmt.name, file=path,
                lineno=stmt.lineno, end_lineno=getattr(stmt, 'end_lineno', stmt.lineno),
                signature=", ".join(ast.unparse(b) for b in stmt.bases),
                docstring=ast.get_docstring(stmt) or ""
            ))
            edges.append(CodeEdge(src=mod_id, dst=cls_id, kind="contains"))
            
            # Identify Inheritance (what this class extends)
            for base in stmt.bases:
                edges.append(CodeEdge(src=cls_id, dst=_dotted(base), kind="inherits"))
                
            # Identify Methods inside the class
            for item in stmt.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    m_id = f"fn:{path}:{stmt.name}.{item.name}"
                    nodes.append(CodeNode(
                        id=m_id, kind="method", name=f"{stmt.name}.{item.name}", file=path,
                        lineno=item.lineno, end_lineno=getattr(item, 'end_lineno', item.lineno),
                        signature=ast.unparse(item.args),
                        docstring=ast.get_docstring(item) or ""
                    ))
                    # The class "contains" this method
                    edges.append(CodeEdge(src=cls_id, dst=m_id, kind="contains"))
                    _walk_calls(item, m_id, edges)
    return nodes, edges
