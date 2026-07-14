from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scripts" / "run_tsan_tests.sh"


def test_tsan_preloads_python_directly_instead_of_uv() -> None:
    script = SCRIPT.read_text(encoding="utf-8")

    assert 'PYTHON_BIN="${REPO_ROOT}/.venv/bin/python"' in script
    assert '  "${PYTHON_BIN}" -m pytest \\' in script
    assert "  uv run pytest \\" not in script
