"""Collection-time platform capability probes shared by symlink contract tests."""

from __future__ import annotations

import tempfile
from pathlib import Path


def _directory_symlinks_supported() -> bool:
    with tempfile.TemporaryDirectory(prefix="pytest-symlink-capability-") as root:
        base = Path(root)
        target = base / "target"
        target.mkdir()
        link = base / "link"
        try:
            link.symlink_to(target, target_is_directory=True)
        except OSError:
            return False
        return link.is_symlink() and link.resolve() == target.resolve()


DIRECTORY_SYMLINKS_SUPPORTED = _directory_symlinks_supported()
