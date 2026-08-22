"""Unit tests for app/utils/img.py.

Tests get_optimized_image_url() without hitting a real imgproxy server.
Uses monkeypatching to control settings values.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
from unittest.mock import patch

from app.utils.img import get_optimized_image_url

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Valid hex-encoded key/salt pair (32 bytes each)
_KEY_HEX = "0" * 64
_SALT_HEX = "1" * 64


def _settings_with_proxy(**overrides):
    """Return a namespace that mimics settings for imgproxy tests."""
    defaults = {
        "imgproxy_key": _KEY_HEX,
        "imgproxy_salt": _SALT_HEX,
        "imgproxy_base_url": "https://img.example.com",
    }
    defaults.update(overrides)

    class _Settings:
        pass

    for k, v in defaults.items():
        setattr(_Settings, k, v)
    return _Settings()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestGetOptimizedImageUrl:
    def test_returns_none_for_none_input(self) -> None:
        assert get_optimized_image_url(None) is None

    def test_returns_none_for_empty_string(self) -> None:
        assert get_optimized_image_url("") is None

    def test_returns_original_url_when_imgproxy_key_missing(self) -> None:
        with patch("app.utils.img.settings") as mock_settings:
            mock_settings.imgproxy_key = ""
            mock_settings.imgproxy_salt = _SALT_HEX
            url = "https://cdn.example.com/photo.jpg"
            assert get_optimized_image_url(url) == url

    def test_returns_original_url_when_imgproxy_salt_missing(self) -> None:
        with patch("app.utils.img.settings") as mock_settings:
            mock_settings.imgproxy_key = _KEY_HEX
            mock_settings.imgproxy_salt = ""
            url = "https://cdn.example.com/photo.jpg"
            assert get_optimized_image_url(url) == url

    def test_returns_signed_url_when_keys_configured(self) -> None:
        with patch("app.utils.img.settings", _settings_with_proxy()):
            result = get_optimized_image_url("https://cdn.example.com/photo.jpg")
        assert result is not None
        assert result.startswith("https://img.example.com/")

    def test_preserves_a_proxy_path_prefix_in_the_public_base_url(self) -> None:
        settings = _settings_with_proxy(
            imgproxy_base_url="https://app.example.com/imgproxy/"
        )

        with patch("app.utils.img.settings", settings):
            result = get_optimized_image_url("https://cdn.example.com/photo.jpg")

        assert result is not None
        assert result.startswith("https://app.example.com/imgproxy/")

    def test_strips_all_trailing_slashes_from_proxy_base_url(self) -> None:
        settings = _settings_with_proxy(imgproxy_base_url="https://img.example.com///")

        with patch("app.utils.img.settings", settings):
            result = get_optimized_image_url("https://cdn.example.com/photo.jpg")

        assert result is not None
        assert result.startswith("https://img.example.com/")
        assert not result.startswith("https://img.example.com//")

    def test_signed_url_contains_processing_options(self) -> None:
        with patch("app.utils.img.settings", _settings_with_proxy()):
            result = get_optimized_image_url(
                "https://cdn.example.com/photo.jpg", width=200, height=150
            )
        assert result is not None
        assert "/rs:fit:200:150:" in result

    def test_default_extension_is_avif(self) -> None:
        with patch("app.utils.img.settings", _settings_with_proxy()):
            result = get_optimized_image_url("https://cdn.example.com/photo.jpg")
        assert result is not None
        assert result.endswith(".avif")

    def test_custom_extension(self) -> None:
        with patch("app.utils.img.settings", _settings_with_proxy()):
            result = get_optimized_image_url(
                "https://cdn.example.com/photo.jpg", extension="webp"
            )
        assert result is not None
        assert result.endswith(".webp")

    def test_no_extension_when_none(self) -> None:
        with patch("app.utils.img.settings", _settings_with_proxy()):
            result = get_optimized_image_url(
                "https://cdn.example.com/photo.jpg", extension=None
            )
        assert result is not None
        # No .avif / .webp / .jpg / .png suffix on the encoded URL part
        assert not result.endswith(".avif")

    def test_local_path_prefixed_with_backend_url(self) -> None:
        with patch("app.utils.img.settings", _settings_with_proxy()):
            result = get_optimized_image_url("/media/photo.jpg")
        assert result is not None
        # The source URL in the path must encode http://backend:8000/media/photo.jpg
        full_source = "http://backend:8000/media/photo.jpg"
        encoded = base64.urlsafe_b64encode(full_source.encode()).rstrip(b"=").decode()
        assert encoded in result

    def test_signature_is_valid_hmac_sha256(self) -> None:
        """Verify the embedded signature is a real HMAC-SHA256 of salt+path."""
        with patch("app.utils.img.settings", _settings_with_proxy()):
            result = get_optimized_image_url(
                "https://cdn.example.com/img.jpg", extension="jpg"
            )

        assert result is not None
        # Strip base URL
        path_with_sig = result[len("https://img.example.com/") :]
        sig_b64, *path_parts = path_with_sig.split("/")
        path = "/" + "/".join(path_parts)

        key = bytes.fromhex(_KEY_HEX)
        salt = bytes.fromhex(_SALT_HEX)
        msg = salt + path.encode()
        expected_sig = hmac.new(key, msg, hashlib.sha256).digest()
        expected_b64 = base64.urlsafe_b64encode(expected_sig).rstrip(b"=").decode()
        assert sig_b64 == expected_b64

    def test_enlarge_flag_included_in_path(self) -> None:
        with patch("app.utils.img.settings", _settings_with_proxy()):
            result = get_optimized_image_url(
                "https://cdn.example.com/photo.jpg", enlarge=True
            )
        assert result is not None
        # enlarge=True → the int(enlarge) part = 1 in the options string
        assert ":1:" in result

    def test_zero_dimensions_when_not_specified(self) -> None:
        with patch("app.utils.img.settings", _settings_with_proxy()):
            result = get_optimized_image_url("https://cdn.example.com/photo.jpg")
        assert result is not None
        # Width and height default to 0 when not specified → rs:fit:0:0
        assert "/rs:fit:0:0:" in result
