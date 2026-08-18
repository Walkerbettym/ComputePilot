"""Check that runtime/ has no agent/ or LLM imports."""
import ast
import sys
from pathlib import Path

RUNTIME_DIR = Path("sciflow/runtime")
FORBIDDEN = {"sciflow.agent", "openai", "anthropic", "httpx"}

errors = []
for py_file in RUNTIME_DIR.rglob("*.py"):
    tree = ast.parse(py_file.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if any(alias.name.startswith(f) for f in FORBIDDEN):
                    errors.append(f"{py_file}: imports {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            _mod = node.module
            if _mod and any(_mod.startswith(f) for f in FORBIDDEN):
                errors.append(f"{py_file}: from {_mod} import ...")

if errors:
    print("DEPENDENCY VIOLATION — runtime depends on agent/LLM:")
    for e in errors:
        print(f"  {e}")
    sys.exit(1)
else:
    print("OK: runtime has no forbidden dependencies")
