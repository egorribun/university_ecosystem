import sys
from unittest.mock import MagicMock, patch

import pytest

# Mock pyvips before importing images_vips to ensure VIPS_AVAILABLE is True
mock_pyvips = MagicMock()
mock_pyvips.enums.Size.DOWN = "down"
sys.modules["pyvips"] = mock_pyvips

if "app.utils.images_vips" in sys.modules:
    del sys.modules["app.utils.images_vips"]

import app.utils.images_vips as iv


def test_optimize_image_vips_success():
    # Setup mocks
    mock_image = MagicMock()
    mock_pyvips.Image.thumbnail_buffer.return_value = mock_image
    mock_image.autorot.return_value = mock_image
    mock_image.webpsave_buffer.return_value = b"webp-data"

    with patch("app.utils.images_vips.VIPS_AVAILABLE", True):
        res, mime = iv.optimize_image_vips(
            b"input-data", max_width=100, max_height=200, quality=75
        )

        assert res == b"webp-data"
        assert mime == "image/webp"
        mock_pyvips.Image.thumbnail_buffer.assert_called_once_with(
            b"input-data", 100, height=200, size="down"
        )
        mock_image.autorot.assert_called_once()
        mock_image.webpsave_buffer.assert_called_once_with(Q=75, effort=4, strip=True)


def test_optimize_image_vips_failure():
    mock_pyvips.Image.thumbnail_buffer.side_effect = Exception("vips internal error")

    with patch("app.utils.images_vips.VIPS_AVAILABLE", True):
        with pytest.raises(ValueError, match="Failed to process image with pyvips"):
            iv.optimize_image_vips(b"input-data")


def test_get_image_dimensions_vips():
    mock_image = MagicMock()
    mock_image.width = 800
    mock_image.height = 600
    mock_pyvips.Image.new_from_buffer.return_value = mock_image

    with patch("app.utils.images_vips.VIPS_AVAILABLE", True):
        width, height = iv.get_image_dimensions_vips(b"input-data")

        assert width == 800
        assert height == 600
        mock_pyvips.Image.new_from_buffer.assert_called_once_with(b"input-data", "")


def test_vips_not_available():
    with patch("app.utils.images_vips.VIPS_AVAILABLE", False):
        with pytest.raises(RuntimeError, match="pyvips is not available"):
            iv.optimize_image_vips(b"input-data")

        with pytest.raises(RuntimeError, match="pyvips is not available"):
            iv.get_image_dimensions_vips(b"input-data")
