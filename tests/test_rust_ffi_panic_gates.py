"""FFI boundary safety and panic gate verification for the PyO3 rust_ext module.

Checks that incorrect parameters, boundary values, and malformed structures
raise expected Python exceptions (TypeError, ValueError) rather than causing
the native extension to panic or crash the Python interpreter.
"""

from __future__ import annotations

import pytest

try:
    import rust_ext

    _IMPORT_ERROR = None
except ImportError as exc:
    rust_ext = None  # type: ignore[assignment]
    _IMPORT_ERROR = exc

requires_rust_ext = pytest.mark.skipif(
    rust_ext is None, reason=f"rust_ext not built: {_IMPORT_ERROR}"
)


@requires_rust_ext
class TestRustFFIPanicGates:
    def test_schedule_item_invalid_types(self) -> None:
        # Weekday type check
        with pytest.raises(TypeError):
            rust_ext.ScheduleItem(123, 0, 3600, "both")  # type: ignore[arg-type]

        # Time bounds and types
        with pytest.raises(TypeError):
            rust_ext.ScheduleItem("monday", "zero", 3600, "both")  # type: ignore[arg-type]

        with pytest.raises(TypeError):
            rust_ext.ScheduleItem("monday", 0, None, "both")  # type: ignore[arg-type]

        # Parity type check
        with pytest.raises(TypeError):
            rust_ext.ScheduleItem("monday", 0, 3600, True)  # type: ignore[arg-type]

    def test_detect_conflicts_invalid_inputs(self) -> None:
        target = rust_ext.ScheduleItem("monday", 0, 3600, "both")

        # Existing items must be a sequence of ScheduleItems, not arbitrary objects
        with pytest.raises(TypeError):
            rust_ext.detect_conflicts(target, [1, 2, 3])  # type: ignore[list-item]

        with pytest.raises(TypeError):
            rust_ext.detect_conflicts(None, [])  # type: ignore[arg-type]

    def test_batch_detect_conflicts_boundaries(self) -> None:
        # Exceeding the maximum allowed items
        items = [rust_ext.ScheduleItem("monday", 0, 3600, "both") for _ in range(2501)]
        with pytest.raises(ValueError, match="Input exceeds maximum allowed items"):
            rust_ext.batch_detect_conflicts(items)

        # Passing non-list parameter
        with pytest.raises(TypeError):
            rust_ext.batch_detect_conflicts("not-a-list")  # type: ignore[arg-type]

    def test_get_partition_info_boundaries(self) -> None:
        # month_offset boundary: 120 is maximum allowed
        info_max = rust_ext.get_partition_info("events", 120)
        assert info_max.name.startswith("events_y")

        info_min = rust_ext.get_partition_info("events", -120)
        assert info_min.name.startswith("events_y")

        # Exceeding bounds must raise ValueError
        with pytest.raises(
            ValueError, match="month_offset .* is out of the allowed range"
        ):
            rust_ext.get_partition_info("events", 121)

        with pytest.raises(
            ValueError, match="month_offset .* is out of the allowed range"
        ):
            rust_ext.get_partition_info("events", -121)

        # Invalid table name type
        with pytest.raises(TypeError):
            rust_ext.get_partition_info(None, 0)  # type: ignore[arg-type]

    def test_is_partition_expired_boundaries(self) -> None:
        # Negative retention days should return False rather than panic
        assert rust_ext.is_partition_expired("events_y2026m07", "events", -10) is False

        # Malformed partition names should return False safely
        assert rust_ext.is_partition_expired("events_y2026", "events", 30) is False
        assert rust_ext.is_partition_expired("events_y2026mXX", "events", 30) is False
        assert rust_ext.is_partition_expired("users_y2026m07", "events", 30) is False

        # Null table names / partition names
        with pytest.raises(TypeError):
            rust_ext.is_partition_expired(None, "events", 30)  # type: ignore[arg-type]

    def test_verify_audit_signature_invalid_keys(self) -> None:
        # Incorrect key argument types
        with pytest.raises(TypeError):
            rust_ext.verify_audit_signature("not-a-list-of-keys", "data", "sig")  # type: ignore[arg-type]

        # Incorrect signature type
        with pytest.raises(TypeError):
            rust_ext.verify_audit_signature(["key1"], "data", None)  # type: ignore[arg-type]

        # Malformed non-hex signatures should not panic, just return False
        assert (
            rust_ext.verify_audit_signature(["key1"], "data", "not-hex-signature")
            is False
        )
        assert rust_ext.verify_audit_signature(["key1"], "data", "") is False
