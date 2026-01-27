"""Tests for the Result pattern implementation.

Validates Success/Failure types, utility functions, and composition operations.
"""

import pytest

from app.core.result import (
    Failure,
    Result,
    Success,
    collect_results,
    flat_map,
    from_exception,
    is_failure,
    is_success,
    map_error,
    map_result,
    partition_results,
    unwrap,
    unwrap_error,
    unwrap_or,
)


class TestSuccessType:
    """Tests for the Success type."""

    def test_success_stores_value(self) -> None:
        result = Success(42)
        assert result.value == 42

    def test_success_is_truthy(self) -> None:
        result = Success("value")
        assert bool(result) is True

    def test_success_repr(self) -> None:
        result = Success("test")
        assert repr(result) == "Success('test')"

    def test_success_with_none_value(self) -> None:
        result = Success(None)
        assert result.value is None
        assert bool(result) is True

    def test_success_equality(self) -> None:
        assert Success(42) == Success(42)
        assert Success("a") != Success("b")

    def test_success_is_frozen(self) -> None:
        result = Success(42)
        with pytest.raises(AttributeError):
            result.value = 100  # type: ignore[misc]


class TestFailureType:
    """Tests for the Failure type."""

    def test_failure_stores_error(self) -> None:
        error = ValueError("something went wrong")
        result = Failure(error)
        assert result.error is error

    def test_failure_is_falsy(self) -> None:
        result = Failure("error")
        assert bool(result) is False

    def test_failure_repr(self) -> None:
        result = Failure("error message")
        assert repr(result) == "Failure('error message')"

    def test_failure_with_exception(self) -> None:
        error = RuntimeError("critical failure")
        result = Failure(error)
        assert isinstance(result.error, RuntimeError)
        assert str(result.error) == "critical failure"

    def test_failure_equality(self) -> None:
        assert Failure("a") == Failure("a")
        assert Failure("a") != Failure("b")

    def test_failure_is_frozen(self) -> None:
        result = Failure("error")
        with pytest.raises(AttributeError):
            result.error = "new error"  # type: ignore[misc]


class TestTypeGuards:
    """Tests for is_success and is_failure type guards."""

    def test_is_success_with_success(self) -> None:
        result: Result[int, str] = Success(42)
        assert is_success(result) is True
        assert is_failure(result) is False

    def test_is_failure_with_failure(self) -> None:
        result: Result[int, str] = Failure("error")
        assert is_failure(result) is True
        assert is_success(result) is False


class TestUnwrap:
    """Tests for unwrap utilities."""

    def test_unwrap_success(self) -> None:
        result: Result[int, str] = Success(42)
        assert unwrap(result) == 42

    def test_unwrap_failure_raises(self) -> None:
        result: Result[int, str] = Failure("error")
        with pytest.raises(ValueError, match="Cannot unwrap Failure"):
            unwrap(result)

    def test_unwrap_or_success(self) -> None:
        result: Result[int, str] = Success(42)
        assert unwrap_or(result, 0) == 42

    def test_unwrap_or_failure_returns_default(self) -> None:
        result: Result[int, str] = Failure("error")
        assert unwrap_or(result, 0) == 0

    def test_unwrap_error_from_failure(self) -> None:
        result: Result[int, str] = Failure("error")
        assert unwrap_error(result) == "error"

    def test_unwrap_error_from_success_raises(self) -> None:
        result: Result[int, str] = Success(42)
        with pytest.raises(ValueError, match="Cannot unwrap_error Success"):
            unwrap_error(result)


class TestMapResult:
    """Tests for map_result transformation."""

    def test_map_result_transforms_success(self) -> None:
        result: Result[int, str] = Success(5)
        mapped = map_result(result, lambda x: x * 2)
        assert mapped == Success(10)

    def test_map_result_preserves_failure(self) -> None:
        result: Result[int, str] = Failure("error")
        mapped = map_result(result, lambda x: x * 2)
        assert mapped == Failure("error")

    def test_map_result_type_transformation(self) -> None:
        result: Result[int, str] = Success(42)
        mapped = map_result(result, str)
        assert mapped == Success("42")


class TestFlatMap:
    """Tests for flat_map (monadic bind) operation."""

    def test_flat_map_chains_success(self) -> None:
        def safe_divide(x: int) -> Result[float, str]:
            if x == 0:
                return Failure("division by zero")
            return Success(100.0 / x)

        result: Result[int, str] = Success(5)
        chained = flat_map(result, safe_divide)
        assert chained == Success(20.0)

    def test_flat_map_short_circuits_on_failure(self) -> None:
        def should_not_be_called(x: int) -> Result[float, str]:
            raise AssertionError("This should not be called")

        result: Result[int, str] = Failure("initial error")
        chained = flat_map(result, should_not_be_called)
        assert chained == Failure("initial error")

    def test_flat_map_chains_to_failure(self) -> None:
        def always_fail(x: int) -> Result[float, str]:
            return Failure("operation failed")

        result: Result[int, str] = Success(5)
        chained = flat_map(result, always_fail)
        assert chained == Failure("operation failed")


class TestMapError:
    """Tests for map_error transformation."""

    def test_map_error_transforms_failure(self) -> None:
        result: Result[int, str] = Failure("error")
        mapped = map_error(result, lambda e: f"Wrapped: {e}")
        assert mapped == Failure("Wrapped: error")

    def test_map_error_preserves_success(self) -> None:
        result: Result[int, str] = Success(42)
        mapped = map_error(result, lambda e: f"Wrapped: {e}")
        assert mapped == Success(42)


class TestFromException:
    """Tests for from_exception utility."""

    def test_from_exception_captures_success(self) -> None:
        result = from_exception(lambda: 42)
        assert result == Success(42)

    def test_from_exception_captures_failure(self) -> None:
        def failing_func() -> int:
            raise ValueError("test error")

        result = from_exception(failing_func)
        assert is_failure(result)
        assert isinstance(unwrap_error(result), ValueError)


class TestCollectResults:
    """Tests for collect_results aggregation."""

    def test_collect_all_successes(self) -> None:
        results: list[Result[int, str]] = [
            Success(1),
            Success(2),
            Success(3),
        ]
        collected = collect_results(results)
        assert collected == Success([1, 2, 3])

    def test_collect_with_failure_returns_first_failure(self) -> None:
        results: list[Result[int, str]] = [
            Success(1),
            Failure("first error"),
            Success(3),
            Failure("second error"),
        ]
        collected = collect_results(results)
        assert collected == Failure("first error")

    def test_collect_empty_list(self) -> None:
        results: list[Result[int, str]] = []
        collected = collect_results(results)
        assert collected == Success([])


class TestPartitionResults:
    """Tests for partition_results utility."""

    def test_partition_mixed_results(self) -> None:
        results: list[Result[int, str]] = [
            Success(1),
            Failure("error1"),
            Success(2),
            Failure("error2"),
            Success(3),
        ]
        successes, failures = partition_results(results)
        assert successes == [1, 2, 3]
        assert failures == ["error1", "error2"]

    def test_partition_all_successes(self) -> None:
        results: list[Result[int, str]] = [
            Success(1),
            Success(2),
        ]
        successes, failures = partition_results(results)
        assert successes == [1, 2]
        assert failures == []

    def test_partition_all_failures(self) -> None:
        results: list[Result[int, str]] = [
            Failure("a"),
            Failure("b"),
        ]
        successes, failures = partition_results(results)
        assert successes == []
        assert failures == ["a", "b"]


class TestRealWorldScenarios:
    """Tests simulating real-world usage patterns."""

    def test_pipeline_composition(self) -> None:
        """Test chaining multiple Result-returning operations."""

        def parse_int(s: str) -> Result[int, str]:
            try:
                return Success(int(s))
            except ValueError:
                return Failure(f"Cannot parse '{s}' as integer")

        def validate_positive(n: int) -> Result[int, str]:
            if n > 0:
                return Success(n)
            return Failure(f"Number {n} is not positive")

        def double(n: int) -> Result[int, str]:
            return Success(n * 2)

        # Success path
        result = flat_map(
            flat_map(parse_int("5"), validate_positive),
            double,
        )
        assert result == Success(10)

        # Failure at parse
        result = flat_map(
            flat_map(parse_int("abc"), validate_positive),
            double,
        )
        assert is_failure(result)
        assert "Cannot parse" in unwrap_error(result)

        # Failure at validation
        result = flat_map(
            flat_map(parse_int("-5"), validate_positive),
            double,
        )
        assert is_failure(result)
        assert "not positive" in unwrap_error(result)

    def test_error_recovery_pattern(self) -> None:
        """Test recovering from errors with default values."""

        def fetch_config(key: str) -> Result[str, str]:
            configs = {"host": "localhost"}
            if key in configs:
                return Success(configs[key])
            return Failure(f"Config '{key}' not found")

        # Found config
        host = unwrap_or(fetch_config("host"), "default")
        assert host == "localhost"

        # Missing config, use default
        port = unwrap_or(fetch_config("port"), "8080")
        assert port == "8080"

    def test_batch_processing_with_collection(self) -> None:
        """Test processing multiple items and collecting results."""

        def process_item(item: int) -> Result[int, str]:
            if item < 0:
                return Failure(f"Negative value: {item}")
            return Success(item * 2)

        # All valid items
        items = [1, 2, 3, 4, 5]
        results = [process_item(i) for i in items]
        collected = collect_results(results)
        assert collected == Success([2, 4, 6, 8, 10])

        # Some invalid items - use partition to handle all
        mixed_items = [1, -2, 3, -4, 5]
        mixed_results = [process_item(i) for i in mixed_items]
        successes, failures = partition_results(mixed_results)
        assert successes == [2, 6, 10]
        assert len(failures) == 2
