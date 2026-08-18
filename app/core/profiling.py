from __future__ import annotations

import os
from typing import Protocol, runtime_checkable

from app.core.logging import get_logger

_logger = get_logger(__name__)


@runtime_checkable
class Profiler(Protocol):
    """Protocol for continuous profiling.

    TD-003 (audit 2026-03-10): Vendor-neutral abstraction for profiling.
    Prevents direct dependency on Pyroscope throughout the application core.
    """

    def configure(self) -> None:
        """Initialize and start the profiler."""


class PyroscopeProfiler:
    """Pyroscope implementation of the Profiler protocol."""

    def __init__(
        self,
        application_name: str = "university-backend",
        server_address: str | None = None,
    ) -> None:
        self.application_name = application_name
        self.server_address = server_address or os.getenv(
            "PYROSCOPE_SERVER_ADDRESS", "http://pyroscope:4040"
        )

    def configure(self) -> None:
        try:
            import pyroscope

            pyroscope.configure(
                application_name=self.application_name,
                server_address=self.server_address,
            )
            _logger.info(
                "Pyroscope profiling configured for %s at %s",
                self.application_name,
                self.server_address,
            )
        except ImportError:
            _logger.warning(
                "Pyroscope is enabled but the 'pyroscope-io' package is not installed. "
                "Profiling will be disabled."
            )
        except Exception as e:  # RZ-22-01-JUSTIFIED: optional dependency — Pyroscope init failure is non-fatal (reviewed TD-27-04)
            _logger.error("Failed to initialize Pyroscope: %s", e)


class NoOpProfiler:
    """Default profiler that does nothing."""

    def configure(self) -> None:
        _logger.debug("Profiling is disabled (NoOpProfiler active).")


def get_profiler() -> Profiler:
    """Factory function for the active profiler based on environment."""
    enabled = os.getenv("ENABLE_PROFILING", "false").lower() == "true"
    if not enabled:
        return NoOpProfiler()

    return PyroscopeProfiler()
