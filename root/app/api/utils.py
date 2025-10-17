from fastapi import UploadFile

from app.utils.files import save_image


async def save_upload(
    file: UploadFile,
    subdir: str,
    prefix: str,
    *,
    locale: str | None = None,
) -> str:
    """Persist an uploaded file using the shared image helper."""

    return await save_image(file, subdir, prefix, locale=locale)
