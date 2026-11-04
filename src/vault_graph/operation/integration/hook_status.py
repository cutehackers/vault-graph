"""Read-only check of the vault-builder hook settings that ``vg setup`` reports on.

vault-builder writes ``<config dir>/vault-builder/vault-hooks.json`` with the absolute ``vg`` path the
hook launcher runs. vg only reads this file. Fixing it is ``vault-builder setup``'s job.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from collections.abc import Mapping
from pathlib import Path

from vault_graph.operation.integration.vault_map import CLAUDE_CONFIG_ENV

VAULT_HOOKS_RELATIVE_PATH = Path("vault-builder/vault-hooks.json")
FIX_COMMAND = "vault-builder setup"


def claude_config_dir(*, environ: Mapping[str, str] | None = None) -> Path:
    """Return ``$CLAUDE_CONFIG_DIR`` when set and not empty, else ``~/.claude`` (same rule as ``vault_map_path``)."""
    env = os.environ if environ is None else environ
    config_dir = env.get(CLAUDE_CONFIG_ENV)
    if config_dir:
        return Path(config_dir).expanduser().absolute()
    return Path("~/.claude").expanduser()


def vault_hooks_path(*, environ: Mapping[str, str] | None = None) -> Path:
    return claude_config_dir(environ=environ) / VAULT_HOOKS_RELATIVE_PATH


def running_vg_path() -> Path | None:
    """Return the vg executable of this process, or None when it cannot be told."""
    argv0 = Path(sys.argv[0]) if sys.argv and sys.argv[0] else None
    if argv0 is not None and argv0.name == "vg":
        found = argv0 if argv0.parent != Path() else shutil.which("vg")
        if found is not None:
            return Path(os.path.abspath(found))
    beside_python = Path(sys.executable).parent / "vg"
    if beside_python.is_file():
        return beside_python
    return None


def hook_status_warning(hooks_path: Path, running_vg: Path | None) -> str | None:
    """Return one warning line body for a hook problem, or None when the hooks use this vg."""
    if not hooks_path.is_file():
        return f"hook_not_installed: no hook settings at {hooks_path}. Run `{FIX_COMMAND}`."
    try:
        data = json.loads(hooks_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        reason = " ".join(f"{type(exc).__name__}: {exc}".split())
        return f"hook_settings_unreadable: cannot read {hooks_path} ({reason}). Run `{FIX_COMMAND}`."
    value = data.get("vg") if isinstance(data, dict) else None
    if not isinstance(value, str) or not value:
        return f"hook_vg_not_found: {hooks_path} has no vg path. Run `{FIX_COMMAND}`."
    recorded = Path(value)
    if not recorded.is_absolute() or not recorded.is_file() or not os.access(recorded, os.X_OK):
        return f"hook_vg_not_found: hook vg {value} is not an executable file. Run `{FIX_COMMAND}`."
    if running_vg is not None and not _same_file(recorded, running_vg):
        return f"hook_vg_differs: hooks use vg {value}, but this vg is {running_vg}. Run `{FIX_COMMAND}`."
    return None


def _same_file(left: Path, right: Path) -> bool:
    try:
        return left.resolve() == right.resolve()
    except OSError:
        return False
