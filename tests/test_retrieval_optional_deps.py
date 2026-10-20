import subprocess
import sys
from pathlib import Path


def test_bm25_remains_available_without_optional_vector_dependencies():
    repository = Path(__file__).resolve().parents[1]
    script = r"""
import builtins
from pathlib import Path

original_import = builtins.__import__
def without_vector_packages(name, *args, **kwargs):
    if name.split(".", 1)[0] in {"joblib", "numpy", "sklearn"}:
        raise ImportError("blocked optional package: " + name)
    return original_import(name, *args, **kwargs)

builtins.__import__ = without_vector_packages
from papertrail import retrieval
retrieval.bm25_search = lambda *_args, **_kwargs: [{"chunk_id": "fixture"}]
assert retrieval.retrieve(Path("unused.sqlite3"), "query", mode="bm25")
assert retrieval.vector_search(Path("unused.sqlite3"), "") == []
try:
    retrieval.vector_search(Path("unused.sqlite3"), "query")
except RuntimeError as error:
    assert "requirements-dev.txt" in str(error)
else:
    raise AssertionError("vector mode must report its missing optional dependencies")
"""
    subprocess.run(
        [sys.executable, "-c", script],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    )
