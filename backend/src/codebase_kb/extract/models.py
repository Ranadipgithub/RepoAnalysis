from dataclasses import dataclass

@dataclass
class CodeNode:
    id: str            # Unique identifier (e.g., "fn:app/main.py:login")
    kind: str          # "module", "function", "method", or "class"
    name: str          # Human-readable name (e.g., "login")
    file: str          # The file path this node lives in
    lineno: int        # Starting line number
    end_lineno: int    # Ending line number
    signature: str     # The function/class signature (arguments/bases)
    docstring: str     # The docstring, if any

@dataclass
class CodeEdge:
    src: str           # ID of the source CodeNode
    dst: str           # ID of the destination CodeNode
    kind: str          # "import", "call", "inherits", "contains", or "decorates"
    label: str = ""    # Optional text (e.g., the specific alias imported)
