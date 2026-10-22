"""Bounded cookie-authenticated HTTP observations for the disabled NATS probe.

This adapter is not wired to the outage coordinator or a command. It uses the
existing signed-owner lease, reads only the already-created owner-scoped admin
credential, and makes one attempt at each HTTP mutation.
"""

from __future__ import annotations

import asyncio
import json
import os
import stat
from collections.abc import Awaitable, Callable
from dataclasses import replace
from pathlib import Path
from typing import TypeVar
from uuid import UUID

import httpx

from scripts import live_stand
from scripts.owned_nats_coordinator import (
    ChatCreateEvidence,
    LoginEvidence,
    MessagePostEvidence,
    OwnerEvidence,
    ParticipantEvidence,
)
from scripts.owned_nats_outage import Deadline, DeadlineVerdict, MessageEvidence
from scripts.owned_nats_owner_adapter import OwnerFilePins

_ADMIN_EMAIL = "admin@university.dev"
_ADMIN_PATH = "/api/v1/auth/login"
_CSRF_PATH = "/api/v1/auth/csrf-cookie"
_CHAT_PATH = "/api/v1/chats"
_MESSAGE_CONTENT = "owned NATS acceptance probe"
_MAX_CREDENTIAL_BYTES = 4096
_MAX_RESPONSE_BYTES = 64 * 1024
_READ_CHUNK_BYTES = 1024
_HTTP_OPERATION_SECONDS = 10.0
_HTTP_REQUEST_SECONDS = 5.0
_HTTP_READ_POLL_SECONDS = 1.0
_CSRF_COOKIE = "csrf_token"
_ACCESS_COOKIE = "access_token_v2"
_T = TypeVar("_T")


class HttpObservationNotReady(RuntimeError):
    """Closed non-sensitive failure at the cookie-authenticated HTTP boundary."""

    def __str__(self) -> str:
        return "owner-scoped HTTP observation is not ready"

    def __repr__(self) -> str:
        return "HttpObservationNotReady()"


def _not_ready() -> None:
    raise HttpObservationNotReady from None


def _uuid(value: object) -> bool:
    if type(value) is not str:
        return False
    try:
        parsed = UUID(value)
    except (ValueError, AttributeError):
        return False
    return parsed.int != 0 and str(parsed) == value


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def _reject_json_constant(_value: str) -> None:
    raise ValueError


def _decode_json_object(raw: bytes | bytearray) -> dict[str, object]:
    try:
        value = json.loads(
            raw,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
        _not_ready()
    if type(value) is not dict:
        _not_ready()
    return value


def _stat_identity(metadata: os.stat_result) -> tuple[object, ...]:
    birth_or_change: int | None
    if os.name == "nt":
        birth_or_change = getattr(metadata, "st_birthtime_ns", None)
    else:
        birth_or_change = getattr(metadata, "st_ctime_ns", None)
    if type(birth_or_change) is not int:
        _not_ready()
    modified = getattr(metadata, "st_mtime_ns", None)
    if type(modified) is not int:
        _not_ready()
    return (
        metadata.st_dev,
        metadata.st_ino,
        stat.S_IFMT(metadata.st_mode),
        metadata.st_size,
        modified,
        birth_or_change,
    )


def _is_regular_file(metadata: os.stat_result) -> bool:
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return stat.S_ISREG(metadata.st_mode) and not (
        getattr(metadata, "st_file_attributes", 0) & reparse_flag
    )


class OwnedNatsHttpPort:
    """Implement only the existing coordinator's login/DM/message HTTP ports."""

    __slots__ = (
        "_admin_id",
        "_chat_id",
        "_closed",
        "_cookies",
        "_create_attempted",
        "_login_attempted",
        "_owner",
        "_owner_port",
        "_peer_id",
        "_pins",
        "_send_attempted",
        "_test_transport",
        "_verified_login",
    )

    def __init__(
        self,
        owner_port: object,
        pins: OwnerFilePins,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if (
            not callable(getattr(owner_port, "read_signed_owner", None))
            or type(pins) is not OwnerFilePins
            or (transport is not None and type(transport) is not httpx.MockTransport)
        ):
            _not_ready()
        try:
            self._owner_port = owner_port
            self._pins = replace(pins)
            self._test_transport = transport
            self._cookies = httpx.Cookies()
            self._owner: OwnerEvidence | None = None
            self._admin_id: str | None = None
            self._peer_id: str | None = None
            self._chat_id: str | None = None
            self._login_attempted = False
            self._verified_login = False
            self._create_attempted = False
            self._send_attempted = False
            self._closed = False
        except (AttributeError, TypeError, ValueError):
            _not_ready()

    @staticmethod
    def _seconds(deadline: object, cap_seconds: float = _HTTP_REQUEST_SECONDS) -> float:
        if type(deadline) is not Deadline:
            _not_ready()
        try:
            budget = deadline.timeout_for(cap_seconds)
        except Exception:
            _not_ready()
        if (
            budget.verdict is not DeadlineVerdict.VALID
            or type(budget.seconds) not in (int, float)
            or budget.seconds <= 0
        ):
            _not_ready()
        return float(budget.seconds)

    @classmethod
    def _operation_deadline(cls, deadline: object) -> Deadline:
        if type(deadline) is not Deadline:
            _not_ready()
        try:
            child = deadline.child(_HTTP_OPERATION_SECONDS)
        except Exception:
            _not_ready()
        cls._seconds(child, _HTTP_OPERATION_SECONDS)
        return child

    @classmethod
    async def _bounded_operation(
        cls,
        deadline: Deadline,
        operation: Callable[[Deadline], Awaitable[_T]],
    ) -> _T:
        seconds = cls._seconds(deadline, _HTTP_OPERATION_SECONDS)
        async with asyncio.timeout(seconds):
            return await operation(deadline)

    @classmethod
    def _run_bounded(
        cls,
        deadline: Deadline,
        operation: Callable[[Deadline], Awaitable[_T]],
    ) -> _T:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            pass
        else:
            _not_ready()
        try:
            return asyncio.run(cls._bounded_operation(deadline, operation))
        except HttpObservationNotReady:
            raise
        except Exception:
            _not_ready()

    def _owner_matches_pins(self, owner: OwnerEvidence) -> bool:
        try:
            repository = Path(self._pins.repository).resolve(strict=True)
            state_root = Path(self._pins.state_root).resolve(strict=True)
            return (
                type(owner) is OwnerEvidence
                and Path(owner.repository).resolve(strict=True) == repository
                and Path(owner.worktree).resolve(strict=True) == state_root
                and owner.source_sha == self._pins.source_sha
                and type(owner.project_name) is str
                and bool(owner.project_name)
                and owner.stack in {"core", "full"}
                and type(owner.published_ports) is tuple
            )
        except (AttributeError, OSError, RuntimeError, TypeError, ValueError):
            return False

    def _check_owner(self, owner: OwnerEvidence, deadline: Deadline) -> None:
        self._seconds(deadline)
        if not self._owner_matches_pins(owner):
            _not_ready()
        try:
            observed = self._owner_port.read_signed_owner(deadline=deadline)
        except Exception:
            _not_ready()
        self._seconds(deadline)
        if type(observed) is not OwnerEvidence or observed != owner:
            _not_ready()

    @staticmethod
    def _http_port(owner: OwnerEvidence) -> int:
        try:
            matches = [
                port for name, port in owner.published_ports if name == "CADDY_HTTP"
            ]
        except (AttributeError, TypeError, ValueError):
            _not_ready()
        if (
            len(matches) != 1
            or type(matches[0]) is not int
            or not 1 <= matches[0] <= 65535
        ):
            _not_ready()
        return matches[0]

    def _client_for(self, owner: OwnerEvidence) -> httpx.AsyncClient:
        if self._closed:
            _not_ready()
        base_url = f"http://127.0.0.1:{self._http_port(owner)}"
        try:
            transport = self._test_transport or httpx.AsyncHTTPTransport(
                retries=0,
                trust_env=False,
            )
            cookies = httpx.Cookies()
            cookies.update(self._cookies)
            return httpx.AsyncClient(
                base_url=base_url,
                transport=transport,
                trust_env=False,
                follow_redirects=False,
                timeout=_HTTP_REQUEST_SECONDS,
                cookies=cookies,
                headers={
                    "Accept": "application/json",
                    "Accept-Encoding": "identity",
                },
            )
        except Exception:
            _not_ready()

    def _read_admin_password(self, owner: OwnerEvidence, deadline: Deadline) -> str:
        self._check_owner(owner, deadline)
        path = Path(owner.worktree) / live_stand.ADMIN_PASSWORD_FILE
        descriptor: int | None = None
        payload = bytearray()
        try:
            relative = live_stand.ADMIN_PASSWORD_FILE
            worktree = Path(owner.worktree)
            live_stand._assert_worktree_paths_safe(worktree, (relative,))
            if os.name != "nt":
                live_stand._assert_private_state_directory(path.parent)
            before = path.lstat()
            if (
                not _is_regular_file(before)
                or before.st_size < 1
                or before.st_size > _MAX_CREDENTIAL_BYTES
            ):
                _not_ready()
            flags = (
                os.O_RDONLY
                | getattr(os, "O_BINARY", 0)
                | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_NONBLOCK", 0)
            )
            descriptor = os.open(path, flags)
            opened = os.fstat(descriptor)
            if not _is_regular_file(opened) or _stat_identity(before) != _stat_identity(
                opened
            ):
                _not_ready()
            if opened.st_uid != self._pins.owner_uid:
                _not_ready()
            if os.name != "nt":
                if opened.st_uid != os.getuid() or stat.S_IMODE(opened.st_mode) & 0o077:
                    _not_ready()
            while len(payload) <= _MAX_CREDENTIAL_BYTES:
                self._seconds(deadline)
                remaining = _MAX_CREDENTIAL_BYTES + 1 - len(payload)
                chunk = os.read(descriptor, min(_READ_CHUNK_BYTES, remaining))
                if not chunk:
                    break
                payload.extend(chunk)
            if len(payload) > _MAX_CREDENTIAL_BYTES:
                _not_ready()
            after_descriptor = os.fstat(descriptor)
            live_stand._assert_worktree_paths_safe(worktree, (relative,))
            after_path = path.lstat()
            if (
                not _is_regular_file(after_descriptor)
                or not _is_regular_file(after_path)
                or _stat_identity(opened) != _stat_identity(after_descriptor)
                or _stat_identity(opened) != _stat_identity(after_path)
            ):
                _not_ready()
            credential = _decode_json_object(payload)
            password = credential.get("password")
            if (
                set(credential) != {"version", "project_name", "password"}
                or credential.get("version") != 1
                or credential.get("project_name") != owner.project_name
                or type(password) is not str
                or not 32 <= len(password) <= 128
            ):
                _not_ready()
            self._check_owner(owner, deadline)
            return password
        except HttpObservationNotReady:
            raise
        except Exception:
            _not_ready()
        finally:
            payload.clear()
            if descriptor is not None:
                try:
                    os.close(descriptor)
                except OSError:
                    _not_ready()

    @staticmethod
    def _csrf_token(cookies: httpx.Cookies) -> str:
        try:
            matches = [
                cookie
                for cookie in cookies.jar
                if cookie.name == _CSRF_COOKIE
                and cookie.domain == "127.0.0.1"
                and cookie.path == "/"
                and cookie.domain_specified is False
                and not cookie.is_expired()
            ]
        except Exception:
            _not_ready()
        if (
            len(matches) != 1
            or type(matches[0].value) is not str
            or not matches[0].value
            or len(matches[0].value) > 512
        ):
            _not_ready()
        return matches[0].value

    @staticmethod
    def _has_http_only_access_cookie(cookies: httpx.Cookies) -> bool:
        try:
            matches = [
                cookie
                for cookie in cookies.jar
                if cookie.name == _ACCESS_COOKIE
                and cookie.domain == "127.0.0.1"
                and cookie.path == "/"
                and cookie.domain_specified is False
                and not cookie.is_expired()
            ]
            return (
                len(matches) == 1
                and bool(matches[0].value)
                and matches[0].secure is False
                and matches[0].has_nonstandard_attr("HttpOnly")
            )
        except Exception:
            return False

    @classmethod
    async def _read_response_json(
        cls, response: httpx.Response, deadline: Deadline
    ) -> dict[str, object]:
        body = bytearray()
        try:
            declared_length = response.headers.get("content-length")
            if declared_length is not None:
                if not declared_length.isascii() or not declared_length.isdecimal():
                    _not_ready()
                if int(declared_length) > _MAX_RESPONSE_BYTES:
                    _not_ready()
            content_encoding = response.headers.get("content-encoding")
            if content_encoding is not None and content_encoding.lower() != "identity":
                _not_ready()
            async for chunk in response.aiter_raw():
                cls._seconds(deadline)
                if type(chunk) is not bytes:
                    _not_ready()
                if len(body) + len(chunk) > _MAX_RESPONSE_BYTES:
                    _not_ready()
                body.extend(chunk)
            if not body:
                _not_ready()
            return _decode_json_object(body)
        except HttpObservationNotReady:
            raise
        except Exception:
            _not_ready()
        finally:
            body.clear()

    async def _request(
        self,
        client: httpx.AsyncClient,
        owner: OwnerEvidence,
        deadline: Deadline,
        method: str,
        path: str,
        *,
        data: dict[str, str] | None = None,
        json_body: dict[str, str] | None = None,
        files: dict[str, tuple[None, str]] | None = None,
    ) -> tuple[int, dict[str, object] | None]:
        self._check_owner(owner, deadline)
        seconds = self._seconds(deadline)
        headers: dict[str, str] = {}
        if method == "POST":
            headers["X-CSRF-Token"] = self._csrf_token(client.cookies)
        response: httpx.Response | None = None
        try:
            request = client.build_request(
                method,
                path,
                data=data,
                json=json_body,
                files=files,
                headers=headers,
                timeout=httpx.Timeout(
                    connect=seconds,
                    read=min(seconds, _HTTP_READ_POLL_SECONDS),
                    write=seconds,
                    pool=seconds,
                ),
            )
            if (
                request.url.scheme != "http"
                or request.url.host != "127.0.0.1"
                or request.url.port != self._http_port(owner)
                or "authorization" in request.headers
            ):
                _not_ready()
            response = await client.send(
                request,
                stream=True,
                auth=None,
                follow_redirects=False,
            )
            status = response.status_code
            if type(status) is not int or 300 <= status < 400:
                _not_ready()
            body = (
                await self._read_response_json(response, deadline)
                if status == 200
                else None
            )
            return status, body
        except HttpObservationNotReady:
            raise
        except Exception:
            _not_ready()
        finally:
            if response is not None:
                try:
                    await response.aclose()
                except Exception:
                    _not_ready()
            self._check_owner(owner, deadline)

    def _save_cookies(self, client: httpx.AsyncClient) -> None:
        cookies = httpx.Cookies()
        cookies.update(client.cookies)
        self._cookies = cookies

    def _poison(self) -> None:
        self._closed = True
        self._verified_login = False
        self._cookies.clear()

    def login_admin(
        self,
        owner: OwnerEvidence,
        admin_id: str,
        *,
        deadline: Deadline,
    ) -> LoginEvidence:
        if (
            self._closed
            or self._login_attempted
            or not _uuid(admin_id)
            or not self._owner_matches_pins(owner)
        ):
            _not_ready()
        operation_deadline = self._operation_deadline(deadline)
        self._check_owner(owner, operation_deadline)
        self._login_attempted = True
        self._owner = owner
        self._admin_id = admin_id
        try:
            password = self._read_admin_password(owner, operation_deadline)
            evidence = self._run_bounded(
                operation_deadline,
                lambda bounded: self._login_operation(
                    owner, admin_id, password, bounded
                ),
            )
            self._verified_login = True
            return evidence
        except HttpObservationNotReady:
            self._poison()
            raise
        except Exception:
            self._poison()
            _not_ready()

    async def _login_operation(
        self,
        owner: OwnerEvidence,
        admin_id: str,
        password: str,
        deadline: Deadline,
    ) -> LoginEvidence:
        async with self._client_for(owner) as client:
            status, _ = await self._request(client, owner, deadline, "GET", _CSRF_PATH)
            if status != 200:
                _not_ready()
            self._csrf_token(client.cookies)
            status, body = await self._request(
                client,
                owner,
                deadline,
                "POST",
                _ADMIN_PATH,
                data={"username": _ADMIN_EMAIL, "password": password},
            )
            if (
                status != 200
                or body is None
                or not self._has_http_only_access_cookie(client.cookies)
            ):
                _not_ready()
            csrf_token = self._csrf_token(client.cookies)
            user = body.get("user")
            actor_id = user.get("id") if type(user) is dict else None
            body.clear()
            if actor_id != admin_id or not csrf_token:
                _not_ready()
            self._save_cookies(client)
            return LoginEvidence(status_code=status, actor_id=actor_id)

    def create_dm_once(
        self,
        peer_id: str,
        *,
        deadline: Deadline,
    ) -> ChatCreateEvidence:
        owner = self._owner
        admin_id = self._admin_id
        if (
            self._closed
            or not self._verified_login
            or self._create_attempted
            or owner is None
            or admin_id is None
            or not _uuid(peer_id)
            or peer_id == admin_id
            or not self._has_http_only_access_cookie(self._cookies)
        ):
            _not_ready()
        self._create_attempted = True
        self._peer_id = peer_id
        operation_deadline = self._operation_deadline(deadline)
        try:
            evidence = self._run_bounded(
                operation_deadline,
                lambda bounded: self._create_operation(
                    owner, admin_id, peer_id, bounded
                ),
            )
            self._chat_id = evidence.id
            return evidence
        except HttpObservationNotReady:
            self._poison()
            raise
        except Exception:
            self._poison()
            _not_ready()

    async def _create_operation(
        self,
        owner: OwnerEvidence,
        admin_id: str,
        peer_id: str,
        deadline: Deadline,
    ) -> ChatCreateEvidence:
        async with self._client_for(owner) as client:
            status, body = await self._request(
                client,
                owner,
                deadline,
                "POST",
                _CHAT_PATH,
                json_body={"participant_id": peer_id},
            )
            if status != 200 or body is None:
                _not_ready()
            chat_id = body.get("id")
            chat_type = body.get("chat_type")
            raw_participants = body.get("participants")
            if (
                not _uuid(chat_id)
                or chat_type != "dm"
                or type(raw_participants) is not list
                or len(raw_participants) != 2
            ):
                _not_ready()
            participants: list[ParticipantEvidence] = []
            for raw in raw_participants:
                if (
                    type(raw) is not dict
                    or not _uuid(raw.get("id"))
                    or type(raw.get("is_active")) is not bool
                ):
                    _not_ready()
                participants.append(
                    ParticipantEvidence(id=raw["id"], is_active=raw["is_active"])
                )
            body.clear()
            if {row.id for row in participants} != {admin_id, peer_id} or any(
                row.is_active is not True for row in participants
            ):
                _not_ready()
            self._save_cookies(client)
            return ChatCreateEvidence(
                status_code=status,
                id=chat_id,
                chat_type=chat_type,
                participants=tuple(participants),
            )

    def send_message_once(
        self,
        chat_id: str,
        content: str,
        *,
        deadline: Deadline,
    ) -> MessagePostEvidence:
        owner = self._owner
        admin_id = self._admin_id
        if (
            self._closed
            or not self._create_attempted
            or self._send_attempted
            or owner is None
            or admin_id is None
            or self._chat_id is None
            or chat_id != self._chat_id
            or content != _MESSAGE_CONTENT
            or not self._verified_login
            or not self._has_http_only_access_cookie(self._cookies)
        ):
            _not_ready()
        self._send_attempted = True
        operation_deadline = self._operation_deadline(deadline)
        try:
            return self._run_bounded(
                operation_deadline,
                lambda bounded: self._send_operation(
                    owner, admin_id, chat_id, content, bounded
                ),
            )
        except HttpObservationNotReady:
            self._poison()
            raise
        except Exception:
            self._poison()
            _not_ready()

    async def _send_operation(
        self,
        owner: OwnerEvidence,
        admin_id: str,
        chat_id: str,
        content: str,
        deadline: Deadline,
    ) -> MessagePostEvidence:
        async with self._client_for(owner) as client:
            status, body = await self._request(
                client,
                owner,
                deadline,
                "POST",
                f"/api/v1/chats/{chat_id}/messages",
                files={"content": (None, content)},
            )
            if status != 200 or body is None:
                _not_ready()
            message_id = body.get("id")
            response_chat_id = body.get("chat_id")
            sender_id = body.get("sender_id")
            response_content = body.get("content")
            reply_to = body.get("reply_to", object())
            attachments = body.get("attachments", [])
            body.clear()
            if (
                not _uuid(message_id)
                or response_chat_id != chat_id
                or sender_id != admin_id
                or response_content != content
                or reply_to is not None
                or type(attachments) is not list
                or attachments
            ):
                _not_ready()
            self._save_cookies(client)
            return MessagePostEvidence(
                status_code=status,
                message=MessageEvidence(message_id, chat_id, admin_id, content),
            )

    def close_clients(self, *, deadline: Deadline) -> None:
        if type(deadline) is not Deadline:
            _not_ready()
        self._closed = True
        self._verified_login = False
        try:
            self._cookies.clear()
        except Exception:
            _not_ready()

    def __repr__(self) -> str:
        return "<OwnedNatsHttpPort>"
