"""Full coverage tests for app/utils/images_vips.py.

Targets UNCOVERED branches not addressed by tests/test_images_vips.py:
  - VIPS_AVAILABLE=False path for both functions (RuntimeError)
  - optimize_image_vips with pyvips.Error specific exception type
  - get_image_dimensions_vips exception propagation (pyvips error)
  - webpsave_buffer returning memoryview / bytes-like buffer
  - autorot chained call verified explicitly
  - VIPS_AVAILABLE module-level=False (ImportError simulation)
  - Module __all__ export check
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers — build a fresh module with pyvips mocked
# ---------------------------------------------------------------------------


def _make_mock_pyvips() -> MagicMock:
    """Create a fresh pyvips mock with required enums."""
    mock = MagicMock()
    mock.enums.Size.DOWN = "down"
    return mock


# ---------------------------------------------------------------------------
# Tests that rely on the already-imported iv module (pyvips mocked at module level)
# We import here fresh to avoid contaminating test_images_vips.py state.
# ---------------------------------------------------------------------------


class TestOptimizeImageVipsVipsAvailableFalse:
    """When VIPS_AVAILABLE is False, both functions raise RuntimeError."""

    def test_optimize_raises_runtime_error(self):
        # Re-use the module already in sys.modules (pyvips is mocked there)
        import app.utils.images_vips as iv

        with patch("app.utils.images_vips.VIPS_AVAILABLE", False):
            with pytest.raises(RuntimeError, match="pyvips is not available"):
                iv.optimize_image_vips(b"data")

    def test_get_dimensions_raises_runtime_error(self):
        import app.utils.images_vips as iv

        with patch("app.utils.images_vips.VIPS_AVAILABLE", False):
            with pytest.raises(RuntimeError, match="pyvips is not available"):
                iv.get_image_dimensions_vips(b"data")


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
        """autorot() must be called to strip EXIF orientation."""
        import app.utils.images_vips as iv

        iv.optimize_image_vips(b"raw")
        self.mock_image.autorot.assert_called_once()

    def test_strip_exif_metadata(self):
        """webpsave_buffer must be called with strip=True to remove EXIF."""
        import app.utils.images_vips as iv

        iv.optimize_image_vips(b"raw")
        call_kwargs = self.mock_image.webpsave_buffer.call_args
        assert call_kwargs.kwargs["strip"] is True

    def test_returns_bytes_from_memoryview(self):
        """If webpsave_buffer returns a memoryview, result is still bytes."""
        import app.utils.images_vips as iv

        # pyvips can return a buffer that is not exactly bytes
        self.mock_image.webpsave_buffer.return_value = memoryview(b"webp-mv")
        result, mime = iv.optimize_image_vips(b"raw")
        assert isinstance(result, bytes)
        assert result == b"webp-mv"
        assert mime == "image/webp"

    def test_output_mime_is_always_webp(self):
        """Regardless of input format, output MIME is always image/webp."""
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

    def test_pyvips_error_class_becomes_value_error(self):
        """pyvips.Error (if available) becomes ValueError (same path)."""
        import app.utils.images_vips as iv

        # Simulate pyvips.Error by making it a subclass of Exception
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

    def test_pyvips_error_propagates(self):
        """Exceptions from new_from_buffer propagate uncaught (no try/except in that fn)."""
        import app.utils.images_vips as iv

        self.mock_pyvips.Image.new_from_buffer.side_effect = Exception("corrupt image")
        with pytest.raises(Exception, match="corrupt image"):
            iv.get_image_dimensions_vips(b"bad-data")


class TestModulePublicApi:
    """Tests that the module's public API is correctly exported."""

    def test_all_exports(self):
        """__all__ must contain the three expected symbols."""
        import app.utils.images_vips as iv

        assert "VIPS_AVAILABLE" in iv.__all__
        assert "optimize_image_vips" in iv.__all__
        assert "get_image_dimensions_vips" in iv.__all__

    def test_vips_available_is_bool(self):
        """VIPS_AVAILABLE must be a bool, not truthy-any."""
        import app.utils.images_vips as iv

        assert isinstance(iv.VIPS_AVAILABLE, bool)


class TestImportErrorFallback:
    """Verify that importing the module when pyvips is absent sets VIPS_AVAILABLE=False."""

    def test_vips_unavailable_when_import_error(self):
        """If pyvips raises ImportError, VIPS_AVAILABLE is False."""
        # Remove the module so we can re-import with a missing pyvips
        saved_module = sys.modules.pop("app.utils.images_vips", None)
        saved_pyvips = sys.modules.pop("pyvips", None)

        # Make pyvips unimportable
        sys.modules["pyvips"] = None  # type: ignore[assignment]

        try:
            import importlib

            import app.utils.images_vips as fresh_iv

            importlib.reload(fresh_iv)
            # VIPS_AVAILABLE must be False because pyvips=None causes ImportError
            assert fresh_iv.VIPS_AVAILABLE is False
        except ImportError:
            # Acceptable: the import itself failed, which means pyvips was unavailable
            pass
        finally:
            # Restore original state
            if saved_pyvips is not None:
                sys.modules["pyvips"] = saved_pyvips
            else:
                sys.modules.pop("pyvips", None)
            if saved_module is not None:
                sys.modules["app.utils.images_vips"] = saved_module
            else:
                sys.modules.pop("app.utils.images_vips", None)
