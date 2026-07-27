"""Closure tests for StorageSettings derived sets and validators."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config.storage import StorageSettings


def test_storage_allowed_sets_normalize_and_filter_values():
    settings = StorageSettings(
        _allow_missing=True,
        chat_attachment_allowed_mime_types=" image/JPEG, , TEXT/PLAIN ",
        chat_attachment_allowed_extensions=".JPG, , .TXT",
        event_file_allowed_mime_types=" application/PDF, , text/plain ",
        event_file_allowed_extensions=".PDF, , .TXT",
    )

    assert settings.chat_attachment_allowed_mime_types_set == {
        "image/jpeg",
        "text/plain",
    }
    assert settings.chat_attachment_allowed_extensions_set == {"jpg", "txt"}
    assert settings.event_file_allowed_mime_types_set == {
        "application/pdf",
        "text/plain",
    }
    assert settings.event_file_allowed_extensions_set == {"pdf", "txt"}


def test_storage_backend_is_normalized_and_rejects_unknown_values():
    assert (
        StorageSettings(_allow_missing=True, storage_backend="  LOCAL ").storage_backend
        == "local"
    )

    with pytest.raises(ValidationError, match="STORAGE_BACKEND must be one of"):
        StorageSettings(_allow_missing=True, storage_backend="database")


def test_image_proxy_widths_are_sorted_and_static_path_handles_both_forms(tmp_path):
    settings = StorageSettings(
        _allow_missing=True,
        image_proxy_allowed_widths="800, bad, 100, 400",
        static_dir="relative-static",
    )

    assert settings.image_proxy_allowed_widths == [100, 400, 800]
    assert (
        settings.static_dir_path
        == (Path(__file__).parents[1] / "relative-static").resolve()
    )

    absolute = StorageSettings(_allow_missing=True, static_dir=str(tmp_path))
    assert absolute.static_dir_path == tmp_path
