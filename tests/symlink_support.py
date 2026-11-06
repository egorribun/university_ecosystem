"""Collection-time platform capability probes shared by symlink contract tests.

Windows creates symbolic links only with Developer Mode or an elevated token
(``SeCreateSymbolicLinkPrivilege``).  The probes perform a real native
``symlink_to`` call so that ``*_when_supported`` tests are gated by the actual
capability of the runner rather than by ``os.name`` and fail with an explicit
skip reason instead of an ``OSError`` from the test body (AUD-332).
"""

from __future__ import annotations

import errno
import os
import sys
import tempfile
from pathlib import Path

# ENOSYS/ENOTSUP/EOPNOTSUPP explicitly report unsupported POSIX operations.
# Linux symlink(2) also uses EPERM for filesystems without symlink support;
# elsewhere EPERM is ambiguous, and EACCES always remains operational here.
_POSIX_SYMLINK_UNAVAILABLE_ERRNOS = frozenset(
    error_number
    for error_name in ("ENOSYS", "ENOTSUP", "EOPNOTSUPP")
    if (error_number := getattr(errno, error_name, None)) is not None
)


def _symlink_capability_unavailable(error: OSError) -> bool:
    """Return only platform errors that mean symlink creation is unavailable."""
    winerror = getattr(error, "winerror", None)
    if winerror is not None:
        return winerror == 1314
    if os.name != "posix":
        return False
    if sys.platform.startswith("linux") and error.errno == errno.EPERM:
        return True
    return error.errno in _POSIX_SYMLINK_UNAVAILABLE_ERRNOS


def _directory_symlinks_supported() -> bool:
    with tempfile.TemporaryDirectory(prefix="pytest-symlink-capability-") as root:
        base = Path(root)
        target = base / "target"
        target.mkdir()
        link = base / "link"
        try:
            link.symlink_to(target, target_is_directory=True)
        except OSError as error:
            if _symlink_capability_unavailable(error):
                return False
            raise
        return link.is_symlink() and link.resolve() == target.resolve()


def _file_symlinks_supported() -> bool:
    with tempfile.TemporaryDirectory(prefix="pytest-symlink-capability-") as root:
        base = Path(root)
        target = base / "target.txt"
        target.write_text("probe", encoding="utf-8")
        link = base / "link.txt"
        try:
            link.symlink_to(target)
        except OSError as error:
            if _symlink_capability_unavailable(error):
                return False
            raise
        return link.is_symlink() and link.read_text(encoding="utf-8") == "probe"


DIRECTORY_SYMLINKS_SUPPORTED = _directory_symlinks_supported()
FILE_SYMLINKS_SUPPORTED = _file_symlinks_supported()
