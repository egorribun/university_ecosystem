from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scripts" / "run_tsan_tests.sh"


def test_tsan_preloads_python_directly_instead_of_uv() -> None:
    script = SCRIPT.read_text(encoding="utf-8")

    assert 'PYTHON_BIN="${REPO_ROOT}/.venv/bin/python"' in script
    assert '  "${PYTHON_BIN}" -m pytest \\' in script
    assert "  uv run pytest \\" not in script

    assert 'TSAN_LOG_PREFIX="${REPO_ROOT}/tsan-report"' in script
    assert "log_path=${TSAN_LOG_PREFIX}" in script
    assert "TEST_EXIT_CODE=$?" in script


def test_tsan_suppresses_uvloop_embedded_libuv() -> None:
    suppressions = SCRIPT.parents[1] / "tests" / "tsan_suppressions.txt"

    assert "called_from_lib:uvloop" in suppressions.read_text(encoding="utf-8")
