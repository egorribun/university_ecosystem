"""Bundled demo media: provenance, storage keys and the seed's install step.

Seeded news, stories and events load their photographs from the site's own
storage, because img-src allows no third-party image host apart from Spotify
album art (ADR-047, owner decision 2026-11-21).
"""

from __future__ import annotations

import json
import re
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from app.api.images import _PUBLIC_S3_IMAGE_PREFIXES
from app.utils.files import _cache_control_for_subdir
from scripts import seed_demo_data

ROOT = Path(__file__).resolve().parents[1]
MEDIA_DIR = ROOT / "scripts" / "demo_media"
PROVENANCE = json.loads((MEDIA_DIR / "PROVENANCE.json").read_text(encoding="utf-8"))
SEED_ITEMS = (
    *seed_demo_data.NEWS_DATA,
    *seed_demo_data.STORIES_DATA,
    *seed_demo_data.EVENTS_DATA,
    *seed_demo_data.ARCHIVE_EVENTS_DATA,
)
SIZES = {"news": (800, 600), "event": (800, 600), "story": (400, 700)}


def _seed_image_url(item: dict) -> str:
    return item["cover_url"] if "short_text" in item else item["image_url"]


def test_provenance_lists_exactly_the_bundled_images_the_seed_uses() -> None:
    files = sorted(path.name for path in MEDIA_DIR.glob("*.webp"))
    assert sorted(entry["file"] for entry in PROVENANCE["images"]) == files
    assert seed_demo_data._demo_media_files() == files
    assert {_seed_image_url(item) for item in SEED_ITEMS} == {
        seed_demo_data.demo_media_url(name) for name in files
    }
    assert len(files) == 35
    assert PROVENANCE["license"] == "Unsplash License"
    assert PROVENANCE["license_url"] == "https://unsplash.com/license"


@pytest.mark.parametrize("entry", PROVENANCE["images"], ids=lambda entry: entry["file"])
def test_each_image_is_a_metadata_free_webp_of_its_declared_size(entry) -> None:
    kind, index = re.fullmatch(
        r"(news|event|story)-(\d{2})\.webp", entry["file"]
    ).groups()
    width, height = SIZES[kind]
    assert (entry["width"], entry["height"]) == (width, height)
    assert entry["replaces"] == (
        f"https://picsum.photos/seed/{kind}{int(index)}/{width}/{height}"
    )
    assert re.fullmatch(r"https://unsplash\.com/photos/[\w-]+", entry["source"])
    assert entry["author"].strip()
    with Image.open(BytesIO((MEDIA_DIR / entry["file"]).read_bytes())) as image:
        assert image.format == "WEBP"
        assert image.size == (width, height)
        assert not {"exif", "xmp", "icc_profile"} & set(image.info)


def test_seed_data_references_only_storage_urls() -> None:
    source = (ROOT / "scripts" / "seed_demo_data.py").read_text(encoding="utf-8")
    assert "picsum" not in source
    assert "https://" not in "".join(_seed_image_url(item) for item in SEED_ITEMS)
    base_url = seed_demo_data._get_storage_backend().base_url
    for item in SEED_ITEMS:
        assert _seed_image_url(item).startswith(f"{base_url}/")


@pytest.mark.parametrize("file_name", seed_demo_data._demo_media_files())
def test_demo_keys_are_public_and_outside_every_upload_ownership_pattern(
    file_name: str,
) -> None:
    key = seed_demo_data._demo_media_key(file_name)
    prefix, _, name = key.rpartition("/")
    assert key.startswith(_PUBLIC_S3_IMAGE_PREFIXES)
    assert prefix == seed_demo_data._DEMO_MEDIA_PREFIXES[file_name.partition("-")[0]]
    assert re.fullmatch(r"demo_[0-9a-f]{32}\.webp", name)
    # Upload names start with their owner prefix (news_, stories_, event_<id>_),
    # so ownership-based cleanup never claims or deletes a shared demo image.
    assert not name.startswith(("news_", "stories_", "event_"))
    assert _cache_control_for_subdir(prefix) == "public, max-age=31536000, immutable"


@pytest.mark.parametrize(
    ("base_url", "expected_prefix"),
    [
        ("", "/"),
        ("/static", "/static/"),
        ("https://campus.test/api/v1/img", "https://campus.test/api/v1/img/"),
    ],
)
def test_demo_media_url_follows_the_storage_base_url(
    monkeypatch: pytest.MonkeyPatch, base_url: str, expected_prefix: str
) -> None:
    monkeypatch.setattr(
        seed_demo_data,
        "_get_storage_backend",
        lambda: SimpleNamespace(base_url=base_url),
    )
    key = seed_demo_data._demo_media_key("news-01.webp")
    assert seed_demo_data.demo_media_url("news-01.webp") == expected_prefix + key


class _FakeStorage:
    base_url = "https://campus.test/api/v1/img"

    def __init__(self, *, wrong_url: bool = False) -> None:
        self.objects: dict[str, tuple[bytes, str | None, str | None]] = {}
        self.wrong_url = wrong_url

    async def exists(self, key: str) -> bool:
        return key in self.objects

    async def save_file(
        self,
        key: str,
        data: bytes,
        *,
        content_type: str | None = None,
        cache_control: str | None = None,
    ) -> str:
        self.objects[key] = (data, content_type, cache_control)
        return (
            f"https://elsewhere.test/{key}"
            if self.wrong_url
            else f"{self.base_url}/{key}"
        )


@pytest.mark.asyncio
async def test_install_stores_each_image_once_and_is_idempotent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _FakeStorage()
    monkeypatch.setattr(seed_demo_data, "_get_storage_backend", lambda: storage)

    await seed_demo_data.install_demo_media()
    first = dict(storage.objects)
    await seed_demo_data.install_demo_media()

    assert storage.objects == first
    assert len(first) == 35
    for file_name in seed_demo_data._demo_media_files():
        data, content_type, cache_control = first[
            seed_demo_data._demo_media_key(file_name)
        ]
        assert data == (MEDIA_DIR / file_name).read_bytes()
        assert content_type == "image/webp"
        assert cache_control == "public, max-age=31536000, immutable"


@pytest.mark.asyncio
async def test_install_fails_when_storage_returns_another_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _FakeStorage(wrong_url=True)
    monkeypatch.setattr(seed_demo_data, "_get_storage_backend", lambda: storage)

    with pytest.raises(RuntimeError, match="does not match its seed URL"):
        await seed_demo_data.install_demo_media()


def test_seed_installs_media_before_writing_rows_that_reference_it() -> None:
    source = (ROOT / "scripts" / "seed_demo_data.py").read_text(encoding="utf-8")
    body = source[source.index("async def main() -> None:") :]
    assert body.index("await install_demo_media()") < body.index(
        "await seed_news(db, user)"
    )
