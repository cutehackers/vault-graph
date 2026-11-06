"""Copy a folder as an APFS clone on macOS, or as a plain copy elsewhere."""

from __future__ import annotations

import ctypes
import os
import shutil
import sys
from pathlib import Path
from typing import Literal

# <sys/clonefile.h>: do not follow a symlink given as the source path.
_CLONE_NOFOLLOW = 0x0001


def clone_tree(source: Path, target: Path) -> Literal["clone", "copy"]:
    """Create target as a copy of the source folder.

    On macOS clonefile(2) clones the whole folder, so file blocks are shared until written.
    When clonefile fails or the system is not macOS, shutil.copytree copies the folder and
    one warning line goes to standard error. The target must not exist.
    """

    if target.exists() or target.is_symlink():
        raise FileExistsError(f"clone target already exists: {target}")
    reason = "clonefile(2) is only available on macOS"
    if sys.platform == "darwin":
        try:
            _clonefile(source, target)
            return "clone"
        except OSError as exc:
            reason = f"clonefile(2) failed: {exc}"
            _remove_partial_target(target)
    message = f"vault-graph: warning: {reason}; copying {source.name} with copytree instead"
    print(" ".join(message.split()), file=sys.stderr)
    shutil.copytree(source, target, symlinks=False)
    return "copy"


def _clonefile(source: Path, target: Path) -> None:
    function = getattr(ctypes.CDLL(None, use_errno=True), "clonefile", None)
    if function is None:
        raise OSError("clonefile(2) is not available in the C library")
    function.argtypes = (ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint32)
    function.restype = ctypes.c_int
    if function(os.fsencode(source), os.fsencode(target), _CLONE_NOFOLLOW) != 0:
        error_number = ctypes.get_errno()
        raise OSError(error_number, os.strerror(error_number), str(source))


def _remove_partial_target(target: Path) -> None:
    if target.is_symlink() or target.is_file():
        target.unlink(missing_ok=True)
    elif target.exists():
        shutil.rmtree(target, ignore_errors=True)
