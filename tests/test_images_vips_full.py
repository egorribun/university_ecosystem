"""Full coverage tests for app/utils/images_vips.py.

Targets UNCOVERED branches not addressed by tests/test_images_vips.py:
  - optimize_image_vips with various exception types from pyvips
  - get_image_dimensions_vips exception propagation
  - webpsave_buffer returning memoryview / bytes-like buffer
  - autorot chained call verified explicitly
  - EXIF strip=True parameter verified
  - Module __all__ export check
  - VIPS_AVAILABLE is bool check
  - Format-agnostic output always returns image/webp
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers - build a fresh pyvips mock with required enums
# ---------------------------------------------------------------------------


def _make_mock_pyvips() -> MagicMock:
    """Create a fresh pyvips mock with required enums."""
    mock = MagicMock()
    mock.enums.Size.DOWN = "down"
    return mock


# ---------------------------------------------------------------------------
# Tests: VIPS_AVAILABLE=False paths
# ---------------------------------------------------------------------------


class TestVipsNotAvailable:
    """When VIPS_AVAILABLE is False, both functions raise RuntimeError."""

    def test_optimize_raises_runtime_error(self):
        import app.utils.images_vips as iv

        with patch("app.utils.images_vips.VIPS_AVAILABLE", False):
            with pytest.raises(RuntimeError, match="pyvips is not available"):
                iv.optimize_image_vips(b"data")

    def test_get_dimensions_raises_runtime_error(self):
        import app.utils.images_vips as iv

        with patch("app.utils.images_vips.VIPS_AVAILABLE", False):
            with pytest.raises(RuntimeError, match="pyvips is not available"):
                iv.get_image_dimensions_vips(b"data")


# ---------------------------------------------------------------------------
# Tests: optimize_image_vips with controlled pyvips mock
# ---------------------------------------------------------------------------


class TestOptimizeImageVipsWithPyvipsMocked:
    """Parameterised tests using a cleanly-controlled pyvips mock."""

    @pytest.fixture(autouse=True)
    def setup_pyvips_mock(self):
        self.mock_pyvips = _make_mock_pyvips()
        self.mock_image = MagicMock()
        self.mock_pyvips.Image.thumbnail_buffer.return_value = self.mock_image
        self.mock_image.autorot.return_value = self.mock_image
        self.mock_image.webpsave_buffer.return_value = b"webp-data"

        with patch("app.utils.images_vips.pyvips", self.mock_pyvips):
            with patch("app.utils.images_vips.VIPS_AVAILABLE", True):
                yield

    def test_default_parameters(self):
        """Default call uses max_width=1920, max_height=1920, quality=85."""
        import app.utils.images_vips as iv

        result, mime = iv.optimize_image_vips(b"raw-data")
        assert mime == "image/webp"
        assert result == b"webp-data"
        self.mock_pyvips.Image.thumbnail_buffer.assert_called_once_with(
            b"raw-data",
            1920,
            height=1920,
            size="down",
        )
        self.mock_image.webpsave_buffer.assert_called_once_with(
            Q=85, effort=4, strip=True
        )

    def test_custom_quality_and_dimensions(self):
        """Custom quality, width, height are forwarded to pyvips."""
        import app.utils.images_vips as iv

        iv.optimize_image_vips(b"raw", max_width=640, max_height=480, quality=60)

        self.mock_pyvips.Image.thumbnail_buffer.assert_called_once_with(
            b"raw", 640, height=480, size="down"
        )
        self.mock_image.webpsave_buffer.assert_called_once_with(
            Q=60, effort=4, strip=True
        )

    def test_autorot_is_called(self):
        """autorot() must be called to handle EXIF orientation."""
        import app.utils.images_vips as iv

        iv.optimize_image_vips(b"raw")
        self.mock_image.autorot.assert_called_once()

    def test_strip_exif_metadata_parameter(self):
        """webpsave_buffer must be called with strip=True to remove EXIF metadata."""
        import app.utils.images_vips as iv

        iv.optimize_image_vips(b"raw")
        call_kwargs = self.mock_image.webpsave_buffer.call_args
        assert call_kwargs.kwargs["strip"] is True

    def test_returns_bytes_from_memoryview(self):
        """If webpsave_buffer returns a memoryview, result is still bytes."""
        import app.utils.images_vips as iv

        self.mock_image.webpsave_buffer.return_value = memoryview(b"webp-mv")
        result, mime = iv.optimize_image_vips(b"raw")
        assert isinstance(result, bytes)
        assert result == b"webp-mv"
        assert mime == "image/webp"

    def test_output_mime_always_webp_for_any_input(self):
        """Regardless of input format label, output MIME is always image/webp."""
        import app.utils.images_vips as iv

        for input_data in [b"jpeg-data", b"png-data", b"avif-data", b"gif-data"]:
            self.mock_pyvips.Image.thumbnail_buffer.reset_mock()
            self.mock_image.webpsave_buffer.return_value = b"webp-out"
            _, mime = iv.optimize_image_vips(input_data)
            assert mime == "image/webp"

    def test_pyvips_generic_exception_becomes_value_error(self):
        """Any exception from pyvips is wrapped in ValueError."""
        import app.utils.images_vips as iv

        self.mock_pyvips.Image.thumbnail_buffer.side_effect = RuntimeError(
            "pyvips internal error"
        )
        with pytest.raises(ValueError, match="Failed to process image with pyvips"):
            iv.optimize_image_vips(b"bad-data")

    def test_pyvips_error_subclass_becomes_value_error(self):
        """A custom Exception subclass (simulating pyvips.Error) becomes ValueError."""
        import app.utils.images_vips as iv

        class FakeVipsError(Exception):
            pass

        self.mock_pyvips.Image.thumbnail_buffer.side_effect = FakeVipsError(
            "vips op failed"
        )
        with pytest.raises(ValueError, match="Failed to process image with pyvips"):
            iv.optimize_image_vips(b"data")

    def test_autorot_exception_becomes_value_error(self):
        """Exception from autorot() is caught and wrapped in ValueError."""
        import app.utils.images_vips as iv

        self.mock_image.autorot.side_effect = Exception("autorot failure")
        with pytest.raises(ValueError, match="Failed to process image with pyvips"):
            iv.optimize_image_vips(b"data")

    def test_webpsave_exception_becomes_value_error(self):
        """Exception from webpsave_buffer() is caught and wrapped in ValueError."""
        import app.utils.images_vips as iv

        self.mock_image.webpsave_buffer.side_effect = MemoryError("OOM")
        with pytest.raises(ValueError, match="Failed to process image with pyvips"):
            iv.optimize_image_vips(b"data")

    def test_value_error_chain_preserves_original_cause(self):
        """ValueError raised must chain from the original exception via __cause__."""
        import app.utils.images_vips as iv

        original = RuntimeError("root cause")
        self.mock_pyvips.Image.thumbnail_buffer.side_effect = original
        try:
            iv.optimize_image_vips(b"data")
            pytest.fail("Expected ValueError")
        except ValueError as exc:
            assert exc.__cause__ is original


# ---------------------------------------------------------------------------
# Tests: get_image_dimensions_vips with controlled pyvips mock
# ---------------------------------------------------------------------------


class TestGetImageDimensionsVips:
    """Tests for get_image_dimensions_vips."""

    @pytest.fixture(autouse=True)
    def setup_pyvips_mock(self):
        self.mock_pyvips = _make_mock_pyvips()
        self.mock_image = MagicMock()
        self.mock_image.width = 1280
        self.mock_image.height = 720
        self.mock_pyvips.Image.new_from_buffer.return_value = self.mock_image

        with patch("app.utils.images_vips.pyvips", self.mock_pyvips):
            with patch("app.utils.images_vips.VIPS_AVAILABLE", True):
                yield

    def test_returns_width_and_height(self):
        """Returns (width, height) tuple from the loaded image."""
        import app.utils.images_vips as iv

        w, h = iv.get_image_dimensions_vips(b"image-bytes")
        assert w == 1280
        assert h == 720

    def test_calls_new_from_buffer_with_empty_options(self):
        """new_from_buffer must be called with empty option string."""
        import app.utils.images_vips as iv

        iv.get_image_dimensions_vips(b"image-bytes")
        self.mock_pyvips.Image.new_from_buffer.assert_called_once_with(
            b"image-bytes", ""
        )

    def test_pyvips_error_propagates_uncaught(self):
        """Exceptions from new_from_buffer propagate (no try/except in that fn)."""
        import app.utils.images_vips as iv

        self.mock_pyvips.Image.new_from_buffer.side_effect = Exception("corrupt image")
        with pytest.raises(Exception, match="corrupt image"):
            iv.get_image_dimensions_vips(b"bad-data")

    def test_large_dimensions(self):
        """Returns correct large dimensions without overflow."""
        import app.utils.images_vips as iv

        self.mock_image.width = 16384
        self.mock_image.height = 16384
        w, h = iv.get_image_dimensions_vips(b"large-img")
        assert w == 16384
        assert h == 16384

    def test_tiny_image_dimensions(self):
        """Returns correct tiny dimensions (1x1)."""
        import app.utils.images_vips as iv

        self.mock_image.width = 1
        self.mock_image.height = 1
        w, h = iv.get_image_dimensions_vips(b"1x1-img")
        assert w == 1
        assert h == 1


# ---------------------------------------------------------------------------
# Tests: Module public API contract
# ---------------------------------------------------------------------------


class TestModulePublicApi:
    """Tests that the module public API is correctly exported."""

    def test_all_exports(self):
        """__all__ must contain the three expected symbols."""
        import app.utils.images_vips as iv

        assert "VIPS_AVAILABLE" in iv.__all__
        assert "optimize_image_vips" in iv.__all__
        assert "get_image_dimensions_vips" in iv.__all__

    def test_vips_available_is_bool(self):
        """VIPS_AVAILABLE must be a strict bool, not just truthy."""
        import app.utils.images_vips as iv

        assert isinstance(iv.VIPS_AVAILABLE, bool)

    def test_all_symbols_are_callable_or_bool(self):
        """All exported symbols must be accessible as module attributes."""
        import app.utils.images_vips as iv

        for name in iv.__all__:
            assert hasattr(iv, name), f"Missing exported symbol: {name}"
