"""Verify the transport destination, TLS identity and one-origin DNS binding."""

from uuid import uuid4

import pytest
import requests

from app.services.webpush import _create_pinned_webpush_session


@pytest.mark.parametrize("address", ["93.184.216.34", "2606:4700:4700::1111"])
def test_webpush_connection_pool_targets_validated_ip_and_original_tls_name(address):
    endpoint = "https://push.example.test:8443/subscription"
    with _create_pinned_webpush_session(endpoint, (address, 8443)) as session:
        request = requests.Request("POST", endpoint).prepare()
        adapter = session.get_adapter(endpoint)
        pool = adapter.get_connection_with_tls_context(request, verify=True)
        assert pool.host == address
        assert pool.port == 8443
        assert pool.assert_hostname == "push.example.test"
        assert pool.conn_kw["server_hostname"] == "push.example.test"
        connection = pool._new_conn()
        assert connection.host == address
        assert connection.server_hostname == "push.example.test"
        assert connection.assert_hostname == "push.example.test"
        adapter.add_headers(request)
        assert request.headers["Host"] == "push.example.test:8443"


@pytest.mark.parametrize(
    "target",
    [
        "https://other.example.test/subscription",
        "https://push.example.test:8443/subscription",
        "http://push.example.test/subscription",
        pytest.param(
            f"https://user:{uuid4().hex}@push.example.test/subscription",
            id="userinfo",
        ),
    ],
)
def test_pinned_adapter_rejects_origin_changes(target):
    endpoint = "https://push.example.test/subscription"
    with _create_pinned_webpush_session(endpoint, ("93.184.216.34", 443)) as session:
        adapter = session.get_adapter(endpoint)
        request = requests.Request("POST", target).prepare()
        with pytest.raises(requests.exceptions.InvalidURL, match="pinned HTTPS origin"):
            adapter.get_connection_with_tls_context(request, verify=True)


def test_pinned_adapter_preserves_certificate_verification():
    endpoint = "https://push.example.test/subscription"
    with _create_pinned_webpush_session(endpoint, ("93.184.216.34", 443)) as session:
        adapter = session.get_adapter(endpoint)
        request = requests.Request("POST", endpoint).prepare()
        with pytest.raises(requests.exceptions.InvalidURL, match="TLS verification"):
            adapter.get_connection_with_tls_context(request, verify=False)
