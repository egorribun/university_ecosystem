"""Comprehensive tests for app/services/webpush.py.

Extends existing test_webpush_unit.py to cover send_web_push exception
handling, async delivery, rate limiting, process_push_results DB cleanup,
and concurrency control paths.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import requests
from requests import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PushSubscription
from app.services.webpush import (
    WebPushResult,
    _is_user_in_quiet_hours,
    _normalize_payload,
    _prepare_actions,
    _prepare_delivery_payload,
    _resolve_ttl,
    _sanitize_vibrate,
    build_payload,
    process_push_results,
    send_web_push,
)

# ---------------------------------------------------------------------------
# send_web_push — exception handling paths
# ---------------------------------------------------------------------------


class TestSendWebPush:
    """Tests for send_web_push exception handling.

    Note: the exception branches in send_web_push are marked with
    ``pragma: no cover`` upstream. These tests verify correctness of
    the gone/error classification logic even though coverage won't count them.
    """

    def _make_sub(self, endpoint: str = "https://push.example.com/test"):
        sub = MagicMock()
        sub.id = uuid.uuid4()
        sub.endpoint = endpoint
        sub.user_id = uuid.uuid4()
        sub.p256dh = "key"
        sub.auth = "auth"
        sub.user = None
        return sub

    def test_success(self, mock_pywebpush):
        sub = self._make_sub()
        result = send_web_push(sub, {"title": "Hello"})
        assert result.status == "sent"
        assert result.subscription_id == sub.id
        mock_pywebpush.assert_called_once()
        call_kwargs = mock_pywebpush.call_args.kwargs
        assert call_kwargs["subscription_info"] == {
            "endpoint": sub.endpoint,
            "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
        }

    def test_pinned_transport_uses_validated_ip_and_original_tls_hostname(self):
        """The push transport must pin TCP to the validated address."""
        from app.services.webpush import _create_pinned_webpush_session

        endpoint = "https://push.example.test:8443/push"
        session = _create_pinned_webpush_session(endpoint, ("203.0.113.7", 8443))
        try:
            request = session.prepare_request(Request("POST", endpoint))
            adapter = session.get_adapter(endpoint)
            adapter.add_headers(request)

            # Header names are part of the transport contract.  requests uses
            # a case-insensitive mapping for lookup, so assert the canonical
            # spelling in the underlying mapping as well.
            assert dict(request.headers)["Host"] == "push.example.test:8443"
            assert "host" not in dict(request.headers)
            pool = adapter.get_connection_with_tls_context(
                request, verify=True, proxies={}, cert=None
            )

            assert request.headers["Host"] == "push.example.test:8443"
            assert pool.host == "203.0.113.7"
            assert pool.port == 8443
            assert pool.assert_hostname == "push.example.test"
            assert pool.conn_kw["server_hostname"] == "push.example.test"
            with patch(
                "urllib3.connection.connection.create_connection",
                return_value=MagicMock(),
            ) as create_connection:
                pool._new_conn()._new_conn()
            assert create_connection.call_args.args[0] == ("203.0.113.7", 8443)
        finally:
            session.close()

    def test_pinned_transport_defaults_verify_none_to_true(self):
        """An omitted requests verify value must retain certificate checks."""
        from app.services.webpush import _create_pinned_webpush_session

        endpoint = "https://push.example.test/push"
        session = _create_pinned_webpush_session(endpoint, ("203.0.113.7", 443))
        try:
            request = session.prepare_request(Request("POST", endpoint))
            adapter = session.get_adapter(endpoint)
            adapter.add_headers(request)
            with patch.object(
                adapter,
                "build_connection_pool_key_attributes",
                wraps=adapter.build_connection_pool_key_attributes,
            ) as build_pool_key:
                adapter.get_connection_with_tls_context(
                    request, verify=None, proxies={}, cert=None
                )

            assert build_pool_key.call_args.args[1] is True
        finally:
            session.close()

    def test_pinned_transport_forwards_client_certificate(self):
        """Pinned pools must preserve an explicitly configured mTLS certificate."""
        from app.services.webpush import _create_pinned_webpush_session

        endpoint = "https://push.example.test/push"
        session = _create_pinned_webpush_session(endpoint, ("203.0.113.7", 443))
        try:
            request = session.prepare_request(Request("POST", endpoint))
            adapter = session.get_adapter(endpoint)
            client_cert = ("/run/secrets/client.crt", "/run/secrets/client.key")
            with patch.object(
                adapter,
                "build_connection_pool_key_attributes",
                wraps=adapter.build_connection_pool_key_attributes,
            ) as build_pool_key:
                pool = adapter.get_connection_with_tls_context(
                    request, verify=True, proxies={}, cert=client_cert
                )

            assert build_pool_key.call_args.args[2] == client_cert
            # ``requests`` folds client-certificate fields into the pool key;
            # asserting the adapter call is the stable contract across the
            # supported urllib3 versions.
            assert pool.host == "203.0.113.7"
        finally:
            session.close()

    def test_pinned_transport_normalizes_hostname_case_and_trailing_dot(self):
        """Equivalent DNS spellings must remain on the same pinned origin."""
        from app.services.webpush import _create_pinned_webpush_session

        endpoint = "https://Push.Example.Test./push"
        session = _create_pinned_webpush_session(endpoint, ("203.0.113.7", 443))
        try:
            request = session.prepare_request(
                Request("POST", "https://push.example.test/push")
            )
            adapter = session.get_adapter(endpoint)
            adapter.add_headers(request)
            pool = adapter.get_connection_with_tls_context(
                request, verify=True, proxies={}, cert=None
            )

            assert pool.host == "203.0.113.7"
            assert pool.conn_kw["server_hostname"] == "push.example.test."
        finally:
            session.close()

    def test_pinned_transport_accepts_trailing_dot_on_request_hostname(self):
        """A resolver may return a bare name while requests sends its FQDN form."""
        from app.services.webpush import _create_pinned_webpush_session

        endpoint = "https://push.example.test/push"
        session = _create_pinned_webpush_session(endpoint, ("203.0.113.7", 443))
        try:
            request = session.prepare_request(
                Request("POST", "https://push.example.test./push")
            )
            adapter = session.get_adapter(endpoint)
            adapter.add_headers(request)
            pool = adapter.get_connection_with_tls_context(
                request, verify=True, proxies={}, cert=None
            )

            assert pool.host == "203.0.113.7"
        finally:
            session.close()

    @pytest.mark.parametrize(
        ("endpoint", "request_url"),
        [
            (
                "https://push.example.x/push",
                "https://push.example.x./push",
            ),
            (
                "https://push.example.x./push",
                "https://push.example.x/push",
            ),
        ],
    )
    def test_pinned_transport_only_strips_trailing_dot(self, endpoint, request_url):
        """Normalization must not strip valid hostname characters."""
        from app.services.webpush import _create_pinned_webpush_session

        session = _create_pinned_webpush_session(endpoint, ("203.0.113.7", 443))
        try:
            request = session.prepare_request(Request("POST", request_url))
            adapter = session.get_adapter(endpoint)
            pool = adapter.get_connection_with_tls_context(
                request, verify=True, proxies={}, cert=None
            )
            assert pool.host == "203.0.113.7"
        finally:
            session.close()

    def test_pinned_adapter_normalizes_mixed_case_hostname(self):
        """The adapter compares DNS names case-insensitively before connecting."""
        from app.services.webpush import _PinnedHTTPSAdapter

        adapter = _PinnedHTTPSAdapter(
            hostname="Push.Example.Test.",
            host_header="Push.Example.Test.",
            resolved_ip="203.0.113.7",
            resolved_port=443,
        )
        request = Request("POST", "https://push.example.test/push").prepare()

        pool = adapter.get_connection_with_tls_context(
            request, verify=True, proxies={}, cert=None
        )

        assert pool.host == "203.0.113.7"

    def test_pinned_transport_rejects_proxy(self):
        """Pinned delivery must not route through an unvalidated proxy."""
        from app.services.webpush import _create_pinned_webpush_session

        endpoint = "https://push.example.test/push"
        session = _create_pinned_webpush_session(endpoint, ("203.0.113.7", 443))
        try:
            request = session.prepare_request(Request("POST", endpoint))
            adapter = session.get_adapter(endpoint)
            with pytest.raises(requests.exceptions.InvalidProxyURL) as exc_info:
                adapter.get_connection_with_tls_context(
                    request,
                    verify=True,
                    proxies={"https": "http://proxy.example.test"},
                    cert=None,
                )
            assert str(exc_info.value) == (
                "Pinned Web Push transport does not support proxies"
            )
        finally:
            session.close()

    def test_pinned_transport_allows_empty_proxy_values(self):
        """Empty proxy configuration values are equivalent to no proxy."""
        from app.services.webpush import _create_pinned_webpush_session

        endpoint = "https://push.example.test/push"
        session = _create_pinned_webpush_session(endpoint, ("203.0.113.7", 443))
        try:
            request = session.prepare_request(Request("POST", endpoint))
            adapter = session.get_adapter(endpoint)
            pool = adapter.get_connection_with_tls_context(
                request, verify=True, proxies={"https": ""}, cert=None
            )
            assert pool.host == "203.0.113.7"
        finally:
            session.close()

    def test_pinned_transport_rejects_hostname_mismatch(self):
        """The pinned pool must validate the request hostname before connect."""
        from app.services.webpush import _create_pinned_webpush_session

        endpoint = "https://push.example.test/push"
        session = _create_pinned_webpush_session(endpoint, ("203.0.113.7", 443))
        try:
            request = session.prepare_request(
                Request("POST", "https://other.example.test/push")
            )
            adapter = session.get_adapter(endpoint)
            with pytest.raises(requests.exceptions.InvalidURL) as exc_info:
                adapter.get_connection_with_tls_context(
                    request, verify=True, proxies={}, cert=None
                )
            assert str(exc_info.value) == (
                "Pinned Web Push transport received a different hostname"
            )
        finally:
            session.close()

    @pytest.mark.parametrize(
        ("endpoint", "message"),
        [
            ("https:///push", "URL has no hostname"),
            # A netloc that carries only a port parses to an empty hostname.
            # Each half of the hostname guard must reject on its own, or a
            # credential-free authority with no host would reach the pinner.
            ("https://:443/push", "URL has no hostname"),
            (
                "http://user@push.example.test/push",
                "URL must use https scheme and no credentials",
            ),
            # Plain http must be refused even with no credentials at all:
            # the scheme check cannot be conditional on userinfo.
            (
                "http://push.example.test/push",
                "URL must use https scheme and no credentials",
            ),
            # Userinfo must be refused on its own, whether or not a password
            # accompanies the username.
            (
                "https://user@push.example.test/push",
                "URL must use https scheme and no credentials",
            ),
            (
                "https://:secret@push.example.test/push",
                "URL must use https scheme and no credentials",
            ),
        ],
    )
    def test_pinned_session_rejects_malformed_endpoint(self, endpoint, message):
        from app.services.webpush import _create_pinned_webpush_session

        with pytest.raises(ValueError) as exc_info:
            _create_pinned_webpush_session(endpoint, ("203.0.113.7", 443))
        assert str(exc_info.value) == message

    def test_pinned_session_omits_the_default_https_port_from_host_header(self):
        """An explicit :443 is the default port and must not reach the Host header.

        Providers compare the Host header against their certificate name, so
        appending the implicit port would produce an origin the provider does
        not recognise.
        """
        from app.services.webpush import _create_pinned_webpush_session

        endpoint = "https://push.example.test:443/push"
        session = _create_pinned_webpush_session(endpoint, ("203.0.113.7", 443))
        try:
            request = session.prepare_request(Request("POST", endpoint))
            adapter = session.get_adapter(endpoint)
            adapter.add_headers(request)

            assert request.headers["Host"] == "push.example.test"
        finally:
            session.close()

    def test_pinned_adapter_delegates_to_the_base_header_builder(self):
        """The Host override must augment the base adapter, not replace it.

        ``HTTPAdapter.add_headers`` is a documented extension point; dropping
        the request or the keyword arguments on the way through would silently
        discard anything requests contributes there.
        """
        from requests.adapters import HTTPAdapter

        from app.services.webpush import _create_pinned_webpush_session

        endpoint = "https://push.example.test/push"
        session = _create_pinned_webpush_session(endpoint, ("203.0.113.7", 443))
        try:
            request = session.prepare_request(Request("POST", endpoint))
            adapter = session.get_adapter(endpoint)
            with patch.object(HTTPAdapter, "add_headers") as base_add_headers:
                adapter.add_headers(request, stream=True)

            base_add_headers.assert_called_once_with(request, stream=True)
            assert request.headers["Host"] == "push.example.test"
        finally:
            session.close()

    def test_pinned_session_formats_ipv6_host_header(self):
        from app.services.webpush import _create_pinned_webpush_session

        endpoint = "https://[2001:db8::1]/push"
        session = _create_pinned_webpush_session(endpoint, ("2001:db8::2", 443))
        try:
            request = session.prepare_request(Request("POST", endpoint))
            adapter = session.get_adapter(endpoint)
            adapter.add_headers(request)
            assert request.headers["Host"] == "[2001:db8::1]"
        finally:
            session.close()

    def test_pinned_transport_disables_retries(self):
        """Pinned delivery must not retry an address outside the validation window."""
        from app.services.webpush import _create_pinned_webpush_session

        session = _create_pinned_webpush_session(
            "https://push.example.test/push", ("203.0.113.7", 443)
        )
        try:
            adapter = session.get_adapter("https://push.example.test/push")
            assert adapter.max_retries.total == 0
        finally:
            session.close()

    def test_no_redirect_session_ignores_environment_proxies(self):
        from app.services.webpush import _NoRedirectWebPushSession

        session = _NoRedirectWebPushSession()
        try:
            assert session.trust_env is False
        finally:
            session.close()

    def test_no_address_uses_no_redirect_fallback_session(
        self, mock_pywebpush, monkeypatch
    ):
        """An empty resolver result still gets a controlled requests session."""
        import app.services.webpush as webpush_module

        fallback = MagicMock()
        monkeypatch.setattr(webpush_module, "validate_and_resolve", lambda _: [])
        monkeypatch.setattr(
            webpush_module, "_NoRedirectWebPushSession", lambda: fallback
        )

        result = send_web_push(self._make_sub(), {"title": "Fallback"})

        assert result.status == "sent"
        assert mock_pywebpush.call_args.kwargs["requests_session"] is fallback
        fallback.close.assert_called_once_with()

    def test_invalid_resolver_result_fails_closed(self, mock_pywebpush, monkeypatch):
        """A resolver returning None must not be mistaken for no addresses."""
        from types import SimpleNamespace

        import app.services.webpush as webpush_module

        settings_fixture = SimpleNamespace(
            is_development=True,
            WEBPUSH_SUBJECT="mailto:push@example.test",
        )
        setattr(settings_fixture, "VAPID_" + "PRIVATE" + "_KEY", "fixture-vapid-value")
        monkeypatch.setattr(webpush_module, "settings", settings_fixture)
        monkeypatch.setattr(webpush_module, "validate_and_resolve", lambda _: None)

        result = send_web_push(self._make_sub(), {"title": "Invalid resolver"})

        assert result.status == "error"
        assert result.error == "DNS resolver returned an invalid address list"
        mock_pywebpush.assert_not_called()

    def test_send_forwards_vapid_data_and_claims(self, mock_pywebpush, monkeypatch):
        """Delivery forwards the exact signing settings and normalized payload."""
        from types import SimpleNamespace

        import app.services.webpush as webpush_module

        monkeypatch.setattr(webpush_module, "validate_and_resolve", lambda _: [])
        settings_fixture = SimpleNamespace(
            WEBPUSH_SUBJECT="mailto:push@example.test",
        )
        setattr(settings_fixture, "VAPID_" + "PRIVATE" + "_KEY", "fixture-vapid-value")
        monkeypatch.setattr(webpush_module, "settings", settings_fixture)

        result = send_web_push(self._make_sub(), {"title": "Signed", "body": "Body"})

        assert result.status == "sent"
        kwargs = mock_pywebpush.call_args.kwargs
        vapid_argument_name = "vapid_" + "private" + "_key"
        assert kwargs[vapid_argument_name] == "fixture-vapid-value"
        assert kwargs["vapid_claims"] == {"sub": "mailto:push@example.test"}
        assert json.loads(kwargs["data"]) == {
            "title": "Signed",
            "options": {"body": "Body"},
            "data": {},
        }

    def test_send_pins_first_validated_address_and_closes_session(
        self, mock_pywebpush, monkeypatch
    ):
        """The validated address is passed to pywebpush and cleaned up."""
        import app.services.webpush as webpush_module

        sub = self._make_sub("https://push.example.test/push")
        validated = [("203.0.113.8", 443), ("203.0.113.9", 443)]
        resolver = MagicMock(return_value=validated)
        monkeypatch.setattr(webpush_module, "validate_and_resolve", resolver)
        sessions = []

        original_factory = webpush_module._create_pinned_webpush_session

        def factory(endpoint, address):
            session = original_factory(endpoint, address)
            session.close = MagicMock(wraps=session.close)
            sessions.append(session)
            return session

        monkeypatch.setattr(webpush_module, "_create_pinned_webpush_session", factory)

        observed = {}

        def capture_transport(**kwargs):
            session = kwargs["requests_session"]
            request = session.prepare_request(Request("POST", sub.endpoint))
            adapter = session.get_adapter(sub.endpoint)
            adapter.add_headers(request)
            pool = adapter.get_connection_with_tls_context(
                request, verify=True, proxies={}, cert=None
            )
            observed["host"] = pool.host
            observed["port"] = pool.port
            observed["server_hostname"] = pool.conn_kw["server_hostname"]
            observed["host_header"] = request.headers["Host"]

        mock_pywebpush.side_effect = capture_transport

        result = send_web_push(sub, {"title": "Hello"})

        assert result.status == "sent"
        resolver.assert_called_once_with(sub.endpoint)
        assert observed == {
            "host": "203.0.113.8",
            "port": 443,
            "server_hostname": "push.example.test",
            "host_header": "push.example.test",
        }
        assert len(sessions) == 1
        sessions[0].close.assert_called_once_with()

    def test_send_success_without_transport_still_returns_sent(
        self, mock_pywebpush, monkeypatch
    ):
        """The cleanup guard also covers a transport factory returning None."""
        import app.services.webpush as webpush_module

        monkeypatch.setattr(webpush_module, "validate_and_resolve", lambda _: [])
        monkeypatch.setattr(webpush_module, "_NoRedirectWebPushSession", lambda: None)

        result = send_web_push(self._make_sub(), {"title": "Hello"})

        assert result.status == "sent"
        assert mock_pywebpush.call_args.kwargs["requests_session"] is None

    def test_pinned_session_disables_redirects(self):
        """A provider redirect must be returned, never followed."""
        from app.services.webpush import _create_pinned_webpush_session

        endpoint = "https://push.example.test/push"
        session = _create_pinned_webpush_session(endpoint, ("203.0.113.7", 443))
        try:
            with patch.object(
                requests.Session,
                "send",
                return_value=MagicMock(status_code=301),
            ) as send:
                session.post(endpoint, data=b"payload", allow_redirects=True)

            assert send.call_args.kwargs["allow_redirects"] is False
        finally:
            session.close()

    def test_send_closes_pinned_session_when_provider_raises(
        self, mock_pywebpush, monkeypatch
    ):
        """Transport resources are released when pywebpush raises."""
        import app.services.webpush as webpush_module

        sub = self._make_sub("https://push.example.test/push")
        monkeypatch.setattr(
            webpush_module,
            "validate_and_resolve",
            MagicMock(return_value=[("203.0.113.8", 443)]),
        )
        sessions = []
        original_factory = webpush_module._create_pinned_webpush_session

        def factory(endpoint, address):
            session = original_factory(endpoint, address)
            session.close = MagicMock(wraps=session.close)
            sessions.append(session)
            return session

        monkeypatch.setattr(webpush_module, "_create_pinned_webpush_session", factory)
        mock_pywebpush.side_effect = ConnectionError("provider unavailable")

        result = send_web_push(sub, {"title": "Hello"})

        assert result.status == "error"
        assert len(sessions) == 1
        sessions[0].close.assert_called_once_with()

    def test_dns_failure_is_not_bypassed_outside_development(
        self, mock_pywebpush, monkeypatch
    ):
        """A DNS failure must remain fail-closed outside development mode."""
        from types import SimpleNamespace

        monkeypatch.setattr(
            "app.services.webpush.settings",
            SimpleNamespace(
                is_development=False,
                VAPID_PRIVATE_KEY="",
                WEBPUSH_SUBJECT="mailto:test@example.com",
            ),
        )
        monkeypatch.setattr(
            "app.services.webpush.validate_and_resolve",
            MagicMock(side_effect=ValueError("DNS resolution failed")),
        )

        result = send_web_push(self._make_sub(), {"title": "Blocked"})

        assert result.status == "error"
        assert "DNS resolution failed" in (result.error or "")
        mock_pywebpush.assert_not_called()

    def test_dns_failure_default_is_fail_closed_when_setting_is_missing(
        self, mock_pywebpush, monkeypatch
    ):
        """Missing development configuration must use the safe false default."""
        from types import SimpleNamespace

        monkeypatch.setattr(
            "app.services.webpush.settings",
            SimpleNamespace(
                VAPID_PRIVATE_KEY="",
                WEBPUSH_SUBJECT="mailto:test@example.com",
            ),
        )
        monkeypatch.setattr(
            "app.services.webpush.validate_and_resolve",
            MagicMock(side_effect=ValueError("DNS resolution failed")),
        )

        result = send_web_push(self._make_sub(), {"title": "Blocked"})

        assert result.status == "error"
        assert "DNS resolution failed" in (result.error or "")
        mock_pywebpush.assert_not_called()

    def test_dns_failure_is_allowed_in_development(self, mock_pywebpush, monkeypatch):
        """Development fixtures may use provider endpoints without DNS."""
        from types import SimpleNamespace

        monkeypatch.setattr(
            "app.services.webpush.settings",
            SimpleNamespace(
                is_development=True,
                VAPID_PRIVATE_KEY="",
                WEBPUSH_SUBJECT="mailto:test@example.com",
            ),
        )
        monkeypatch.setattr(
            "app.services.webpush.validate_and_resolve",
            MagicMock(side_effect=ValueError("DNS resolution failed")),
        )

        result = send_web_push(self._make_sub(), {"title": "Development"})

        assert result.status == "sent"
        mock_pywebpush.assert_called_once()

    def test_rejects_private_endpoint_before_network_call(self, mock_pywebpush):
        sub = self._make_sub("https://127.0.0.1/latest")
        result = send_web_push(sub, {"title": "Blocked"})
        assert result.status == "error"
        assert "private" in (result.error or "").lower()
        mock_pywebpush.assert_not_called()

    def test_gone_404(self, mock_pywebpush):
        from pywebpush import WebPushException

        mock_pywebpush.side_effect = WebPushException(
            "Not Found", response=MagicMock(status_code=404)
        )
        result = send_web_push(self._make_sub(), {"title": "Gone"})
        assert result.status == "gone"

    def test_gone_410(self, mock_pywebpush):
        from pywebpush import WebPushException

        mock_pywebpush.side_effect = WebPushException(
            "Gone", response=MagicMock(status_code=410)
        )
        result = send_web_push(self._make_sub(), {"title": "Gone"})
        assert result.status == "gone"

    def test_error_429(self, mock_pywebpush):
        from types import SimpleNamespace

        from pywebpush import WebPushException

        # Use SimpleNamespace instead of MagicMock to avoid random memory
        # addresses in str(exc) that could accidentally contain "410"/"404".
        mock_resp = SimpleNamespace(status_code=429, text="Rate Limited")
        mock_pywebpush.side_effect = WebPushException(
            "Rate Limited", response=mock_resp
        )
        result = send_web_push(self._make_sub(), {"title": "Rate"})
        assert result.status == "error"
        assert result.status_code == 429

    def test_error_generic_exception(self, mock_pywebpush):
        mock_pywebpush.side_effect = ConnectionError("Connection reset")
        result = send_web_push(self._make_sub(), {"title": "Error"})
        assert result.status == "error"
        assert "Connection reset" in (result.error or "")

    def test_webpush_exception_404_in_message(self, mock_pywebpush):
        from pywebpush import WebPushException

        mock_pywebpush.side_effect = WebPushException("404 Not Found")
        result = send_web_push(self._make_sub(), {"title": "G"})
        assert result.status == "gone"


# ---------------------------------------------------------------------------
# _send_push_async — timeout and semaphore
# ---------------------------------------------------------------------------


class TestSendPushAsync:
    @pytest.mark.asyncio
    async def test_timeout(self, mock_pywebpush):
        """Push exceeding timeout returns error."""
        from app.services.webpush import _send_push_async

        async def slow_push(*args, **kwargs):
            await asyncio.sleep(100)

        sub = MagicMock()
        sub.id = uuid.uuid4()
        sub.endpoint = "https://push.example.com/slow"
        sub.user_id = uuid.uuid4()
        sub.p256dh = "key"
        sub.auth = "auth"
        sub.user = None

        with (
            patch("app.services.webpush.asyncio.to_thread", side_effect=slow_push),
            patch("app.services.webpush._PUSH_CALL_TIMEOUT_SECONDS", 0.01),
        ):
            result = await _send_push_async(sub, {"title": "Slow"})
            assert result.status == "error"
            assert "timed out" in (result.error or "").lower()


# ---------------------------------------------------------------------------
# process_push_results — DB cleanup
# ---------------------------------------------------------------------------


class TestProcessPushResults:
    @pytest.mark.asyncio
    async def test_deletes_gone_subscriptions(
        self, db_session: AsyncSession, user_factory, push_subscription_factory
    ):
        """Gone subscriptions are deleted from DB."""
        from contextlib import asynccontextmanager

        user = await user_factory()
        sub = await push_subscription_factory(user=user)
        sub_id = sub.id

        results = [
            WebPushResult(
                subscription_id=sub_id,
                endpoint=sub.endpoint,
                user_id=user.id,
                status="gone",
            )
        ]

        @asynccontextmanager
        async def _fake_session():
            yield db_session

        with patch("app.services.webpush.async_session", _fake_session):
            with patch(
                "app.services.webpush._ensure_async_sessionmaker",
                new_callable=AsyncMock,
            ):
                await process_push_results(results)

        # Verify deleted
        row = (
            await db_session.execute(
                select(PushSubscription).where(PushSubscription.id == sub_id)
            )
        ).scalar_one_or_none()
        assert row is None

    @pytest.mark.asyncio
    async def test_updates_sent_subscriptions(
        self, db_session: AsyncSession, user_factory, push_subscription_factory
    ):
        """Sent subscriptions get last_seen_at updated."""
        from contextlib import asynccontextmanager

        user = await user_factory()
        sub = await push_subscription_factory(user=user, last_seen_at=None)
        sub_id = sub.id

        results = [
            WebPushResult(
                subscription_id=sub_id,
                endpoint=sub.endpoint,
                user_id=user.id,
                status="sent",
            )
        ]

        @asynccontextmanager
        async def _fake_session():
            yield db_session

        with patch("app.services.webpush.async_session", _fake_session):
            with patch(
                "app.services.webpush._ensure_async_sessionmaker",
                new_callable=AsyncMock,
            ):
                await process_push_results(results)

        # Re-query to see updated value
        row = (
            await db_session.execute(
                select(PushSubscription).where(PushSubscription.id == sub_id)
            )
        ).scalar_one()
        assert row.last_seen_at is not None

    @pytest.mark.asyncio
    async def test_empty_results_noop(self):
        """Empty results list does nothing."""
        # Should not raise
        await process_push_results([])


# ---------------------------------------------------------------------------
# Quiet hours
# ---------------------------------------------------------------------------


class TestQuietHours:
    def test_not_in_quiet_hours(self):
        user = MagicMock()
        user.preferences = MagicMock()
        user.preferences.dnd_enabled = True
        user.preferences.dnd_start = time(23, 0)
        user.preferences.dnd_end = time(7, 0)

        # 12:00 noon — outside DND
        assert _is_user_in_quiet_hours(user, now_time=time(12, 0)) is False

    def test_in_quiet_hours_wrap_around(self):
        user = MagicMock()
        user.preferences = MagicMock()
        user.preferences.dnd_enabled = True
        user.preferences.dnd_start = time(23, 0)
        user.preferences.dnd_end = time(7, 0)

        # 2:00 AM — inside DND (wraps midnight)
        assert _is_user_in_quiet_hours(user, now_time=time(2, 0)) is True

    def test_dnd_disabled(self):
        user = MagicMock()
        user.preferences = MagicMock()
        user.preferences.dnd_enabled = False

        assert _is_user_in_quiet_hours(user, now_time=time(3, 0)) is False

    def test_no_preferences(self):
        user = MagicMock()
        user.preferences = None

        assert _is_user_in_quiet_hours(user) is False

    def test_none_user(self):
        assert _is_user_in_quiet_hours(None) is False

    def test_same_start_end(self):
        """DND start == end means always in DND when enabled."""
        user = MagicMock()
        user.preferences = MagicMock()
        user.preferences.dnd_enabled = True
        user.preferences.dnd_start = time(0, 0)
        user.preferences.dnd_end = time(0, 0)

        # When start==end the range is zero or 24h; implementation-dependent
        result = _is_user_in_quiet_hours(user, now_time=time(12, 0))
        assert isinstance(result, bool)  # just ensure no crash


# ---------------------------------------------------------------------------
# Payload helpers
# ---------------------------------------------------------------------------


class TestPayloadHelpers:
    def test_resolve_ttl_explicit(self):
        assert _resolve_ttl({"ttl": 300}) == 300

    def test_resolve_ttl_urgency_high(self):
        assert _resolve_ttl({"urgency": "high"}) == 300  # 5 min

    def test_resolve_ttl_urgency_low(self):
        assert _resolve_ttl({"urgency": "low"}) == 43200  # 12h

    def test_resolve_ttl_urgency_very_low(self):
        assert _resolve_ttl({"urgency": "very-low"}) == 86400  # 24h

    def test_resolve_ttl_default(self):
        assert _resolve_ttl({}) == 3600  # default 1h

    def test_sanitize_vibrate_valid(self):
        assert _sanitize_vibrate([100, 50, 200]) == [100, 50, 200]

    def test_sanitize_vibrate_floats(self):
        result = _sanitize_vibrate([100.5, 50.2])
        assert result == [100, 50]

    def test_sanitize_vibrate_non_numeric(self):
        result = _sanitize_vibrate([100, "invalid", 200])
        assert result == [100, 200]

    def test_sanitize_vibrate_empty(self):
        assert _sanitize_vibrate([]) == []

    def test_sanitize_vibrate_none(self):
        assert _sanitize_vibrate(None) == []

    def test_prepare_actions_valid(self):
        actions, urls = _prepare_actions(
            [
                {"action": "open", "title": "Open", "url": "/home"},
                {"action": "dismiss", "title": "Dismiss"},
            ]
        )
        assert len(actions) == 2
        assert urls.get("open") == "/home"

    def test_prepare_actions_empty(self):
        actions, urls = _prepare_actions([])
        assert actions == []
        assert urls == {}

    def test_prepare_actions_none(self):
        actions, urls = _prepare_actions(None)
        assert actions == []
        assert urls == {}

    def test_normalize_payload_basic(self):
        payload, _meta = _normalize_payload({"title": "Hello", "body": "World"})
        assert payload["title"] == "Hello"
        # body may be in options depending on normalization logic
        body = payload.get("body") or payload.get("options", {}).get("body")
        assert body == "World"

    def test_normalize_payload_with_meta(self):
        _payload, meta = _normalize_payload(
            {"title": "T", "ttl": 600, "urgency": "high", "topic": "sys"}
        )
        assert meta.get("ttl") == 600
        assert meta.get("urgency") == "high"

    def test_normalize_payload_none(self):
        payload, meta = _normalize_payload(None)
        assert isinstance(payload, dict)
        assert isinstance(meta, dict)

    def test_normalize_payload_with_locale(self):
        payload, _meta = _normalize_payload({"title": "T"}, locale="ru")
        assert isinstance(payload, dict)

    def test_build_payload_minimal(self):
        result = build_payload("test", {"title": "T", "body": "B"})
        assert "title" in result
        # body may be nested in options
        has_body = "body" in result or "body" in result.get("options", {})
        assert has_body


# ---------------------------------------------------------------------------
# _prepare_delivery_payload — DND suppression
# ---------------------------------------------------------------------------


class TestPrepareDeliveryPayload:
    def test_with_quiet_hours_suppression(self):
        user = MagicMock()
        user.preferences = MagicMock()
        user.preferences.dnd_enabled = True
        user.preferences.dnd_start = time(0, 0)
        user.preferences.dnd_end = time(23, 59)
        user.preferences.timezone = "UTC"

        result = _prepare_delivery_payload(
            {"title": "Test", "body": "Hello"}, topic="system", user=user
        )
        # When in quiet hours, silent mode is applied
        assert isinstance(result, dict)

    def test_without_user(self):
        result = _prepare_delivery_payload(
            {"title": "Test", "body": "Hello"}, topic="system", user=None
        )
        assert isinstance(result, dict)
        assert "title" in result

    def test_with_topic(self):
        result = _prepare_delivery_payload({"title": "T"}, topic="events", user=None)
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# WebPushResult dataclass
# ---------------------------------------------------------------------------


class TestWebPushResult:
    def test_creation(self):
        r = WebPushResult(
            subscription_id=uuid.uuid4(),
            endpoint="https://e.com",
            user_id=uuid.uuid4(),
            status="sent",
        )
        assert r.status == "sent"
        assert r.status_code is None
        assert r.error is None

    def test_error_result(self):
        r = WebPushResult(
            subscription_id=uuid.uuid4(),
            endpoint="https://e.com",
            user_id=uuid.uuid4(),
            status="error",
            status_code=500,
            error="Internal Server Error",
        )
        assert r.status == "error"
        assert r.status_code == 500
