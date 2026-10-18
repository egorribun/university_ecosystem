"""Chat images are stored without identifying metadata."""

from __future__ import annotations

from io import BytesIO
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException, UploadFile
from PIL import ExifTags, Image, ImageChops, ImageOps, PngImagePlugin
from PIL.TiffImagePlugin import IFDRational
from starlette.datastructures import Headers

from app.core.config import settings
from app.services.chat import attachment_service
from app.services.chat.attachment_service import ChatAttachmentService
from app.services.storage import StaticFSStorage
from app.utils import files, images
from app.utils.images import ImagePixelLimitError

TEST_ICC_PROFILE = b"synthetic aud240 color profile"


def _gps_exif() -> Image.Exif:
    exif = Image.Exif()
    exif[ExifTags.Base.Orientation] = 6
    exif[ExifTags.IFD.GPSInfo] = {
        ExifTags.GPS.GPSLatitudeRef: "N",
        ExifTags.GPS.GPSLatitude: (
            IFDRational(37, 1),
            IFDRational(48, 1),
            IFDRational(30, 1),
        ),
        ExifTags.GPS.GPSLongitudeRef: "W",
        ExifTags.GPS.GPSLongitude: (
            IFDRational(122, 1),
            IFDRational(24, 1),
            IFDRational(15, 1),
        ),
    }
    return exif


def _jpeg_with_gps() -> bytes:
    image = Image.new("RGB", (2, 3), color=(20, 80, 140))
    payload = BytesIO()
    image.save(
        payload,
        format="JPEG",
        exif=_gps_exif(),
        xmp=b"aud240-xmp-sentinel",
        comment=b"aud240-comment-sentinel",
        icc_profile=TEST_ICC_PROFILE,
    )
    return payload.getvalue()


@pytest.mark.asyncio
async def test_chat_jpeg_scan_preserves_original_and_storage_strips_gps_orientation(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    original = _jpeg_with_gps()
    with Image.open(BytesIO(original)) as source:
        assert source.getexif().get(ExifTags.Base.Orientation) == 6
        gps = source.getexif().get_ifd(ExifTags.IFD.GPSInfo)
        assert gps[ExifTags.GPS.GPSLatitudeRef] == "N"
    backend = StaticFSStorage(tmp_path, base_url="/static")
    scanned_payloads: list[bytes] = []

    async def record_storage_scan(data: bytes, **_kwargs: object) -> None:
        scanned_payloads.append(data)

    monkeypatch.setattr(attachment_service, "scan_for_malware", AsyncMock())
    monkeypatch.setattr(files, "scan_for_malware", record_storage_scan)
    monkeypatch.setattr(files, "_get_storage_backend", lambda: backend)
    upload = UploadFile(
        filename="location.jpg",
        file=BytesIO(original),
        size=len(original),
        headers=Headers({"content-type": "image/jpeg"}),
    )

    try:
        result = await ChatAttachmentService().process_upload(
            upload, uuid4(), locale="en"
        )
        stored = await backend.read_file(str(result["url"]))
    finally:
        await upload.close()

    assert scanned_payloads == [original]
    assert result["file_type"] == "image"
    assert result["size"] == len(stored)
    assert str(result["url"]).endswith(".jpg")
    with Image.open(BytesIO(stored)) as sanitized:
        assert sanitized.format == "JPEG"
        assert sanitized.size == (3, 2)
        assert ExifTags.IFD.GPSInfo not in sanitized.getexif()
        assert ExifTags.Base.Orientation not in sanitized.getexif()
        assert sanitized.info.get("icc_profile") == TEST_ICC_PROFILE
        assert not {"exif", "xmp", "comment"}.intersection(sanitized.info)
    assert b"aud240-xmp-sentinel" not in stored
    assert b"aud240-comment-sentinel" not in stored


@pytest.mark.asyncio
async def test_chat_rejects_invalid_image_without_persisting_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    backend = StaticFSStorage(tmp_path, base_url="/static")
    monkeypatch.setattr(attachment_service, "scan_for_malware", AsyncMock())
    monkeypatch.setattr(files, "scan_for_malware", AsyncMock())
    monkeypatch.setattr(files, "_get_storage_backend", lambda: backend)
    monkeypatch.setattr(files, "detect_mime_type", lambda _data: "image/jpeg")
    payload = b"\xff\xd8\xffnot a decodable JPEG"
    upload = UploadFile(
        filename="broken.jpg",
        file=BytesIO(payload),
        size=len(payload),
        headers=Headers({"content-type": "image/jpeg"}),
    )

    try:
        with pytest.raises(HTTPException) as error:
            await ChatAttachmentService().process_upload(upload, uuid4(), locale="en")
    finally:
        await upload.close()

    assert error.value.status_code == 415
    assert not (tmp_path / "chat_uploads").exists()


@pytest.mark.asyncio
async def test_chat_rejects_sanitized_image_that_exceeds_upload_limit(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    backend = StaticFSStorage(tmp_path, base_url="/static")
    monkeypatch.setattr(attachment_service, "scan_for_malware", AsyncMock())
    monkeypatch.setattr(files, "scan_for_malware", AsyncMock())
    monkeypatch.setattr(files, "_get_storage_backend", lambda: backend)
    monkeypatch.setattr(settings, "chat_attachment_max_size_bytes", 4096)
    monkeypatch.setattr(
        images, "strip_image_metadata", lambda *_args, **_kwargs: b"x" * 4097
    )
    payload = _jpeg_with_gps()
    upload = UploadFile(
        filename="location.jpg",
        file=BytesIO(payload),
        size=len(payload),
        headers=Headers({"content-type": "image/jpeg"}),
    )

    try:
        with pytest.raises(HTTPException) as error:
            await ChatAttachmentService().process_upload(upload, uuid4(), locale="en")
    finally:
        await upload.close()

    assert error.value.status_code == 413
    assert not (tmp_path / "chat_uploads").exists()


@pytest.mark.asyncio
async def test_chat_non_image_attachment_bytes_are_unchanged(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    backend = StaticFSStorage(tmp_path, base_url="/static")
    monkeypatch.setattr(attachment_service, "scan_for_malware", AsyncMock())
    monkeypatch.setattr(files, "scan_for_malware", AsyncMock())
    monkeypatch.setattr(files, "_get_storage_backend", lambda: backend)
    payload = b"%PDF-1.7\nsynthetic attachment bytes"
    upload = UploadFile(
        filename="report.pdf",
        file=BytesIO(payload),
        size=len(payload),
        headers=Headers({"content-type": "application/pdf"}),
    )

    try:
        result = await ChatAttachmentService().process_upload(
            upload, uuid4(), locale="en"
        )
        stored = await backend.read_file(str(result["url"]))
    finally:
        await upload.close()

    assert result["file_type"] == "file"
    assert result["size"] == len(payload)
    assert stored == payload


@pytest.mark.asyncio
async def test_generic_image_attachment_keeps_legacy_byte_preservation_by_default(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    backend = StaticFSStorage(tmp_path, base_url="/static")
    original = _jpeg_with_gps()
    monkeypatch.setattr(files, "scan_for_malware", AsyncMock())
    monkeypatch.setattr(files, "detect_mime_type", lambda _data: "image/jpeg")
    monkeypatch.setattr(files, "_get_storage_backend", lambda: backend)
    upload = UploadFile(
        filename="event-location.jpg",
        file=BytesIO(original),
        size=len(original),
        headers=Headers({"content-type": "image/jpeg"}),
    )

    try:
        result = await files.save_attachment(
            upload,
            "event_files",
            "event-test",
            allowed_mime_types={"image/jpeg"},
            allowed_extensions={"jpg"},
            max_size_bytes=4096,
            return_meta=True,
        )
        assert isinstance(result, dict)
        stored = await backend.read_file(str(result["url"]))
    finally:
        await upload.close()

    assert stored == original
    assert result["size"] == len(original)


def test_png_metadata_stripping_applies_orientation_and_removes_exif() -> None:
    original_buffer = BytesIO()
    pnginfo = PngImagePlugin.PngInfo()
    pnginfo.add_text("XML:com.adobe.xmp", "aud240-png-xmp-sentinel")
    pnginfo.add_text("Comment", "aud240-png-comment-sentinel")
    Image.new("RGB", (2, 3), color=(90, 120, 150)).save(
        original_buffer,
        format="PNG",
        exif=_gps_exif().tobytes(),
        icc_profile=TEST_ICC_PROFILE,
        pnginfo=pnginfo,
    )
    original = original_buffer.getvalue()
    with Image.open(BytesIO(original)) as source:
        assert source.getexif().get(ExifTags.Base.Orientation) == 6

    sanitized_data = images.strip_image_metadata(
        original, content_type="image/png", max_pixels=100
    )

    with Image.open(BytesIO(sanitized_data)) as sanitized:
        assert sanitized.format == "PNG"
        assert sanitized.size == (3, 2)
        assert ExifTags.IFD.GPSInfo not in sanitized.getexif()
        assert ExifTags.Base.Orientation not in sanitized.getexif()
        assert sanitized.info.get("icc_profile") == TEST_ICC_PROFILE
        assert not {"exif", "xmp", "XML:com.adobe.xmp", "Comment"}.intersection(
            sanitized.info
        )
    assert b"aud240-png-xmp-sentinel" not in sanitized_data
    assert b"aud240-png-comment-sentinel" not in sanitized_data


def test_metadata_stripping_rejects_mime_mismatch_and_pixel_budget_overflow() -> None:
    original = _jpeg_with_gps()

    with pytest.raises(ValueError, match="Unsupported image format"):
        images.strip_image_metadata(original, content_type="image/avif", max_pixels=100)
    with pytest.raises(ValueError, match="does not match"):
        images.strip_image_metadata(original, content_type="image/png", max_pixels=100)
    with pytest.raises(ImagePixelLimitError):
        images.strip_image_metadata(original, content_type="image/jpeg", max_pixels=5)


@pytest.mark.parametrize(
    ("image_format", "content_type", "loop", "durations"),
    [
        ("GIF", "image/gif", 2, [40, 80]),
        ("WEBP", "image/webp", 3, [50, 90]),
    ],
)
def test_metadata_stripping_preserves_animation_frames_timing_and_loop(
    image_format: str,
    content_type: str,
    loop: int,
    durations: list[int],
) -> None:
    first = Image.new("RGB", (3, 2), color=(220, 10, 10))
    second = Image.new("RGB", (3, 2), color=(10, 20, 220))
    original_buffer = BytesIO()
    if image_format == "GIF":
        first.save(
            original_buffer,
            format=image_format,
            save_all=True,
            append_images=[second],
            duration=durations,
            loop=loop,
            comment=b"location-sensitive-comment",
            disposal=[2, 1],
        )
    else:
        first.save(
            original_buffer,
            format=image_format,
            save_all=True,
            append_images=[second],
            duration=durations,
            loop=loop,
            lossless=True,
            exif=_gps_exif(),
            xmp=b"<x:xmpmeta>location-sensitive-xmp</x:xmpmeta>",
            icc_profile=TEST_ICC_PROFILE,
        )

    original_buffer.seek(0)
    with Image.open(original_buffer) as source:
        if image_format == "WEBP":
            assert source.getexif().get(ExifTags.Base.Orientation) == 6
        expected_frames = []
        expected_disposals = []
        for frame_index in range(source.n_frames):
            source.seek(frame_index)
            expected_frames.append(
                ImageOps.exif_transpose(source).convert("RGBA").copy()
            )
            if image_format == "GIF":
                expected_disposals.append(source.disposal_method)

    sanitized_data = images.strip_image_metadata(
        original_buffer.getvalue(), content_type=content_type, max_pixels=100
    )
    with Image.open(BytesIO(sanitized_data)) as sanitized:
        assert sanitized.format == image_format
        assert sanitized.n_frames == 2
        assert sanitized.info.get("loop") == loop
        actual_durations = []
        actual_disposals = []
        for frame_index in range(sanitized.n_frames):
            sanitized.seek(frame_index)
            actual_frame = sanitized.convert("RGBA")
            actual_durations.append(sanitized.info.get("duration", 0))
            if image_format == "GIF":
                actual_disposals.append(sanitized.disposal_method)
            assert (
                ImageChops.difference(
                    expected_frames[frame_index], actual_frame
                ).getbbox(alpha_only=False)
                is None
            )
        assert actual_durations == durations
        if image_format == "GIF":
            assert expected_disposals == [2, 1]
            assert actual_disposals == [2, 2]
            assert b"location-sensitive-comment" not in sanitized_data
        else:
            assert b"location-sensitive-xmp" not in sanitized_data
        assert "exif" not in sanitized.info
        assert "xmp" not in sanitized.info
        assert "comment" not in sanitized.info
        if image_format == "WEBP":
            assert sanitized.info.get("icc_profile") == TEST_ICC_PROFILE


def test_static_gif_without_loop_metadata_remains_static_and_unchanged() -> None:
    original_buffer = BytesIO()
    expected_frame = Image.new("RGB", (3, 2), color=(23, 91, 177))
    expected_frame.save(original_buffer, format="GIF", comment=b"private-comment")
    original = original_buffer.getvalue()

    with Image.open(BytesIO(original)) as source:
        assert source.n_frames == 1
        assert "loop" not in source.info

    sanitized_data = images.strip_image_metadata(
        original, content_type="image/gif", max_pixels=100
    )

    with Image.open(BytesIO(sanitized_data)) as sanitized:
        assert sanitized.format == "GIF"
        assert sanitized.n_frames == 1
        assert "loop" not in sanitized.info
        assert "comment" not in sanitized.info
        assert (
            ImageChops.difference(
                expected_frame.convert("RGBA"), sanitized.convert("RGBA")
            ).getbbox(alpha_only=False)
            is None
        )
    assert b"private-comment" not in sanitized_data


def test_gif_metadata_stripping_preserves_frames_across_disposal_modes() -> None:
    size = (3, 2)
    durations = [40, 80, 120, 160]
    frame_definitions = [
        (1, 0, (220, 10, 10), (0, 0)),
        (6, 5, (10, 20, 220), (1, 0)),
        (9, 7, (10, 220, 20), (2, 0)),
        (12, 11, (230, 200, 10), (0, 1)),
    ]
    original_frames = []
    for color_index, transparent_index, color, point in frame_definitions:
        palette = [0] * 768
        palette[transparent_index * 3 : transparent_index * 3 + 3] = [3, 4, 5]
        palette[color_index * 3 : color_index * 3 + 3] = list(color)
        image = Image.new("P", size, color=transparent_index)
        image.putpalette(palette)
        image.putpixel(point, color_index)
        image.info["transparency"] = transparent_index
        original_frames.append(image)

    original_buffer = BytesIO()
    original_frames[0].save(
        original_buffer,
        format="GIF",
        save_all=True,
        append_images=original_frames[1:],
        duration=durations,
        disposal=[2, 2, 3, 1],
        loop=3,
        optimize=False,
        comment=b"aud240-gif-disposal-comment",
    )
    original = original_buffer.getvalue()

    with Image.open(BytesIO(original)) as source:
        assert source.n_frames == 4
        expected_frames = []
        original_durations = []
        original_disposals = []
        for frame_index in range(source.n_frames):
            source.seek(frame_index)
            expected_frames.append(source.convert("RGBA").copy())
            original_durations.append(source.info.get("duration", 0))
            original_disposals.append(source.disposal_method)

    assert original_disposals == [2, 2, 3, 1]
    sanitized_data = images.strip_image_metadata(
        original, content_type="image/gif", max_pixels=100
    )

    with Image.open(BytesIO(sanitized_data)) as sanitized:
        assert sanitized.n_frames == len(expected_frames)
        assert sanitized.info.get("loop") == 3
        actual_durations = []
        actual_disposals = []
        for frame_index in range(sanitized.n_frames):
            sanitized.seek(frame_index)
            actual_frame = sanitized.convert("RGBA")
            actual_durations.append(sanitized.info.get("duration", 0))
            actual_disposals.append(sanitized.disposal_method)
            assert (
                ImageChops.difference(
                    expected_frames[frame_index], actual_frame
                ).getbbox(alpha_only=False)
                is None
            )

    assert actual_durations == original_durations == durations
    assert actual_disposals == [2, 2, 2, 2]
    assert b"aud240-gif-disposal-comment" not in sanitized_data


@pytest.mark.parametrize("default_image", [False, True])
@pytest.mark.parametrize("disposal_mode", [1, 2])
def test_apng_metadata_stripping_preserves_composited_animation(
    default_image: bool, disposal_mode: int
) -> None:
    size = (2, 3)
    standalone = Image.new(
        "RGBA",
        size,
        color=(20, 30, 40, 255) if default_image else (0, 0, 0, 0),
    )
    red_frame = Image.new("RGBA", size, color=(0, 0, 0, 0))
    red_frame.putpixel((0, 0), (220, 10, 10, 128))
    blue_frame = Image.new("RGBA", size, color=(0, 0, 0, 0))
    blue_frame.putpixel((0, 0), (10, 20, 220, 128))
    green_frame = Image.new("RGBA", size, color=(0, 0, 0, 0))
    green_frame.putpixel((0, 0), (10, 220, 20, 128))
    animation_frames = [red_frame, blue_frame, green_frame]
    payload = BytesIO()
    pnginfo = PngImagePlugin.PngInfo()
    pnginfo.add_text("XML:com.adobe.xmp", "aud240-xmp-sentinel")
    pnginfo.add_text("Comment", "aud240-comment-sentinel")

    durations = [70, 130, 190] if default_image else [40, 70, 130, 190]
    disposal = [0, disposal_mode, 0] if default_image else [0, 0, disposal_mode, 0]
    blend = [0, 1, 1] if default_image else [0, 1, 1, 1]
    save_options: dict[str, object] = {
        "format": "PNG",
        "save_all": True,
        "append_images": animation_frames,
        "duration": durations,
        "disposal": disposal,
        "blend": blend,
        "loop": 4,
        "icc_profile": TEST_ICC_PROFILE,
        "exif": _gps_exif().tobytes(),
        "pnginfo": pnginfo,
    }
    if default_image:
        save_options["default_image"] = True
    standalone.save(payload, **save_options)
    original = payload.getvalue()

    with Image.open(BytesIO(original)) as source:
        assert source.getexif().get(ExifTags.Base.Orientation) == 6
        expected_default_image = bool(source.info.get("default_image"))
        animation_offset = 1 if expected_default_image else 0
        expected_frames = []
        expected_durations = []
        expected_disposal = []
        expected_blend = []
        for frame_index in range(source.n_frames):
            source.seek(frame_index)
            expected_frames.append(
                ImageOps.exif_transpose(source).convert("RGBA").copy()
            )
            if frame_index >= animation_offset:
                expected_durations.append(source.info.get("duration", 0))
                expected_disposal.append(source.info.get("disposal", 0))
                expected_blend.append(source.info.get("blend", 0))

    sanitized_data = images.strip_image_metadata(
        original, content_type="image/png", max_pixels=100
    )
    with Image.open(BytesIO(sanitized_data)) as sanitized:
        assert sanitized.format == "PNG"
        assert sanitized.n_frames == len(expected_frames)
        assert bool(sanitized.info.get("default_image")) is expected_default_image
        assert sanitized.info.get("loop") == 4
        assert sanitized.info.get("icc_profile") == TEST_ICC_PROFILE
        actual_durations = []
        actual_disposal = []
        actual_blend = []
        for frame_index in range(sanitized.n_frames):
            sanitized.seek(frame_index)
            actual_frame = sanitized.convert("RGBA")
            assert (
                ImageChops.difference(
                    expected_frames[frame_index], actual_frame
                ).getbbox(alpha_only=False)
                is None
            )
            if frame_index >= animation_offset:
                actual_durations.append(sanitized.info.get("duration", 0))
                actual_disposal.append(sanitized.info.get("disposal", 0))
                actual_blend.append(sanitized.info.get("blend", 0))
        assert actual_durations == expected_durations
        assert disposal_mode in expected_disposal
        assert 1 in expected_blend
        assert actual_disposal == [0] * len(expected_durations)
        assert actual_blend == [0] * len(expected_durations)
        assert "exif" not in sanitized.info
        assert "xmp" not in sanitized.info
        assert "XML:com.adobe.xmp" not in sanitized.info
        assert "Comment" not in sanitized.info
    assert b"aud240-xmp-sentinel" not in sanitized_data
    assert b"aud240-comment-sentinel" not in sanitized_data


@pytest.mark.asyncio
async def test_chat_gif_fallback_detection_preserves_animation_without_comment(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    backend = StaticFSStorage(tmp_path, base_url="/static")
    scanned_payloads: list[bytes] = []

    async def record_storage_scan(data: bytes, **_kwargs: object) -> None:
        scanned_payloads.append(data)

    monkeypatch.setattr(attachment_service, "scan_for_malware", AsyncMock())
    monkeypatch.setattr(files, "scan_for_malware", record_storage_scan)
    monkeypatch.setattr(files, "_magic_mime_detector", None)
    monkeypatch.setattr(files, "_get_storage_backend", lambda: backend)
    first = Image.new("RGB", (3, 2), color=(220, 10, 10))
    second = Image.new("RGB", (3, 2), color=(10, 20, 220))
    payload = BytesIO()
    first.save(
        payload,
        format="GIF",
        save_all=True,
        append_images=[second],
        duration=[40, 80],
        loop=2,
        comment=b"aud240-gif-comment-sentinel",
        disposal=[2, 1],
    )
    original = payload.getvalue()
    assert files.detect_mime_type(original) == "image/gif"
    upload = UploadFile(
        filename="animation.gif",
        file=BytesIO(original),
        size=len(original),
        headers=Headers({"content-type": "image/gif"}),
    )

    try:
        result = await ChatAttachmentService().process_upload(
            upload, uuid4(), locale="en"
        )
        stored = await backend.read_file(str(result["url"]))
    finally:
        await upload.close()

    assert scanned_payloads == [original]
    assert result["file_type"] == "image"
    assert result["size"] == len(stored)
    assert str(result["url"]).endswith(".gif")
    assert b"aud240-gif-comment-sentinel" not in stored
    with Image.open(BytesIO(stored)) as sanitized:
        assert sanitized.format == "GIF"
        assert sanitized.n_frames == 2
        assert sanitized.info.get("loop") == 2
        durations = []
        disposals = []
        for frame_index in range(sanitized.n_frames):
            sanitized.seek(frame_index)
            sanitized.load()
            durations.append(sanitized.info.get("duration", 0))
            disposals.append(sanitized.disposal_method)
        assert durations == [40, 80]
        assert disposals == [2, 2]
        assert "comment" not in sanitized.info


def test_metadata_stripping_enforces_aggregate_pixel_and_frame_budgets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = Image.new("RGB", (3, 2), color=(220, 10, 10))
    second = Image.new("RGB", (3, 2), color=(10, 20, 220))
    payload = BytesIO()
    first.save(
        payload,
        format="GIF",
        save_all=True,
        append_images=[second],
        duration=[40, 80],
    )
    animation = payload.getvalue()

    with pytest.raises(ImagePixelLimitError):
        images.strip_image_metadata(animation, content_type="image/gif", max_pixels=10)

    monkeypatch.setattr(images, "_MAX_METADATA_SANITIZATION_FRAMES", 1)
    with pytest.raises(ValueError, match="frame count"):
        images.strip_image_metadata(animation, content_type="image/gif", max_pixels=100)
