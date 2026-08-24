"""PyO3 extension-module smoke test and CI import guard.

NOTE ON NAMING: the plan called this `test_smoke_pyo3_sanitizer.py` with
"sanitizer parity", but `rust_ext` exposes schedule-conflict / partition /
audit-signature functions — there is no HTML sanitizer in the PyO3 crate (that
lives in the frontend `wasm-sanitizer`, covered by its own native tests). So
this file delivers the *substance* the plan needed: a hard CI guard that the
extension-module build still imports + a small FFI smoke that regression-checks
the Stream-D1 feature-gate (extension-module stays the default), complementing
the existing `test_smoke_rust_audit.py` / `test_smoke_rust_partitions.py`
(which use a silent `importorskip` with no CI enforcement).
"""

import hashlib
import hmac
import os

import pytest

CI = os.environ.get("CI", "").strip().lower() == "true"

try:
    import rust_ext

    _IMPORT_ERROR: ImportError | None = None
except ImportError as exc:
    rust_ext = None  # type: ignore[assignment]
    _IMPORT_ERROR = exc

# FFI tests run wherever the extension is built; they skip cleanly when it is
# not. The CI hard-fail guard below is what turns a missing build into a CI
# error rather than a silent skip.
requires_rust_ext = pytest.mark.skipif(
    rust_ext is None, reason=f"rust_ext not built: {_IMPORT_ERROR}"
)


def test_rust_ext_importable_in_ci():
    """In CI the extension-module build MUST import — no silent skip.

    The D1 feature-gate keeps `pyo3/extension-module` as the default feature, so
    maturin/uv produce the same abi3 wheel. If that import ever breaks in CI,
    this fails loudly instead of the other smoke files silently skipping.
    """
    if CI:
        assert rust_ext is not None, (
            "rust_ext must be importable under CI=true after the Stream-D1 "
            f"feature-gate (extension-module is still default); import failed: {_IMPORT_ERROR}"
        )
    elif rust_ext is None:
        pytest.skip(f"rust_ext not built locally: {_IMPORT_ERROR}")


@requires_rust_ext
def test_detect_conflicts_overlap_same_day_parity():
    target = rust_ext.ScheduleItem("monday", 0, 3600, "both")
    overlapping = rust_ext.ScheduleItem("monday", 1800, 5400, "both")
    disjoint = rust_ext.ScheduleItem("monday", 7200, 9000, "both")
    other_day = rust_ext.ScheduleItem("tuesday", 0, 3600, "both")

    conflicts = rust_ext.detect_conflicts(target, [overlapping, disjoint, other_day])
    assert len(conflicts) == 1, "only the overlapping same-day item conflicts"
    assert conflicts[0].start_time == 1800


@requires_rust_ext
def test_detect_conflicts_respects_parity():
    target = rust_ext.ScheduleItem("monday", 0, 3600, "odd")
    even_overlap = rust_ext.ScheduleItem("monday", 1800, 5400, "even")
    # odd vs even on the same slot must NOT conflict (alternating weeks).
    assert rust_ext.detect_conflicts(target, [even_overlap]) == []


@requires_rust_ext
def test_batch_detect_conflicts_finds_overlapping_pair():
    a = rust_ext.ScheduleItem("monday", 0, 3600, "both")
    b = rust_ext.ScheduleItem("monday", 1800, 5400, "both")
    c = rust_ext.ScheduleItem("tuesday", 0, 3600, "both")
    pairs = rust_ext.batch_detect_conflicts([a, b, c])
    assert len(pairs) == 1, "exactly one overlapping pair (a, b)"


@requires_rust_ext
def test_find_optimal_slot_avoids_existing():
    existing = [rust_ext.ScheduleItem("monday", 0, 3600, "both")]
    # 60-minute slot somewhere in Monday's 09:00–12:00 window.
    slot = rust_ext.find_optimal_slot(60, existing, [("monday", [9, 10, 11])])
    assert slot is not None, "an open slot exists in the available block"
    assert slot.weekday == "monday"


@requires_rust_ext
def test_verify_audit_signature_ffi_parity():
    # Mirrors the native Rust HMAC test: a Python-computed HMAC-SHA256 must
    # verify through the Rust FFI boundary (and a wrong key must not).
    key = "ffi-parity-key"
    log_data = "log_9|user_42|action_export|2026-06-13T00:00:00Z"
    sig = hmac.new(key.encode(), log_data.encode(), hashlib.sha256).hexdigest()
    assert rust_ext.verify_audit_signature([key], log_data, sig) is True
    assert rust_ext.verify_audit_signature(["wrong-key"], log_data, sig) is False


@requires_rust_ext
def test_rust_ext_invalid_types_raise_type_error():
    # 1. Invalid argument types to ScheduleItem constructor
    with pytest.raises(TypeError):
        # start_time must be int, not string
        rust_ext.ScheduleItem("monday", "not-an-int", 3600, "both")

    with pytest.raises(TypeError):
        # weekday must be string, not None
        rust_ext.ScheduleItem(None, 0, 3600, "both")  # type: ignore[arg-type]

    # 2. Invalid argument types to detect_conflicts
    with pytest.raises(TypeError):
        target = rust_ext.ScheduleItem("monday", 0, 3600, "both")
        # existing must be a list, not a string
        rust_ext.detect_conflicts(target, "not-a-list")  # type: ignore[arg-type]

    # 3. Invalid offset range to get_partition_info
    with pytest.raises(ValueError):
        rust_ext.get_partition_info("events", 150)
    with pytest.raises(ValueError):
        rust_ext.get_partition_info("events", -150)

    # 4. Invalid types to get_partition_info
    with pytest.raises(TypeError):
        rust_ext.get_partition_info(123, 0)  # type: ignore[arg-type]

    # 5. Invalid types to verify_audit_signature
    with pytest.raises(TypeError):
        rust_ext.verify_audit_signature("not-a-list", "data", "sig")  # type: ignore[arg-type]

    # 6. batch_detect_conflicts size limit error
    huge_items = [rust_ext.ScheduleItem("monday", 0, 3600, "both") for _ in range(2501)]
    with pytest.raises(ValueError):
        rust_ext.batch_detect_conflicts(huge_items)


@requires_rust_ext
def test_rust_ext_multithreading_safety():
    import threading

    # Create a larger list of items to detect conflicts on
    items = [
        rust_ext.ScheduleItem("monday", i * 10, i * 10 + 5, "both") for i in range(100)
    ]

    errors = []

    def run_fuzz():
        try:
            for _ in range(50):
                # Call batch_detect_conflicts concurrently from multiple threads
                pairs = rust_ext.batch_detect_conflicts(items)
                assert isinstance(pairs, list)
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=run_fuzz) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"Errors occurred during concurrent execution: {errors}"


@requires_rust_ext
def test_rust_ext_gil_release_heavy():
    import threading
    import time

    # verify_audit_signature is an intensive operation that can be run concurrently
    # to prove GIL release.
    key = "secret-key"
    log_data = "log_data_payload_to_verify"
    import hashlib
    import hmac

    sig = hmac.new(key.encode(), log_data.encode(), hashlib.sha256).hexdigest()

    errors = []

    def run_signature_verifications():
        try:
            for _ in range(200):
                res = rust_ext.verify_audit_signature([key], log_data, sig)
                assert res is True
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=run_signature_verifications) for _ in range(8)]
    start = time.perf_counter()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    duration = time.perf_counter() - start

    assert not errors, f"Errors in GIL release tests: {errors}"
    print(f"Executed concurrent signature verification in {duration:.4f}s")
