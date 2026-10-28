"""Inner producer for a separately verified owned client-IP probe.

Input addresses alone do not establish ownership. An outer coordinator must
verify and pin the signed stand, its daemon, containers and network inventory
before executing this producer, and repeat those checks after it has closed.
"""

from __future__ import annotations

from dataclasses import dataclass


class ProbeError(RuntimeError):
    """A closed, non-sensitive producer failure."""


@dataclass(frozen=True, slots=True)
class Request:
    source_ip: str
    target_ip: str
    port: int
    method: str
    path: str
    headers: tuple[tuple[str, str], ...]
    body: bytes


@dataclass(frozen=True, slots=True)
class Response:
    status: int
    headers: tuple[tuple[str, str], ...]
    body: bytes
    source_verified: bool
    closed: bool


def parse_input(value: object) -> object:
    raise ProbeError("producer not implemented")


def _collect(config: object, request: object) -> dict[str, object]:
    raise ProbeError("producer not implemented")


def _request(request: Request, timeout: float) -> Response:
    raise ProbeError("producer not implemented")
