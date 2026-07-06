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


@pytest.fixture(autouse=True)
def _reset_pyvips_mock():
    # mock_pyvips is installed into sys.modules at import time and is SHARED across
    # the whole pytest session, so its call counts ACCUMULATE: any earlier test that
    # exercises the image-processing production path (e.g. a media/profile-service
    # test, once this file's import has set sys.modules["pyvips"]) increments
    # Image.new_from_buffer / Image.thumbnail_buffer. Reset before each test so the
    # `assert_called_once_with(...)` checks below count ONLY the current test's calls.
    # Surfaced by mutmut, whose clean-test runs the changed modules' covering tests in
    # ONE deterministic-order pytest.main() (a context normal randomized CI never hits);
    # the tests pass in isolation but the shared mock leaks across that combined run.
    mock_pyvips.reset_mock(return_value=True, side_effect=True)
    mock_pyvips.enums.Size.DOWN = (
        "down"  # reset_mock(return_value=True) drops set attrs
    )
    yield


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
    import app.utils.images_vips as local_iv

    with patch("app.utils.images_vips.VIPS_AVAILABLE", False):
        with pytest.raises(RuntimeError, match="pyvips is not available"):
            local_iv.optimize_image_vips(b"input-data")

        with pytest.raises(RuntimeError, match="pyvips is not available"):
            local_iv.get_image_dimensions_vips(b"input-data")
