"""Collection-time platform capability probes shared by symlink contract tests.

Windows creates symbolic links only with Developer Mode or an elevated token
(``SeCreateSymbolicLinkPrivilege``).  The probes perform a real native
``symlink_to`` call so that ``*_when_supported`` tests are gated by the actual
capability of the runner rather than by ``os.name`` and fail with an explicit
skip reason instead of an ``OSError`` from the test body (AUD-332).
"""

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


def _file_symlinks_supported() -> bool:
    with tempfile.TemporaryDirectory(prefix="pytest-symlink-capability-") as root:
        base = Path(root)
        target = base / "target.txt"
        target.write_text("probe", encoding="utf-8")
        link = base / "link.txt"
        try:
            link.symlink_to(target)
        except OSError:
            return False
        return link.is_symlink() and link.read_text(encoding="utf-8") == "probe"


DIRECTORY_SYMLINKS_SUPPORTED = _directory_symlinks_supported()
FILE_SYMLINKS_SUPPORTED = _file_symlinks_supported()
