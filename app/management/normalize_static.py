"""Normalize avatar and cover filenames and update DB references."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from sqlalchemy import update

from app.core.config import settings
from app.core.database import async_session
from app.core.logging import get_logger
from app.utils.files import normalize_filename_prefix

if TYPE_CHECKING:
    from pathlib import Path

    from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)

_STATIC_SUBDIRS = ("avatars", "covers")


def _normalize_path(path: Path) -> tuple[Path, str] | None:
    """Return new path and URL if the file name needs normalization."""

    if not path.is_file():
        return None
    stem = path.stem
    suffix = path.suffix
    if "_" in stem:
        prefix, remainder = stem.split("_", 1)
    else:
        prefix, remainder = stem, ""
    safe_prefix = normalize_filename_prefix(prefix)
    new_stem = f"{safe_prefix}_{remainder}" if remainder else safe_prefix
    new_name = f"{new_stem}{suffix}"
    if new_name == path.name:
        return None
    target = path.with_name(new_name)
    counter = 1
    while target.exists():
        target = path.with_name(f"{new_stem}-{counter}{suffix}")
        counter += 1
    public_url = f"/static/{path.parent.name}/{target.name}"
    return target, public_url


def _rename_files(base_dir: Path) -> tuple[dict[str, str], dict[str, str]]:
    avatar_mapping: dict[str, str] = {}
    cover_mapping: dict[str, str] = {}
    for subdir in _STATIC_SUBDIRS:
        directory = base_dir / subdir
        if not directory.exists():
            continue
        for item in directory.iterdir():
            result = _normalize_path(item)
            if result is None:
                continue
            target, public_url = result
            old_url = f"/static/{subdir}/{item.name}"
            # Rename on disk before touching the DB.
            target.parent.mkdir(parents=True, exist_ok=True)
            item.rename(target)
            if subdir == "avatars":
                avatar_mapping[old_url] = public_url
            else:
                cover_mapping[old_url] = public_url
            logger.info("Renamed %s -> %s", item.name, target.name)
    return avatar_mapping, cover_mapping


async def _update_column(
    session: AsyncSession, mapping: dict[str, str], column_name: str
) -> None:
    if not mapping:
        return
    from app.models.users import UserProfile

    column = getattr(UserProfile, column_name)
    for old_url, new_url in mapping.items():
        await session.execute(
            update(UserProfile).where(column == old_url).values({column_name: new_url})
        )


async def main() -> None:
    base_dir = settings.static_dir_path
    avatar_mapping, cover_mapping = _rename_files(base_dir)
    combined = {**avatar_mapping, **cover_mapping}
    if not combined:
        logger.info("Static assets already normalized")
        return
    async with async_session() as session, session.begin():
        await _update_column(session, avatar_mapping, "avatar_url")
        await _update_column(session, cover_mapping, "cover_url")
    logger.info(
        "Updated %s avatar URLs and %s cover URLs",
        len(avatar_mapping),
        len(cover_mapping),
    )


if __name__ == "__main__":
    asyncio.run(main())
