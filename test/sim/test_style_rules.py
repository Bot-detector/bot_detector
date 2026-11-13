import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

DST_ROOT = REPO_ROOT / "dst"
TEST_ROOT = REPO_ROOT / "test" / "sim"

# the style test itself must stay clean under the rule it enforces
assert TEST_ROOT.exists()
assert DST_ROOT.exists()


def _python_files(root: Path) -> list[Path]:
    files = sorted(root.rglob("*.py"))
    assert files, f"no python files under {root}"
    return files


def _module_docstring_file(path: Path) -> str | None:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    if ast.get_docstring(tree) is None:
        return None
    return str(path.relative_to(REPO_ROOT))


def test_dst_files_have_no_module_docstring():
    violations = [
        name
        for path in _python_files(DST_ROOT)
        if (name := _module_docstring_file(path)) is not None
    ]
    assert violations == []


def test_sim_test_files_have_no_module_docstring():
    violations = [
        name
        for path in _python_files(TEST_ROOT)
        if (name := _module_docstring_file(path)) is not None
    ]
    assert violations == []
