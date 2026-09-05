from pathlib import Path
import ast

def test_no_llm_imports_in_financial_engine():
    """Verify statically that no file in app/core/financial_engine imports from app.ai or any LLM package."""
    engine_dir = Path(__file__).resolve().parent.parent.parent / "app" / "core" / "financial_engine"
    assert engine_dir.exists()

    forbidden_terms = ["openai", "anthropic", "langchain", "llama", "llm", "app.ai"]

    for py_file in engine_dir.glob("*.py"):
        content = py_file.read_text(encoding="utf-8")
        tree = ast.parse(content, filename=str(py_file))

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for name in node.names:
                    for forbidden in forbidden_terms:
                        assert forbidden not in name.name.lower(), f"Forbidden import '{name.name}' in {py_file.name}"
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    for forbidden in forbidden_terms:
                        assert forbidden not in node.module.lower(), f"Forbidden from-import '{node.module}' in {py_file.name}"
