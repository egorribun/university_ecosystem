"""Native extraction must not deadlock on Python sequence callbacks."""

import os
import subprocess
import sys
import textwrap

import pytest


@pytest.mark.parametrize("operation", ["detect", "batch", "slot"])
@pytest.mark.parametrize("callback", ["len", "iter", "getitem"])
def test_schedule_extraction_can_reenter_from_sequence(operation, callback):
    try:
        import rust_ext  # noqa: F401
    except ImportError:
        if os.environ.get("CI", "").lower() == "true":
            pytest.fail("rust_ext must be built for the FFI reentrancy regression")
        pytest.skip("rust_ext is not built")

    script = textwrap.dedent(
        """
        import sys
        import rust_ext

        operation, callback = sys.argv[1:]
        target = rust_ext.ScheduleItem("monday", 0, 3600, "both")
        calls = []

        def reenter(where):
            if where == callback:
                assert rust_ext.detect_conflicts(target, []) == []
                calls.append(where)

        class Sequence:
            def __len__(self):
                reenter("len")
                return 1

            def __iter__(self):
                reenter("iter")
                return (self[index] for index in range(1))

            def __getitem__(self, index):
                reenter("getitem")
                if index != 0:
                    raise IndexError(index)
                return target

        if operation == "detect":
            assert len(rust_ext.detect_conflicts(target, Sequence())) == 1
        elif operation == "batch":
            assert rust_ext.batch_detect_conflicts(Sequence()) == []
        else:
            assert rust_ext.find_optimal_slot(60, Sequence(), []) is None
        assert calls == [callback], calls
        # A completed callback must leave subsequent calls usable.
        assert rust_ext.detect_conflicts(target, []) == []
        print("REENTRANT_EXTRACTION_OK")
        """
    )
    # A deadlock in native code cannot be interrupted reliably by a pytest
    # thread timeout; an isolated child is forcibly reaped by subprocess.run.
    result = subprocess.run(
        [sys.executable, "-c", script, operation, callback],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "REENTRANT_EXTRACTION_OK"


def test_concurrent_native_calls_use_owned_schedule_snapshots():
    try:
        import rust_ext  # noqa: F401
    except ImportError:
        if os.environ.get("CI", "").lower() == "true":
            pytest.fail("rust_ext must be built for the FFI concurrency regression")
        pytest.skip("rust_ext is not built")

    script = textwrap.dedent(
        """
        from concurrent.futures import ThreadPoolExecutor
        import rust_ext

        item = rust_ext.ScheduleItem("monday", 0, 3600, "both")
        shared = [item] * 40

        def evaluate(_):
            assert len(rust_ext.detect_conflicts(item, shared)) == 40
            assert len(rust_ext.batch_detect_conflicts(shared)) == 780
            slot = rust_ext.find_optimal_slot(60, shared, [("tuesday", [9])])
            assert slot is not None and slot.weekday == "tuesday"

        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(evaluate, range(16)))
        assert item.start_time == 0 and item.end_time == 3600
        print("CONCURRENT_EXTRACTION_OK")
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "CONCURRENT_EXTRACTION_OK"
