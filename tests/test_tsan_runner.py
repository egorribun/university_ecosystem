from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scripts" / "run_tsan_tests.sh"
CANARY = SCRIPT.parents[1] / "tests" / "tsan_race_canary.c"


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


def test_tsan_suppresses_only_known_pyo3_argument_adapters() -> None:
    suppressions = SCRIPT.parents[1] / "tests" / "tsan_suppressions.txt"
    content = suppressions.read_text(encoding="utf-8")

    assert "race:__pyfunction_batch_detect_conflicts_py" in content
    assert "race:__pyfunction_verify_audit_signature" in content


def test_tsan_canary_synchronizes_start_before_unsynchronized_writes() -> None:
    """The runner canary must make the race observable on every Linux runner."""

    source = CANARY.read_text(encoding="utf-8")

    assert "pthread_barrier_t" in source
    assert "pthread_barrier_wait" in source
    assert "volatile int shared_value" in source


def test_tsan_canary_disables_pie_for_stable_tsan_address_space() -> None:
    """PIE can make libtsan silently miss the canary on hosted Linux images."""

    script = SCRIPT.read_text(encoding="utf-8")

    assert "-fno-pie" in script
    assert "-no-pie" in script
