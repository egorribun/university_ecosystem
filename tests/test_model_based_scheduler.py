"""Model-based stateful differential tests for Rust FFI scheduling optimizer.

Tests rust_ext.detect_conflicts, rust_ext.batch_detect_conflicts, and rust_ext.find_optimal_slot
against a pure Python reference model using hypothesis.stateful.RuleBasedStateMachine.
"""

from __future__ import annotations

import pytest
import hypothesis.strategies as st
from hypothesis.stateful import RuleBasedStateMachine, Bundle, rule, invariant

import rust_ext


def py_check_conflict(a: dict, b: dict) -> bool:
    """Python reference conflict detection logic."""
    if a["weekday"] != b["weekday"]:
        return False
    if a["parity"] != "both" and b["parity"] != "both" and a["parity"] != b["parity"]:
        return False
    return (
        a["start_time"] < a["end_time"]
        and b["start_time"] < b["end_time"]
        and a["start_time"] < b["end_time"]
        and b["start_time"] < a["end_time"]
    )


class ScheduleModelBasedTest(RuleBasedStateMachine):
    def __init__(self) -> None:
        super().__init__()
        # State variables
        self.items: list[dict] = []
        self.next_id = 1

    items_bundle = Bundle("items")

    @rule(
        target=items_bundle,
        weekday=st.sampled_from(["monday", "tuesday", "wednesday", "thursday", "friday"]),
        start_time=st.integers(min_value=0, max_value=86400),
        end_time=st.integers(min_value=0, max_value=86400),
        parity=st.sampled_from(["both", "even", "odd"]),
    )
    def add_item(self, weekday: str, start_time: int, end_time: int, parity: str) -> dict:
        item = {
            "id": self.next_id,
            "weekday": weekday,
            "start_time": start_time,
            "end_time": end_time,
            "parity": parity,
        }
        self.next_id += 1
        self.items.append(item)
        return item

    @rule(item=items_bundle)
    def remove_item(self, item: dict) -> None:
        if item in self.items:
            self.items.remove(item)

    @rule(
        item=items_bundle,
        weekday=st.sampled_from(["monday", "tuesday", "wednesday", "thursday", "friday"]),
        start_time=st.integers(min_value=0, max_value=86400),
        end_time=st.integers(min_value=0, max_value=86400),
        parity=st.sampled_from(["both", "even", "odd"]),
    )
    def update_item(self, item: dict, weekday: str, start_time: int, end_time: int, parity: str) -> None:
        if item in self.items:
            item["weekday"] = weekday
            item["start_time"] = start_time
            item["end_time"] = end_time
            item["parity"] = parity

    @invariant()
    def verify_detect_conflicts(self) -> None:
        """Compare detect_conflicts results between Python and Rust implementations."""
        # For each item, check conflicts with all other items
        for target in self.items:
            # Python reference conflicts list
            py_conflicts = {
                other["id"]
                for other in self.items
                if other["id"] != target["id"] and py_check_conflict(target, other)
            }

            # Rust implementation
            target_rust = rust_ext.ScheduleItem(
                weekday=target["weekday"],
                start_time=target["start_time"],
                end_time=target["end_time"],
                parity=target["parity"],
                id=target["id"],
            )
            existing_rust = [
                rust_ext.ScheduleItem(
                    weekday=item["weekday"],
                    start_time=item["start_time"],
                    end_time=item["end_time"],
                    parity=item["parity"],
                    id=item["id"],
                )
                for item in self.items
                if item["id"] != target["id"]
            ]

            rust_conflicts_raw = rust_ext.detect_conflicts(target_rust, existing_rust)
            rust_conflicts = {item.id for item in rust_conflicts_raw}

            assert py_conflicts == rust_conflicts, (
                f"Conflict mismatch for target {target}.\n"
                f"Python conflicts: {py_conflicts}\n"
                f"Rust conflicts: {rust_conflicts}"
            )

    @invariant()
    def verify_batch_detect_conflicts(self) -> None:
        """Compare batch_detect_conflicts results between Python and Rust implementations."""
        # Python reference batch conflicts (set of sorted ID tuples)
        py_batch: set[tuple[int, int]] = set()
        for i, a in enumerate(self.items):
            for b in self.items[i + 1:]:
                if py_check_conflict(a, b):
                    pair = tuple(sorted([a["id"], b["id"]]))
                    py_batch.add(pair)  # type: ignore[arg-type]

        # Rust implementation
        items_rust = [
            rust_ext.ScheduleItem(
                weekday=item["weekday"],
                start_time=item["start_time"],
                end_time=item["end_time"],
                parity=item["parity"],
                id=item["id"],
            )
            for item in self.items
        ]
        rust_batch_raw = rust_ext.batch_detect_conflicts(items_rust)
        rust_batch = {tuple(sorted([pair[0].id, pair[1].id])) for pair in rust_batch_raw}

        assert py_batch == rust_batch, (
            f"Batch conflict mismatch.\n"
            f"Python batch: {py_batch}\n"
            f"Rust batch: {rust_batch}"
        )

    @rule(
        duration_minutes=st.integers(min_value=15, max_value=120),
        weekday=st.sampled_from(["monday", "tuesday", "wednesday", "thursday", "friday"]),
    )
    def verify_find_optimal_slot(self, duration_minutes: int, weekday: str) -> None:
        """Verify find_optimal_slot results do not conflict with existing items."""
        existing_rust = [
            rust_ext.ScheduleItem(
                weekday=item["weekday"],
                start_time=item["start_time"],
                end_time=item["end_time"],
                parity=item["parity"],
                id=item["id"],
            )
            for item in self.items
        ]

        # Try both signatures for compatibility
        available_blocks = [(weekday, list(range(8, 21)))]
        try:
            suggested = rust_ext.find_optimal_slot(
                duration_minutes,
                existing_rust,
                available_blocks,
            )
        except TypeError:
            suggested = rust_ext.find_optimal_slot(
                duration_minutes,
                existing_rust,
                [weekday],
            )

        if suggested:
            assert suggested.weekday == weekday
            assert suggested.end_time - suggested.start_time == duration_minutes * 60
            assert suggested.parity == "both"

            # Verify that the suggested slot has no conflicts with any existing item
            suggested_dict = {
                "weekday": suggested.weekday,
                "start_time": suggested.start_time,
                "end_time": suggested.end_time,
                "parity": suggested.parity,
            }
            for item in self.items:
                assert not py_check_conflict(suggested_dict, item), (
                     f"Suggested slot {suggested_dict} conflicts with existing item {item}"
                )


TestScheduleModelBased = ScheduleModelBasedTest.TestCase
