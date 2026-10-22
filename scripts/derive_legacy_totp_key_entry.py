#!/usr/bin/env python3
"""Write one legacy Spotify-fallback TOTP ring entry without displaying it."""

from __future__ import annotations

import argparse
import base64
import hashlib
import os
import stat
import sys
from pathlib import Path

_MAX_HISTORICAL_SECRET_BYTES = 4096
_LEGACY_KEY_ID = "legacy-spotify-derived"
_PLATFORM_NAME = os.name


def _read_historical_secret(path: Path) -> str:
    flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    descriptor = os.open(path, flags)
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError("historical secret source must be a regular file")
        if metadata.st_size > _MAX_HISTORICAL_SECRET_BYTES:
            raise ValueError("historical secret source exceeds the allowed size")
        chunks: list[bytes] = []
        remaining = _MAX_HISTORICAL_SECRET_BYTES + 1
        while remaining:
            chunk = os.read(descriptor, remaining)
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
    finally:
        os.close(descriptor)
    if len(raw) > _MAX_HISTORICAL_SECRET_BYTES:
        raise ValueError("historical secret source exceeds the allowed size")
    try:
        value = raw.decode("utf-8").strip()
    except UnicodeDecodeError:
        raise ValueError("historical secret source must be UTF-8 text") from None
    if not value:
        raise ValueError("historical secret source is empty")
    return value


def _write_entry_exclusively(path: Path, content: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
    descriptor = os.open(path, flags, 0o600)
    try:
        offset = 0
        while offset < len(content):
            written = os.write(descriptor, content[offset:])
            if written <= 0:
                raise OSError("could not write the complete protected entry")
            offset += written
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
    except BaseException:
        if descriptor >= 0:
            try:
                os.close(descriptor)
            except OSError:
                pass
        try:
            os.unlink(path)
        except OSError:
            pass
        raise


def derive_legacy_totp_key_entry(
    historical_secret_key_file: Path, output_file: Path
) -> None:
    """Reproduce Spotify's former SECRET_KEY fallback as a legacy-only entry."""
    if _PLATFORM_NAME != "posix":
        raise OSError("protected key output requires a POSIX filesystem")
    historical_secret = _read_historical_secret(historical_secret_key_file)
    digest = hashlib.sha256(historical_secret.encode("utf-8")).digest()
    encoded_key = base64.urlsafe_b64encode(digest)
    entry = f"{_LEGACY_KEY_ID}:{encoded_key.decode('ascii')}\n".encode("ascii")
    _write_entry_exclusively(output_file, entry)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--historical-secret-key-file", required=True, type=Path)
    parser.add_argument("--output-file", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        derive_legacy_totp_key_entry(
            args.historical_secret_key_file,
            args.output_file,
        )
    except (OSError, UnicodeError, ValueError):
        print(
            "Legacy TOTP key entry generation failed; no key material was displayed.",
            file=sys.stderr,
        )
        return 1
    print("Legacy TOTP key entry written to the requested protected file.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
