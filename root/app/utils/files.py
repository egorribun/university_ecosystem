from pathlib import Path
import secrets
import mimetypes
from fastapi import UploadFile, HTTPException, status
from app.core.config import settings

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_IMAGE_SIZE = 5 * 1024 * 1024

def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)

async def _read_limited(upload: UploadFile, limit: int) -> bytes:
    data = await upload.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="file too large")
    return data

def _ext_from_mime(mime: str) -> str:
    exts = mimetypes.guess_all_extensions(mime) or []
    return exts[0] if exts else ""

def _gen_name(prefix: str, ext: str) -> str:
    token = secrets.token_hex(16)
    ext = ext if ext.startswith(".") else f".{ext}" if ext else ""
    return f"{prefix}_{token}{ext}"

async def save_image(upload: UploadFile, subdir: str, prefix: str) -> str:
    if upload.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="unsupported media type")
    data = await _read_limited(upload, MAX_IMAGE_SIZE)
    ext = _ext_from_mime(upload.content_type) or {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
    }.get(upload.content_type, "")
    name = _gen_name(prefix, ext)
    base = Path(settings.static_dir)
    _ensure_dir(base / subdir)
    path = base / subdir / name
    with open(path, "wb") as f:
        f.write(data)
    return f"/static/{subdir}/{name}"