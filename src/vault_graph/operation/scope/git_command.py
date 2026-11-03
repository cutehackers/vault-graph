"""Run one read-only ``git`` command in a folder (정리 발견5).

The vault map (M17) finds the repository of a working folder and the code scanner (M11) reads the
repository revision. Both need the same small runner, and M01 is the area both may import.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


def run_git(folder: Path, *arguments: str, timeout_s: float | None = None) -> str | None:
    """Stripped standard output, which may be empty. None when git fails, is missing or times out."""
    try:
        result = subprocess.run(
            ("git", *arguments),
            cwd=folder,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip()


__all__ = ["run_git"]
