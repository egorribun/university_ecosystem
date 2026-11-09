"""Create the AUD-322 chaos user and its chat through the public API.

The nightly chaos stack is a disposable Compose project, not an owned live
stand, so the database seed entry points (which fail closed outside owned
stands, AUD-313) refuse it. Instead the chaos module registers two ordinary
student accounts exactly as a person would, and the first opens a direct chat
with the second. Errors name the step and HTTP status, never a credential.
"""

from __future__ import annotations

import httpx

_TIMEOUT_SECONDS = 15.0


class ProvisioningError(RuntimeError):
    """A provisioning step failed."""


def peer_email(email: str) -> str:
    local, separator, domain = email.partition("@")
    if not local or separator != "@" or not domain:
        raise ProvisioningError("the chaos user must be an email address")
    return f"{local}-peer@{domain}"


def _csrf_token(client: httpx.Client) -> str:
    response = client.get("/api/v1/auth/csrf-cookie")
    token = client.cookies.get("csrf_token")
    if response.status_code != 200 or not token:
        raise ProvisioningError(
            f"CSRF cookie initialisation failed: HTTP {response.status_code}"
        )
    return token


def _register(base_url: str, email: str, password: str, full_name: str) -> None:
    with httpx.Client(base_url=base_url, timeout=_TIMEOUT_SECONDS) as client:
        response = client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": password, "full_name": full_name},
            headers={"X-CSRF-Token": _csrf_token(client)},
        )
    if response.status_code != 200:
        raise ProvisioningError(
            f"registering {full_name} failed: HTTP {response.status_code}"
        )


def _login(client: httpx.Client, email: str, password: str, label: str) -> None:
    response = client.post(
        "/api/v1/auth/login",
        data={"username": email, "password": password},
        headers={"X-CSRF-Token": _csrf_token(client)},
    )
    if response.status_code != 200 or not client.cookies.get("access_token_v2"):
        raise ProvisioningError(
            f"signing in as {label} failed: HTTP {response.status_code}"
        )


def _own_user_id(base_url: str, email: str, password: str) -> str:
    with httpx.Client(base_url=base_url, timeout=_TIMEOUT_SECONDS) as client:
        _login(client, email, password, "the chaos peer")
        response = client.get("/api/v1/users/me")
    user_id = response.json().get("id") if response.status_code == 200 else None
    if not isinstance(user_id, str) or not user_id:
        raise ProvisioningError(
            f"reading the chaos peer identity failed: HTTP {response.status_code}"
        )
    return user_id


def _open_chat(base_url: str, email: str, password: str, peer_id: str) -> str:
    with httpx.Client(base_url=base_url, timeout=_TIMEOUT_SECONDS) as client:
        _login(client, email, password, "the chaos user")
        created = client.post(
            "/api/v1/chats",
            json={"participant_id": peer_id},
            headers={"X-CSRF-Token": client.cookies.get("csrf_token") or ""},
        )
        if created.status_code != 200:
            raise ProvisioningError(
                f"opening the chaos chat failed: HTTP {created.status_code}"
            )
        chat_id = str(created.json().get("id"))
        listed = client.get("/api/v1/chats", params={"limit": 1})
    items = listed.json().get("items") if listed.status_code == 200 else None
    if not items or str(items[0].get("id")) != chat_id:
        raise ProvisioningError(
            f"the chaos chat is not listed for the chaos user: HTTP {listed.status_code}"
        )
    return chat_id


def provision(base_url: str, email: str, password: str) -> str:
    """Register the user and its peer, open their chat and return its id."""
    peer = peer_email(email)
    _register(base_url, email, password, "Chaos User")
    _register(base_url, peer, password, "Chaos Peer")
    peer_id = _own_user_id(base_url, peer, password)
    return _open_chat(base_url, email, password, peer_id)
