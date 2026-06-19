import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from src.codebase_kb.extract.ast_python import parse_python_file

dummy_code = """
import json

def format_data(data):
    return json.dumps(data)

class ApiHandler:
    def send(self, payload):
        formatted = format_data(payload)
        return formatted
"""

nodes, edges = parse_python_file("dummy.py", dummy_code)

for node in nodes:
    print(f"[{node.kind.upper()}] ID: {node.id} | Name: {node.name}")

for edge in edges:
    print(f"{edge.src} --({edge.kind})--> {edge.dst}")