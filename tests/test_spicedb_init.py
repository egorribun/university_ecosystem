from unittest.mock import patch

import pytest

from app.core.spicedb import SpiceDBClient


@pytest.mark.parametrize(
    "endpoint,expected_target,expected_ssl",
    [
        ("localhost:50051", "localhost:50051", False),
        ("http://localhost:50051", "localhost:50051", False),
        ("https://spicedb.example.com", "spicedb.example.com", True),
        ("spicedb.example.com:443", "spicedb.example.com:443", True),
        ("http://spicedb.example.com:443", "spicedb.example.com:443", True),
    ],
)
def test_init_logic(endpoint, expected_target, expected_ssl, monkeypatch):
    with patch("app.core.spicedb.settings") as mock_settings:
        mock_settings.spicedb_endpoint = endpoint
        mock_settings.spicedb_preshared_key = "test-token"

        if not expected_ssl:
            monkeypatch.setenv("SPICEDB_INSECURE", "true")
        else:
            monkeypatch.setenv("SPICEDB_INSECURE", "false")

        client_wrapper = SpiceDBClient()
        # Reset internal state
        client_wrapper.client = None

        with (
            patch("app.core.spicedb.Client", create=True) as mock_secure,
            patch("app.core.spicedb.InsecureClient", create=True) as mock_insecure,
            patch("grpcutil.bearer_token_credentials", create=True),
        ):
            client_wrapper.get_client()

            if expected_ssl:
                assert mock_secure.called, (
                    f"Expected Client to be called for {endpoint}"
                )
            else:
                assert mock_insecure.called, (
                    f"Expected InsecureClient to be called for {endpoint}"
                )
