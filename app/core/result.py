"""Result pattern types for explicit error handling.

This module provides a lightweight implementation of the Result/Either pattern
for explicit error handling without exceptions. It follows functional programming
principles while remaining Pythonic and compatible with type checkers.

For complex async pipelines, consider using `dry-python/returns` library which
provides `FutureResult`, `flow`, and `bind` composition utilities.

Usage:
    from app.core.result import Result, Success, Failure, is_success, is_failure

    def divide(a: float, b: float) -> Result[float, str]:
        if b == 0:
            return Failure("Division by zero")
        return Success(a / b)

    result = divide(10, 2)
    if is_success(result):
        print(f"Result: {result.value}")
    else:
        print(f"Error: {result.error}")
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Generic, TypeVar, overload

T = TypeVar("T")  # Success value type
E = TypeVar("E")  # Error type
U = TypeVar("U")  # Mapped success value type
F = TypeVar("F")  # Mapped error type


@dataclass(frozen=True, slots=True)
class Success(Generic[T]):
    """Represents a successful result containing a value.

    Attributes:
        value: The success value.
    """

    value: T

    def __repr__(self) -> str:
        return f"Success({self.value!r})"

    def __bool__(self) -> bool:
        """Success is always truthy."""
        return True


@dataclass(frozen=True, slots=True)
class Failure(Generic[E]):
    """Represents a failed result containing an error.

    Attributes:
        error: The error value (typically an exception or error message).
    """

    error: E

    def __repr__(self) -> str:
        return f"Failure({self.error!r})"

    def __bool__(self) -> bool:
        """Failure is always falsy."""
        return False


# Result is a union of Success or Failure
Result = Success[T] | Failure[E]


def is_success(result: Result[T, E]) -> bool:
    """Check if a Result is a Success.

    Args:
        result: The result to check.

    Returns:
        True if the result is a Success, False otherwise.
    """
    return isinstance(result, Success)


def is_failure(result: Result[T, E]) -> bool:
    """Check if a Result is a Failure.

    Args:
        result: The result to check.

    Returns:
        True if the result is a Failure, False otherwise.
    """
    return isinstance(result, Failure)


def unwrap(result: Result[T, E]) -> T:
    """Extract the value from a Success, raising if Failure.

    Args:
        result: The result to unwrap.

    Returns:
        The success value.

    Raises:
        ValueError: If the result is a Failure.
    """
    if isinstance(result, Success):
        return result.value
    raise ValueError(f"Cannot unwrap Failure: {result.error}")


def unwrap_or(result: Result[T, E], default: T) -> T:
    """Extract the value from a Success, or return default if Failure.

    Args:
        result: The result to unwrap.
        default: The default value to return if Failure.

    Returns:
        The success value or the default.
    """
    if isinstance(result, Success):
        return result.value
    return default


def unwrap_error(result: Result[T, E]) -> E:
    """Extract the error from a Failure, raising if Success.

    Args:
        result: The result to unwrap.

    Returns:
        The error value.

    Raises:
        ValueError: If the result is a Success.
    """
    if isinstance(result, Failure):
        return result.error
    raise ValueError(f"Cannot unwrap_error Success: {result.value}")


@overload
def map_result(result: Success[T], func: Callable[[T], U]) -> Success[U]: ...


@overload
def map_result(result: Failure[E], func: Callable[[T], U]) -> Failure[E]: ...


def map_result(result: Result[T, E], func: Callable[[T], U]) -> Result[U, E]:
    """Apply a function to the value inside a Success.

    If the result is a Failure, returns it unchanged.

    Args:
        result: The result to map over.
        func: The function to apply to the success value.

    Returns:
        A new Result with the mapped value or the original Failure.
    """
    if isinstance(result, Success):
        return Success(func(result.value))
    return result


@overload
def flat_map(result: Success[T], func: Callable[[T], Result[U, E]]) -> Result[U, E]: ...


@overload
def flat_map(result: Failure[E], func: Callable[[T], Result[U, E]]) -> Failure[E]: ...


def flat_map(result: Result[T, E], func: Callable[[T], Result[U, E]]) -> Result[U, E]:
    """Apply a function returning a Result to the value inside a Success.

    This is the monadic bind operation, enabling sequential composition
    of Result-returning functions.

    Args:
        result: The result to flat_map over.
        func: The function to apply, which itself returns a Result.

    Returns:
        The result of applying func, or the original Failure.
    """
    if isinstance(result, Success):
        return func(result.value)
    return result


def map_error(result: Result[T, E], func: Callable[[E], F]) -> Result[T, F]:
    """Apply a function to the error inside a Failure.

    If the result is a Success, returns it unchanged.

    Args:
        result: The result to map over.
        func: The function to apply to the error value.

    Returns:
        A new Result with the mapped error or the original Success.
    """
    if isinstance(result, Failure):
        return Failure(func(result.error))
    return result  # type: ignore[return-value]


def from_exception(func: Callable[[], T]) -> Result[T, Exception]:
    """Execute a function and capture any exception as a Failure.

    Args:
        func: A zero-argument function to execute.

    Returns:
        Success with the return value, or Failure with the exception.
    """
    try:
        return Success(func())
    except Exception as exc:
        return Failure(exc)


async def from_async_exception(
    coro_func: Callable[[], T],
) -> Result[T, Exception]:
    """Execute an async function and capture any exception as a Failure.

    Args:
        coro_func: An async function to execute (already called, awaitable).

    Returns:
        Success with the return value, or Failure with the exception.
    """
    try:
        return Success(await coro_func())  # type: ignore[misc]
    except Exception as exc:
        return Failure(exc)


def collect_results(results: list[Result[T, E]]) -> Result[list[T], E]:
    """Collect a list of Results into a Result of list.

    If all results are Success, returns Success with list of values.
    If any result is Failure, returns the first Failure encountered.

    Args:
        results: List of Results to collect.

    Returns:
        Success with list of values, or first Failure.
    """
    values: list[T] = []
    for result in results:
        if isinstance(result, Failure):
            return result
        values.append(result.value)
    return Success(values)


def partition_results(
    results: list[Result[T, E]],
) -> tuple[list[T], list[E]]:
    """Partition a list of Results into successes and failures.

    Args:
        results: List of Results to partition.

    Returns:
        Tuple of (success values, error values).
    """
    successes: list[T] = []
    failures: list[E] = []
    for result in results:
        if isinstance(result, Success):
            successes.append(result.value)
        else:
            failures.append(result.error)
    return successes, failures
