from __future__ import annotations

import importlib.util
import os
import ssl
import sys
import threading
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock

import grpc
import pytest

import app.core.security.spiffe as spiffe
from app.core.security.spiffe import (
    SPIFFEAuthMiddleware,
    SVIDManager,
    create_spiffe_client_ssl_context,
    create_spiffe_server_ssl_context,
    get_spiffe_grpc_credentials,
)


def _scope(path: str = "/api/internal/resource", **extra: object) -> dict[str, object]:
    scope: dict[str, object] = {
        "type": "http",
        "method": "GET",
        "path": path,
        "headers": [],
    }
    scope.update(extra)
    return scope


def test_optional_pyspiffe_import_path_sets_availability_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_id_module = ModuleType("pyspiffe.spiffe_id.spiffe_id")
    fake_id_module.SpiffeId = object
    fake_source_module = ModuleType("pyspiffe.workloadapi.x509_source")
    fake_source_module.X509Source = object
    packages = {
        "pyspiffe": ModuleType("pyspiffe"),
        "pyspiffe.spiffe_id": ModuleType("pyspiffe.spiffe_id"),
        "pyspiffe.spiffe_id.spiffe_id": fake_id_module,
        "pyspiffe.workloadapi": ModuleType("pyspiffe.workloadapi"),
        "pyspiffe.workloadapi.x509_source": fake_source_module,
    }
    for name, module in packages.items():
        monkeypatch.setitem(sys.modules, name, module)

    source_path = Path(spiffe.__file__)
    spec = importlib.util.spec_from_file_location("spiffe_with_pyspiffe", source_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module._PYSPIFFE_AVAILABLE is True


def test_load_cert_chain_uses_temporary_files_without_manager() -> None:
    context = MagicMock()
    spiffe._load_cert_chain_from_pem(
        context,
        b"CERT",
        b"KEY",
        lock=threading.Lock(),
        svid_manager=object(),
    )

    call = context.load_cert_chain.call_args.kwargs
    assert call["certfile"] != call["keyfile"]
    assert not os.path.exists(call["certfile"])
    assert not os.path.exists(call["keyfile"])


def test_svid_manager_recreates_files_and_handles_cleanup_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = SVIDManager()
    manager.close()
    cert_path, key_path = manager._write_active_files((b"CERT", b"KEY"))
    assert Path(cert_path).read_bytes() == b"CERT"
    assert Path(key_path).read_bytes() == b"KEY"
    manager._write_active_files((b"CERT", b"KEY"))

    cleanup_manager = SVIDManager()
    monkeypatch.setattr(spiffe.shutil, "rmtree", MagicMock(side_effect=OSError("busy")))
    cleanup_manager.close()
    assert cleanup_manager._temp_dir == ""


def test_svid_manager_start_stop_and_source_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    disabled = SVIDManager(enabled=False)
    disabled.start()

    monkeypatch.setattr(spiffe, "_PYSPIFFE_AVAILABLE", False)
    degraded = SVIDManager(enabled=True)
    degraded.start()

    source = MagicMock()
    monkeypatch.setattr(spiffe, "_PYSPIFFE_AVAILABLE", True)
    monkeypatch.setattr(spiffe, "X509Source", MagicMock(return_value=source))
    manager = SVIDManager(enabled=True)
    manager.start()
    assert manager._source is source
    manager.stop()
    source.close.assert_called_once()

    failing_source = MagicMock(side_effect=RuntimeError("agent unavailable"))
    monkeypatch.setattr(spiffe, "X509Source", failing_source)
    failing = SVIDManager(enabled=True)
    failing.start()

    close_failing = SVIDManager(enabled=True)
    close_failing._source = MagicMock()
    close_failing._source.close.side_effect = RuntimeError("close failed")
    close_failing.stop()


def test_svid_manager_active_pair_and_retrieval_edges(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = SVIDManager()
    server_context = object()
    client_context = object()
    monkeypatch.setattr(
        spiffe, "create_spiffe_server_ssl_context", lambda _mgr: server_context
    )
    monkeypatch.setattr(
        spiffe, "create_spiffe_client_ssl_context", lambda _mgr: client_context
    )

    assert manager.set_active_svid((b"CERT", b"KEY")) == (b"CERT", b"KEY")
    assert manager._server_ssl_context is server_context
    assert manager._client_ssl_context is client_context

    svid = SimpleNamespace(cert_bytes=b"CERT-2", private_key_bytes=b"KEY-2")
    assert manager.set_active_svid(svid) == (b"CERT-2", b"KEY-2")
    assert manager.set_active_svid(object()) == (b"CERT-2", b"KEY-2")

    source = MagicMock()
    source.get_s_v_i_d.return_value = None
    manager._cached_pair = None
    manager._source = source
    assert manager.get_svid_pem_pair() is None
    source.get_s_v_i_d.side_effect = RuntimeError("SVID unavailable")
    assert manager.get_svid_pem_pair() is None


def test_svid_manager_trust_bundle_variants_and_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = SVIDManager(spiffe_id="spiffe://example.test/ns/default/sa/app")
    assert manager.get_trust_bundle_pem() is None

    source = MagicMock()
    source.get_bundle_for_trust_domain.return_value = SimpleNamespace(
        x509_certs_bytes=b"CA"
    )
    manager._source = source
    fake_spiffe_id = MagicMock()
    fake_spiffe_id.parse.return_value.trust_domain = "example.test"
    monkeypatch.setattr(spiffe, "SpiffeId", fake_spiffe_id)
    assert manager.get_trust_bundle_pem() == b"CA"
    fake_spiffe_id.parse.side_effect = ValueError("invalid id")
    assert manager.get_trust_bundle_pem() is None

    monkeypatch.setattr(spiffe, "SpiffeId", None)
    source.get_bundle_for_trust_domain.return_value = SimpleNamespace(
        x509_certs_bytes=b"CA-FALLBACK"
    )
    assert manager.get_trust_bundle_pem() == b"CA-FALLBACK"
    manager.spiffe_id_str = "invalid-id"
    assert manager.get_trust_bundle_pem() == b"CA-FALLBACK"
    source.get_bundle_for_trust_domain.side_effect = OSError("bundle unavailable")
    assert manager.get_trust_bundle_pem() is None

    source.get_bundle_for_trust_domain.side_effect = None
    source.get_bundle_for_trust_domain.return_value = SimpleNamespace(
        x509_certs_bytes="not-bytes"
    )
    assert manager.get_trust_bundle_pem() is None


def test_sni_reload_handles_no_change_context_swap_and_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = SVIDManager()
    pair = (b"CERT", b"KEY")
    manager._cached_pair = pair
    monkeypatch.setattr(
        ssl.SSLContext, "load_cert_chain", lambda *_args, **_kwargs: None
    )
    context = create_spiffe_server_ssl_context(manager)

    # No pair change is a no-op; a changed pair swaps the SSL context.
    ssl_obj = SimpleNamespace(context=context)
    manager._cached_pair = (b"CERT-2", b"KEY-2")
    fresh_context = MagicMock()
    fresh_context.verify_mode = ssl.CERT_REQUIRED
    manager.get_server_ssl_context = MagicMock(return_value=fresh_context)
    context.verify_mode = ssl.CERT_NONE
    context.sni_callback(ssl_obj, "example.test", context)
    assert ssl_obj.context is fresh_context
    assert fresh_context.verify_mode == ssl.CERT_NONE

    manager.get_server_ssl_context.side_effect = RuntimeError("reload failed")
    context.sni_callback(ssl_obj, "example.test", context)
    context.sni_callback(None, "example.test", context)


def test_ssl_context_builders_without_pair_and_client_with_pair(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = SVIDManager()
    server = create_spiffe_server_ssl_context(manager)
    client = create_spiffe_client_ssl_context(manager)
    assert server.verify_mode == ssl.CERT_REQUIRED
    assert client.verify_mode == ssl.CERT_REQUIRED


@pytest.mark.asyncio
async def test_spiffe_middleware_pass_through_and_peer_certificate_variants() -> None:
    calls: list[dict[str, object]] = []

    async def app(scope, _receive, _send):
        calls.append(scope)

    middleware = SPIFFEAuthMiddleware(
        app, ["spiffe://trusted"], protected_prefixes=("/api",)
    )
    await middleware(_scope(path="/public"), None, None)
    await middleware({**_scope(), "type": "lifespan"}, None, None)
    assert len(calls) == 2

    trusted_transport = MagicMock()
    trusted_transport.get_extra_info.return_value = {
        "subjectAltName": [("URI", "spiffe://trusted")]
    }
    trusted_scope = _scope(transport=trusted_transport)
    sent: list[dict[str, object]] = []
    await middleware(trusted_scope, None, sent.append)
    assert trusted_scope["state"]["spiffe_id"] == "spiffe://trusted"
    assert len(calls) == 3

    ssl_obj = MagicMock()
    ssl_obj.getpeercert.return_value = {
        "subjectAltName": [("DNS", "not-spiffe"), ("URI", "spiffe://trusted")]
    }
    ssl_transport = MagicMock()
    ssl_transport.get_extra_info.side_effect = [None, ssl_obj]
    assert (
        middleware._extract_spiffe_id(_scope(transport=ssl_transport))
        == "spiffe://trusted"
    )

    invalid_transport = MagicMock()
    invalid_transport.get_extra_info.side_effect = RuntimeError("transport closed")
    assert middleware._extract_spiffe_id(_scope(transport=invalid_transport)) is None


@pytest.mark.asyncio
async def test_spiffe_middleware_rejects_missing_and_disabled_requests() -> None:
    async def app(_scope, _receive, _send):
        return None

    sent: list[dict[str, object]] = []
    protected = SPIFFEAuthMiddleware(
        app, ["spiffe://trusted"], protected_prefixes=("/api",)
    )

    async def send(message: dict[str, object]) -> None:
        sent.append(message)

    await protected(_scope(), None, send)
    assert sent[0]["status"] == 403

    disabled_sent: list[dict[str, object]] = []
    disabled = SPIFFEAuthMiddleware(app, ["spiffe://trusted"], enabled=False)
    await disabled(_scope(), None, disabled_sent.append)
    assert disabled_sent == []


def test_grpc_credentials_require_enabled_manager_and_bundle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    disabled = SVIDManager(enabled=False)
    assert get_spiffe_grpc_credentials(disabled) is None

    manager = SVIDManager(enabled=True)
    manager.get_active_svid = MagicMock(return_value=None)
    manager.get_trust_bundle_pem = MagicMock(return_value=b"CA")
    assert get_spiffe_grpc_credentials(manager) is None

    manager.get_active_svid.return_value = (b"CERT", b"KEY")
    credentials = object()
    monkeypatch.setattr(grpc, "ssl_channel_credentials", lambda **_kwargs: credentials)
    assert get_spiffe_grpc_credentials(manager) is credentials
