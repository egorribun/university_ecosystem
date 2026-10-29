"""Inner producer for a separately verified owned client-IP probe.

Input addresses alone do not establish ownership. An outer coordinator must
verify and pin the signed stand, its daemon, containers and network inventory
before executing this producer, and repeat those checks after it has closed.
Only the fixed anonymous HTTP protocol is implemented here, not that adapter.
There is deliberately no CLI entrypoint or process/deployment integration.
The transport supports only bounded HTTP/1.0/1.1 GET/POST on fixed paths: no
DNS, environment proxies, TLS, redirects, retries, compression, authentication,
upgrades, chunk extensions or trailers. Loopback GET / is only a test seam.
"""

from __future__ import annotations

import json
import math
import re
import socket
import time
from collections.abc import Callable
from dataclasses import dataclass
from ipaddress import IPv4Address, IPv4Network

_PRIVATE = tuple(
    IPv4Network(value) for value in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
)
_HEX = re.compile(r"[0-9a-f]+\Z")
_NAME = re.compile(r"[!#$%&'*+.^_\x60|~0-9A-Za-z-]+\Z")
_COOKIE_VALUE = re.compile(r"[A-Za-z0-9._~-]{1,512}\Z")
_COOKIE_NAMES = frozenset({"csrf_token", "_csrf_anon_nonce"})
_INPUT_KEYS = frozenset(
    {
        "schema",
        "source_sha",
        "run_id",
        "routes",
        "gateway_ip",
        "ws_hub_ip",
        "backend_public_ip",
        "gateway_backend_peers",
        "trusted_proxies",
    }
)
_ROUTE_KEYS = frozenset({"network", "network_id", "subnet", "source_ip", "caddy_ip"})
_GATEWAY_PEER_KEYS = frozenset({"network", "network_id", "subnet", "address"})
_ROUTE_NETWORKS = ("public", "frontend_net")
_GATEWAY_NETWORKS = ("public", "internal", "revocation_net")
_CSRF_PATH = "/api/v1/auth/csrf-cookie"
# Logical limits and outer middleware headers differ for the MFA dependency.
_CASES = (
    ("login", "/api/v1/auth/login/json", 60, 60, 45.0),
    ("register", "/api/v1/auth/register", 5, 5, 45.0),
    ("mfa", "/api/v1/auth/mfa/verify", 5, 200, 45.0),
    ("forgot", "/api/v1/password/forgot", 3, 3, 45.0),
    ("ws_hub", "/ws/chat", 10, None, 5.0),
)
_API_PATHS = frozenset(case[1] for case in _CASES[:4])
_MAX_HEADERS = 16384
_MAX_BODY = 4096
_MAX_WIRE = 24576
_TOTAL_SECONDS = 120.0
_MAX_REQUESTS = 119


class ProbeError(RuntimeError):
    """A closed, non-sensitive producer failure."""


@dataclass(frozen=True, slots=True, repr=False)
class Request:
    source_ip: str
    target_ip: str
    port: int
    method: str
    path: str
    headers: tuple[tuple[str, str], ...]
    body: bytes


@dataclass(frozen=True, slots=True, repr=False)
class Response:
    status: int
    headers: tuple[tuple[str, str], ...]
    body: bytes
    source_verified: bool
    closed: bool


@dataclass(frozen=True, slots=True, repr=False)
class _Route:
    subnet: str
    source_ip: str
    caddy_ip: str


@dataclass(frozen=True, slots=True, repr=False)
class _Config:
    source_sha: str
    run_id: str
    routes: tuple[_Route, _Route]
    gateway_ip: str
    ws_hub_ip: str
    backend_public_ip: str


def _address(value: object, *, loopback: bool = False) -> IPv4Address:
    if type(value) is not str or not 1 <= len(value) <= 15:
        raise ProbeError("invalid address")
    try:
        address = IPv4Address(value)
    except ValueError:
        raise ProbeError("invalid address") from None
    if str(address) != value or not (
        any(address in network for network in _PRIVATE)
        or (loopback and address.is_loopback)
    ):
        raise ProbeError("invalid address")
    return address


def _identity(value: object, length: int) -> bool:
    return (
        type(value) is str
        and len(value) == length
        and _HEX.fullmatch(value) is not None
    )


def _topology_address(value: object) -> IPv4Address:
    try:
        return _address(value)
    except ProbeError:
        raise ProbeError("invalid topology") from None


def _topology_network(value: object) -> IPv4Network:
    if type(value) is not str or not 1 <= len(value) <= 18:
        raise ProbeError("invalid topology")
    try:
        network = IPv4Network(value)
    except ValueError:
        raise ProbeError("invalid topology") from None
    if str(network) != value or not any(
        network.subnet_of(private) for private in _PRIVATE
    ):
        raise ProbeError("invalid topology")
    return network


def _usable_host(address: IPv4Address, network: IPv4Network) -> bool:
    return address in network and address not in (
        network.network_address,
        network.broadcast_address,
    )


def parse_input(value: object) -> _Config:
    """Decode the fixed inspected-topology shape; this is not ownership admission."""
    if type(value) is not dict or value.keys() != _INPUT_KEYS:
        raise ProbeError("invalid topology")
    if (
        type(value["schema"]) is not str
        or value["schema"] != "ue-owned-client-ip-probe-input-v2"
        or not _identity(value["source_sha"], 40)
        or not _identity(value["run_id"], 64)
        or type(value["routes"]) is not list
        or len(value["routes"]) != 2
        or type(value["gateway_backend_peers"]) is not list
        or len(value["gateway_backend_peers"]) != 3
    ):
        raise ProbeError("invalid topology")
    routes: list[_Route] = []
    networks: list[IPv4Network] = []
    network_ids: list[str] = []
    for row, name in zip(value["routes"], _ROUTE_NETWORKS, strict=True):
        if (
            type(row) is not dict
            or row.keys() != _ROUTE_KEYS
            or row["network"] != name
            or not _identity(row["network_id"], 64)
        ):
            raise ProbeError("invalid topology")
        network = _topology_network(row["subnet"])
        source = _topology_address(row["source_ip"])
        caddy = _topology_address(row["caddy_ip"])
        if source == caddy or not all(
            _usable_host(address, network) for address in (source, caddy)
        ):
            raise ProbeError("invalid topology")
        networks.append(network)
        network_ids.append(row["network_id"])
        routes.append(_Route(row["subnet"], str(source), str(caddy)))
    gateway = _topology_address(value["gateway_ip"])
    ws_hub = _topology_address(value["ws_hub_ip"])
    backend_public = _topology_address(value["backend_public_ip"])
    if not all(
        _usable_host(address, networks[0])
        for address in (gateway, ws_hub, backend_public)
    ):
        raise ProbeError("invalid topology")

    gateway_addresses: list[str] = []
    for index, (row, name) in enumerate(
        zip(value["gateway_backend_peers"], _GATEWAY_NETWORKS, strict=True)
    ):
        if (
            type(row) is not dict
            or row.keys() != _GATEWAY_PEER_KEYS
            or row["network"] != name
            or not _identity(row["network_id"], 64)
        ):
            raise ProbeError("invalid topology")
        network = _topology_network(row["subnet"])
        address = _topology_address(row["address"])
        if not _usable_host(address, network):
            raise ProbeError("invalid topology")
        if index == 0:
            if (
                network != networks[0]
                or row["network_id"] != network_ids[0]
                or address != gateway
            ):
                raise ProbeError("invalid topology")
        else:
            networks.append(network)
            network_ids.append(row["network_id"])
        gateway_addresses.append(str(address))

    if len(set(network_ids)) != len(network_ids) or any(
        network.overlaps(other)
        for index, network in enumerate(networks)
        for other in networks[index + 1 :]
    ):
        raise ProbeError("invalid topology")
    addresses = [
        *(route.source_ip for route in routes),
        *(route.caddy_ip for route in routes),
        *gateway_addresses,
        str(ws_hub),
        str(backend_public),
    ]
    if len(set(addresses)) != len(addresses):
        raise ProbeError("invalid topology")
    trust = value["trusted_proxies"]
    expected = (
        {routes[0].caddy_ip, routes[1].caddy_ip, *gateway_addresses},
        {routes[0].caddy_ip},
        {routes[0].caddy_ip},
    )
    if type(trust) is not list or len(trust) != 3:
        raise ProbeError("invalid topology")
    for peers, approved in zip(trust, expected, strict=True):
        if (
            type(peers) is not list
            or len(peers) != len(approved)
            or any(type(peer) is not str for peer in peers)
            or set(peers) != approved
        ):
            raise ProbeError("invalid topology")
    return _Config(
        value["source_sha"],
        value["run_id"],
        (routes[0], routes[1]),
        str(gateway),
        str(ws_hub),
        str(backend_public),
    )


def _remaining(deadline: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise ProbeError("deadline expired")
    return remaining


def _header_map(
    headers: tuple[tuple[str, str], ...],
) -> dict[str, list[str]]:
    if type(headers) is not tuple or len(headers) > 64:
        raise ProbeError("invalid response")
    result: dict[str, list[str]] = {}
    size = 0
    for pair in headers:
        if type(pair) is not tuple or len(pair) != 2:
            raise ProbeError("invalid response")
        name, value = pair
        if (
            type(name) is not str
            or not 1 <= len(name) <= 64
            or _NAME.fullmatch(name) is None
            or type(value) is not str
            or any(not 32 <= ord(character) <= 126 for character in value)
        ):
            raise ProbeError("invalid response")
        size += len(name) + len(value) + 4
        if size > _MAX_HEADERS:
            raise ProbeError("invalid response")
        name = name.lower()
        if name in {"authorization", "proxy-authorization", "upgrade"}:
            raise ProbeError("non-anonymous response")
        result.setdefault(name, []).append(value)
    _cookies(result)
    return result


def _single(headers: dict[str, list[str]], name: str) -> str | None:
    values = headers.get(name, [])
    if len(values) > 1:
        raise ProbeError("ambiguous response")
    return values[0] if values else None


def _cookies(headers: dict[str, list[str]]) -> dict[str, str]:
    cookies: dict[str, str] = {}
    for value in headers.get("set-cookie", []):
        pair = value.split(";", 1)[0]
        name, separator, token = pair.partition("=")
        if (
            separator != "="
            or name not in _COOKIE_NAMES
            or name in cookies
            or _COOKIE_VALUE.fullmatch(token) is None
        ):
            raise ProbeError("non-anonymous response")
        cookies[name] = token
    return cookies


def _checked_response(response: Response) -> dict[str, list[str]]:
    if (
        type(response) is not Response
        or response.source_verified is not True
        or response.closed is not True
        or type(response.status) is not int
        or not 200 <= response.status <= 599
        or type(response.body) is not bytes
        or len(response.body) > _MAX_BODY
    ):
        raise ProbeError("incomplete observation")
    headers = _header_map(response.headers)
    encoding = _single(headers, "content-encoding")
    if encoding is not None and encoding.lower() != "identity":
        raise ProbeError("encoded response")
    return headers


def _collect(
    config: object, request: Callable[[Request, float], Response]
) -> dict[str, object]:
    """Collect fixed observations, never emit URLs, headers, cookies or bodies."""
    if type(config) is not _Config or not callable(request):
        raise ProbeError("invalid producer input")
    started = time.monotonic()
    deadline = started + _TOTAL_SECONDS
    count = 0

    def send(
        item: Request, case_deadline: float
    ) -> tuple[Response, dict[str, list[str]]]:
        nonlocal count
        if count >= _MAX_REQUESTS:
            raise ProbeError("request budget exhausted")
        timeout = min(5.0, _remaining(deadline), _remaining(case_deadline))
        count += 1
        try:
            response = request(item, timeout)
        except (OSError, ValueError, TypeError):
            raise ProbeError("request failed") from None
        _remaining(deadline)
        _remaining(case_deadline)
        return response, _checked_response(response)

    proof: list[tuple[tuple[str, str], ...]] = []
    for route in config.routes:
        response, headers = send(
            Request(route.source_ip, route.caddy_ip, 80, "GET", _CSRF_PATH, (), b""),
            deadline,
        )
        cookies = _cookies(headers)
        if response.status != 200 or cookies.keys() != _COOKIE_NAMES:
            raise ProbeError("anonymous CSRF setup failed")
        proof.append(
            (
                (
                    "cookie",
                    f"csrf_token={cookies['csrf_token']}; "
                    f"_csrf_anon_nonce={cookies['_csrf_anon_nonce']}",
                ),
                ("x-csrf-token", cookies["csrf_token"]),
            )
        )

    def observe(
        path: str,
        header_limit: int | None,
        case_deadline: float,
        source_index: int,
        extra: tuple[tuple[str, str], ...] = (),
        *,
        direct: bool = False,
        backend_direct: bool = False,
    ) -> int:
        is_ws = path == "/ws/chat"
        route = config.routes[source_index]
        target = route.caddy_ip
        port = 80
        target_path = path
        if backend_direct:
            target = config.backend_public_ip
            port = 8000
        elif direct:
            target = config.ws_hub_ip if is_ws else config.gateway_ip
            port = 8081 if is_ws else 8080
            target_path = "/ws" if is_ws else path
        response, headers = send(
            Request(
                route.source_ip,
                target,
                port,
                "GET" if is_ws else "POST",
                target_path,
                (() if is_ws else proof[source_index]) + extra,
                b"" if is_ws else b"{}",
            ),
            case_deadline,
        )
        content_type = _single(headers, "content-type") or ""
        if is_ws:
            expected_body = {
                401: b"Unauthorized\n",
                429: b"Too Many Requests\n",
            }.get(response.status)
            if (
                expected_body is None
                or response.body != expected_body
                or content_type.split(";", 1)[0].strip().lower() != "text/plain"
            ):
                raise ProbeError("wrong websocket responder")
        else:
            expected_type = (
                "application/problem+json"
                if response.status == 429
                else "application/json"
            )
            if (
                response.status not in (422, 429)
                or _single(headers, "x-ratelimit-limit") != str(header_limit)
                or content_type.split(";", 1)[0].strip().lower() != expected_type
            ):
                raise ProbeError("wrong backend responder")
        return response.status

    cases: list[dict[str, object]] = []
    for name, path, limit, header_limit, budget in _CASES:
        case_started = time.monotonic()
        case_deadline = min(deadline, case_started + budget)
        allowed = [observe(path, header_limit, case_deadline, 0) for _ in range(limit)]
        blocked = observe(path, header_limit, case_deadline, 0)
        other_client = observe(path, header_limit, case_deadline, 1)
        other_ip = config.routes[1].source_ip
        spoofed = [
            observe(path, header_limit, case_deadline, 0, ((header, value),))
            for header, value in (
                ("x-forwarded-for", other_ip),
                ("x-real-ip", other_ip),
                ("forwarded", f"for={other_ip}"),
            )
        ]
        direct = observe(
            path,
            header_limit,
            case_deadline,
            0,
            (("x-forwarded-for", other_ip),),
            direct=True,
        )
        backend_direct = (
            None
            if name == "ws_hub"
            else observe(
                path,
                header_limit,
                case_deadline,
                0,
                (("x-forwarded-for", other_ip),),
                backend_direct=True,
            )
        )
        cases.append(
            {
                "case": name,
                "allowed": allowed,
                "blocked": blocked,
                "other_client": other_client,
                "spoofed": spoofed,
                "direct_untrusted": direct,
                "backend_direct_untrusted": backend_direct,
                "elapsed_ms": int((time.monotonic() - case_started) * 1000),
            }
        )
    _remaining(deadline)
    frame: dict[str, object] = {
        "schema": "ue-owned-client-ip-v2",
        "source_sha": config.source_sha,
        "run_id": config.run_id,
        "closed": True,
        "sources_verified": True,
        "anonymous": True,
        "source_labels": ["public", "frontend_net"],
        "csrf_ready": [True, True],
        "setup_requests": 2,
        "http_requests": count,
        "elapsed_ms": int((time.monotonic() - started) * 1000),
        "cases": cases,
    }
    if count != _MAX_REQUESTS or len(json.dumps(frame).encode()) + 1 > 4096:
        raise ProbeError("invalid observation frame")
    return frame


def _request_bytes(item: Request) -> bytes:
    if type(item) is not Request:
        raise ProbeError("invalid request")
    source = _address(item.source_ip, loopback=True)
    target = _address(item.target_ip, loopback=True)
    local = source.is_loopback and target.is_loopback
    if (
        source.is_loopback != target.is_loopback
        or type(item.port) is not int
        or not 1 <= item.port <= 65535
        or type(item.body) is not bytes
        or type(item.method) is not str
        or type(item.path) is not str
        or len(item.path) > 64
    ):
        raise ProbeError("invalid request")
    if local:
        valid_route = (
            item.method == "GET"
            and item.path == "/"
            and item.body == b""
            and item.headers == ()
        )
    else:
        valid_route = source != target and (
            (
                item.method == "GET"
                and item.body == b""
                and (
                    (item.path == _CSRF_PATH and item.port == 80)
                    or (item.path == "/ws/chat" and item.port == 80)
                    or (item.path == "/ws" and item.port == 8081)
                )
            )
            or (
                item.method == "POST"
                and item.path in _API_PATHS
                and item.port in (80, 8000, 8080)
                and item.body == b"{}"
            )
        )
    if not valid_route or type(item.headers) is not tuple or len(item.headers) > 3:
        raise ProbeError("invalid request")
    supplied: dict[str, str] = {}
    for pair in item.headers:
        if type(pair) is not tuple or len(pair) != 2:
            raise ProbeError("invalid request")
        name, value = pair
        if (
            type(name) is not str
            or name
            not in {
                "cookie",
                "x-csrf-token",
                "x-forwarded-for",
                "x-real-ip",
                "forwarded",
            }
            or name in supplied
            or type(value) is not str
            or not 1 <= len(value) <= 1200
            or any(not 32 <= ord(character) <= 126 for character in value)
        ):
            raise ProbeError("invalid request")
        if name in {"x-forwarded-for", "x-real-ip"}:
            _address(value)
        elif name == "forwarded":
            if not value.startswith("for="):
                raise ProbeError("invalid request")
            _address(value[4:])
        elif name == "x-csrf-token":
            if _COOKIE_VALUE.fullmatch(value) is None:
                raise ProbeError("invalid request")
        else:
            pairs = value.split("; ")
            if len(pairs) != 2 or any(";" in pair for pair in pairs):
                raise ProbeError("invalid request")
            parsed = _cookies({"set-cookie": pairs})
            if parsed.keys() != _COOKIE_NAMES:
                raise ProbeError("invalid request")
        supplied[name] = value
    forwarding = ("x-forwarded-for", "x-real-ip", "forwarded")
    if sum(name in supplied for name in forwarding) > 1:
        raise ProbeError("invalid request")
    if item.method == "POST":
        cookies = _cookies({"set-cookie": supplied.get("cookie", "").split("; ")})
        if cookies.get("csrf_token") != supplied.get("x-csrf-token"):
            raise ProbeError("invalid request")
    elif "cookie" in supplied or "x-csrf-token" in supplied:
        raise ProbeError("invalid request")
    headers = [
        f"{item.method} {item.path} HTTP/1.1",
        "Host: localhost",
        "Accept: application/json, application/problem+json, text/plain",
        "Accept-Encoding: identity",
        "Connection: close",
    ]
    if item.method == "POST":
        headers.extend(("Content-Type: application/json", "Content-Length: 2"))
    headers.extend(f"{name}: {value}" for name, value in supplied.items())
    return ("\r\n".join(headers) + "\r\n\r\n").encode("ascii") + item.body


class _Reader:
    """One connection, one absolute deadline, one bounded wire allocation."""

    def __init__(self, connection: socket.socket, deadline: float) -> None:
        self.connection = connection
        self.deadline = deadline
        self.buffer = bytearray()
        self.received = 0

    def fill(self) -> bool:
        self.connection.settimeout(_remaining(self.deadline))
        chunk = self.connection.recv(min(4096, _MAX_WIRE - self.received + 1))
        _remaining(self.deadline)
        self.received += len(chunk)
        if self.received > _MAX_WIRE:
            raise ProbeError("response wire limit")
        self.buffer.extend(chunk)
        return bool(chunk)

    def line(self, limit: int) -> bytes:
        while True:
            end = self.buffer.find(b"\r\n")
            if end >= 0:
                if end + 2 > limit:
                    raise ProbeError("response header limit")
                result = bytes(self.buffer[:end])
                del self.buffer[: end + 2]
                return result
            if len(self.buffer) >= limit or b"\n" in self.buffer or not self.fill():
                raise ProbeError("invalid response line")

    def exact(self, count: int) -> bytes:
        while len(self.buffer) < count:
            if not self.fill():
                raise ProbeError("truncated response")
        result = bytes(self.buffer[:count])
        del self.buffer[:count]
        return result

    def until_closed(self) -> bytes:
        while True:
            if len(self.buffer) > _MAX_BODY:
                raise ProbeError("response body limit")
            if not self.fill():
                return bytes(self.buffer)


def _read_response(reader: _Reader) -> tuple[int, tuple[tuple[str, str], ...], bytes]:
    header_bytes = 0
    for _ in range(9):
        line = reader.line(min(1024, _MAX_HEADERS - header_bytes))
        header_bytes += len(line) + 2
        matched = re.fullmatch(rb"HTTP/1\.[01] ([1-5][0-9]{2})(?: [ -~]*)?", line)
        if matched is None:
            raise ProbeError("invalid response status")
        status = int(matched[1])
        pairs: list[tuple[str, str]] = []
        for _ in range(65):
            line = reader.line(_MAX_HEADERS - header_bytes)
            header_bytes += len(line) + 2
            if not line:
                break
            name, separator, value = line.partition(b":")
            if separator != b":" or line[:1] in (b" ", b"\t"):
                raise ProbeError("invalid response header")
            pairs.append((name.decode("ascii"), value.strip(b" ").decode("ascii")))
        else:
            raise ProbeError("response header count")
        headers = _header_map(tuple(pairs))
        length = _single(headers, "content-length")
        transfer = _single(headers, "transfer-encoding")
        encoding = _single(headers, "content-encoding")
        if (
            (length is not None and transfer is not None)
            or (transfer is not None and transfer.lower() != "chunked")
            or (encoding is not None and encoding.lower() != "identity")
        ):
            raise ProbeError("unsupported response framing")
        if status >= 200:
            break
        if status != 100 or length is not None or transfer is not None:
            raise ProbeError("unsupported interim response")
    else:
        raise ProbeError("interim response limit")

    if transfer is not None:
        chunks: list[bytes] = []
        body_size = 0
        for _ in range(128):
            line = reader.line(32)
            if re.fullmatch(rb"[0-9a-fA-F]{1,8}", line) is None:
                raise ProbeError("invalid response chunk")
            size = int(line, 16)
            if size == 0:
                if reader.line(_MAX_HEADERS - header_bytes) != b"":
                    raise ProbeError("response trailers not supported")
                body = b"".join(chunks)
                break
            body_size += size
            if body_size > _MAX_BODY:
                raise ProbeError("response body limit")
            chunks.append(reader.exact(size))
            if reader.exact(2) != b"\r\n":
                raise ProbeError("invalid response chunk")
        else:
            raise ProbeError("response chunk count")
    elif length is not None:
        if re.fullmatch(r"[0-9]{1,5}", length) is None:
            raise ProbeError("invalid response length")
        size = int(length)
        if size > _MAX_BODY:
            raise ProbeError("response body limit")
        body = reader.exact(size)
    else:
        body = reader.until_closed()
        reader.buffer.clear()
    if reader.buffer:
        raise ProbeError("unexpected response bytes")
    return status, tuple(pairs), body


def _request(request: Request, timeout: float) -> Response:
    """Use only numeric IPv4, never DNS/proxies/redirects/retries or credentials."""
    if (
        type(timeout) not in (int, float)
        or not 0 < timeout <= 5
        or not math.isfinite(timeout)
    ):
        raise ProbeError("invalid timeout")
    wire = _request_bytes(request)
    deadline = time.monotonic() + timeout
    connection: socket.socket | None = None
    response: tuple[int, tuple[tuple[str, str], ...], bytes] | None = None
    try:
        connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        connection.settimeout(_remaining(deadline))
        connection.bind((request.source_ip, 0))
        connection.settimeout(_remaining(deadline))
        connection.connect((request.target_ip, request.port))
        if connection.getsockname()[
            0
        ] != request.source_ip or connection.getpeername() != (
            request.target_ip,
            request.port,
        ):
            raise ProbeError("socket attribution failed")
        connection.settimeout(_remaining(deadline))
        connection.sendall(wire)
        _remaining(deadline)
        response = _read_response(_Reader(connection, deadline))
        _remaining(deadline)
    except (OSError, ValueError, OverflowError):
        raise ProbeError("transport failed") from None
    finally:
        if connection is not None:
            try:
                connection.close()
            except OSError:
                raise ProbeError("socket closure failed") from None
            if connection.fileno() != -1:
                raise ProbeError("socket closure unconfirmed")
    if response is None:
        raise ProbeError("missing response")
    _remaining(deadline)
    status, headers, body = response
    return Response(status, headers, body, True, True)
