"""Read ``vault-map.json`` version 2 and find the project of a folder (spec 4.2.2, 결정9).

vault-builder owns the file and the project finding rule. The rule here follows
``find_project`` in ``$HOME/.claude/vault-builder/llm_wiki_router.py``: compare the main
worktree root, then the normalized origin remote, then the folder name. The first stage with
one match decides. A stage with two or more matches decides nothing. This module never
writes the file.
"""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from urllib.parse import unquote, urlsplit

from vault_graph.project.context.project_binding_reader import MappedProjectMatch, MappedVault, VaultMapReader

VAULT_MAP_VERSION = 2
VAULT_MAP_ENV = "VAULT_GRAPH_VAULT_MAP"
DEFAULT_VAULT_MAP_PATH = Path("~/.claude/vault-builder/vault-map.json")

STAGE_ROOT = "root"
STAGE_REMOTE = "remote"
STAGE_NAME = "name"

VaultMapState = Literal["loaded", "missing", "invalid"]


class VaultMapError(ValueError):
    """The file is missing, is not version 2, or does not have the version 2 shape."""


@dataclass(frozen=True)
class MappedProject:
    project_id: str
    root: str
    vault_names: tuple[str, ...]
    remote: str | None
    default_write_vault: str | None = None


class VaultMap(VaultMapReader):
    """Read-only view of one ``vault-map.json`` version 2 file.

    ``warnings`` lists optional fields that were ignored because their value was unusable.
    """

    def __init__(
        self,
        *,
        path: Path,
        version: int,
        vaults: tuple[MappedVault, ...],
        projects: tuple[MappedProject, ...],
        warnings: tuple[str, ...] = (),
    ) -> None:
        self.path = path
        self.version = version
        self._vaults = vaults
        self._projects = {project.project_id: project for project in projects}
        self.warnings = warnings

    @property
    def vaults(self) -> tuple[MappedVault, ...]:
        return self._vaults

    @property
    def default_write_vaults(self) -> dict[str, str | None]:
        """Each project id with its usable default write Vault name, sorted by project id."""
        return {pid: self._projects[pid].default_write_vault for pid in sorted(self._projects)}

    def find_project(self, cwd: Path) -> MappedProjectMatch:
        root = main_worktree_root(Path(cwd))
        if root is None:
            return MappedProjectMatch(None, None, (), reason=f"{cwd} is not inside a git repository.")
        projects = self._projects

        by_root = sorted(pid for pid, entry in projects.items() if _resolve(Path(entry.root)) == root)
        if by_root:
            return self._decide(by_root, STAGE_ROOT, root)

        origin = origin_url(root)
        if origin is not None:
            wanted = normalize_remote(origin, root)
            by_remote = sorted(
                pid
                for pid, entry in projects.items()
                if entry.remote is not None and normalize_remote(entry.remote, _resolve(Path(entry.root))) == wanted
            )
            if by_remote:
                return self._decide(by_remote, STAGE_REMOTE, root)

        by_name = sorted(
            pid
            for pid, entry in projects.items()
            if pid == root.name and not (origin is not None and entry.remote is not None)
        )
        if by_name:
            return self._decide(by_name, STAGE_NAME, root)
        return MappedProjectMatch(None, None, (), reason=f"Repository {root} is not linked to a project.")

    def vaults_for(self, cwd: Path) -> tuple[MappedVault, ...]:
        return self.find_project(cwd).vaults

    def _decide(self, ids: list[str], stage: str, root: Path) -> MappedProjectMatch:
        if len(ids) > 1:
            return MappedProjectMatch(
                None,
                stage,
                (),
                candidates=tuple(ids),
                reason=f"Several projects match repository {root} by {stage}: {', '.join(ids)}.",
            )
        by_name = {vault.name: vault for vault in self._vaults}
        project = self._projects[ids[0]]
        return MappedProjectMatch(
            project.project_id,
            stage,
            # Like the router: unknown names are skipped and repeated names kept once.
            tuple(by_name[name] for name in dict.fromkeys(project.vault_names) if name in by_name),
            default_write_vault=by_name.get(project.default_write_vault) if project.default_write_vault else None,
        )


@dataclass(frozen=True)
class VaultMapOpening:
    """Result of reading a map that may be absent or damaged. ``warning`` is set only when damaged."""

    path: Path
    state: VaultMapState
    vault_map: VaultMap | None
    warning: str | None = None

    @property
    def version(self) -> int | None:
        return self.vault_map.version if self.vault_map is not None else None


def vault_map_path(explicit: Path | None = None, *, environ: Mapping[str, str] | None = None) -> Path:
    """Return the map path: the explicit option, then ``VAULT_GRAPH_VAULT_MAP``, then the default."""
    if explicit is not None:
        return explicit.expanduser()
    value = (os.environ if environ is None else environ).get(VAULT_MAP_ENV)
    if value:
        return Path(value).expanduser()
    return DEFAULT_VAULT_MAP_PATH.expanduser()


def load_vault_map(path: Path) -> VaultMap:
    """Read a version 2 map or raise ``VaultMapError``."""
    if not path.is_file():
        raise VaultMapError(f"No vault map at {path}.")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise VaultMapError(f"Vault map {path} is damaged: {exc}".replace("\n", " ")) from exc
    problem = _shape_problem(data)
    if problem is not None:
        raise VaultMapError(f"Vault map {path} is not used: {problem}")
    vaults = tuple(
        MappedVault(name=name, path=_resolve(Path(entry["path"])), role=entry["role"])
        for name, entry in sorted(data["vaults"].items())
    )
    vault_names = {vault.name for vault in vaults}
    warnings: list[str] = []
    projects = []
    for project_id, entry in data["projects"].items():
        default_write_vault, warning = _default_write_vault(project_id, entry, vault_names)
        if warning is not None:
            warnings.append(f"Vault map {path}: {warning}")
        projects.append(
            MappedProject(
                project_id=project_id,
                root=entry["root"],
                vault_names=tuple(entry["vaults"]),
                remote=entry.get("remote"),
                default_write_vault=default_write_vault,
            )
        )
    return VaultMap(
        path=path, version=data["version"], vaults=vaults, projects=tuple(projects), warnings=tuple(warnings)
    )


def _default_write_vault(project_id: str, entry: dict[str, Any], map_vaults: set[str]) -> tuple[str | None, str | None]:
    """Return the usable ``default_write_vault`` name and a warning when the field is ignored.

    A bad value drops only this field, never the whole map (vault-map-v2 contract).
    """
    if "default_write_vault" not in entry:
        return None, None
    value = entry["default_write_vault"]
    prefix = f"project {project_id} default_write_vault"
    if not isinstance(value, str):
        return None, f"{prefix} is not a string. The field is ignored."
    if value not in entry["vaults"]:
        return None, f"{prefix} {value!r} is not in the project vaults. The field is ignored."
    if value not in map_vaults:
        return None, f"{prefix} {value!r} is not listed in the map vaults. The field is ignored."
    return value, None


def open_vault_map(path: Path) -> VaultMapOpening:
    """Read the map without raising. A missing file is normal. A damaged file gives a warning."""
    if not path.exists():
        return VaultMapOpening(path=path, state="missing", vault_map=None)
    try:
        return VaultMapOpening(path=path, state="loaded", vault_map=load_vault_map(path))
    except VaultMapError as exc:
        return VaultMapOpening(path=path, state="invalid", vault_map=None, warning=str(exc))


def _shape_problem(data: Any) -> str | None:
    if not isinstance(data, dict):
        return "it must be a JSON object."
    version = data.get("version")
    if type(version) is not int or version != VAULT_MAP_VERSION:
        return f"version must be {VAULT_MAP_VERSION}."
    vaults = data.get("vaults")
    projects = data.get("projects")
    if not isinstance(vaults, dict) or not isinstance(projects, dict):
        return "vaults and projects must be objects."
    for name, entry in vaults.items():
        if not isinstance(entry, dict) or not all(isinstance(entry.get(key), str) for key in ("path", "role")):
            return f"vault {name} needs string path and role."
    for project_id, entry in projects.items():
        names = entry.get("vaults") if isinstance(entry, dict) else None
        if (
            not isinstance(entry, dict)
            or not isinstance(entry.get("root"), str)
            or not isinstance(names, list)
            or not all(isinstance(name, str) for name in names)
        ):
            return f"project {project_id} needs a string root and a vaults list."
        if "remote" in entry and not isinstance(entry["remote"], str):
            return f"project {project_id} remote must be a string."
    return None


def _git(folder: Path, *arguments: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(folder), *arguments],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    output = result.stdout.strip()
    if result.returncode != 0 or not output:
        return None
    return output


def _resolve(path: Path) -> Path:
    try:
        return path.expanduser().resolve()
    except (OSError, RuntimeError):
        return path.expanduser().absolute()


def main_worktree_root(start: Path) -> Path | None:
    """Return the main worktree root of the repository holding ``start``, or None outside git."""
    common_dir = _git(start, "rev-parse", "--path-format=absolute", "--git-common-dir")
    if common_dir is None:
        return None
    common = Path(common_dir)
    if common.name == ".git":
        return _resolve(common.parent)
    top = _git(start, "rev-parse", "--show-toplevel")
    return _resolve(Path(top)) if top else None


def origin_url(root: Path) -> str | None:
    """Return the origin URL as written in the git config, or None."""
    return _git(root, "config", "--get", "remote.origin.url")


def normalize_remote(url: str, base: Path) -> str:
    """Normalize a remote URL so the same repository compares equal.

    Host forms become ``host/path`` with a lowercase host. Local paths and ``file://`` URLs
    become absolute paths. A relative local path is read against ``base``.
    """
    text = url.strip()
    if "://" in text:
        parts = urlsplit(text)
        if parts.scheme.lower() == "file":
            return str(_resolve(Path(unquote(parts.path))))
        return _host_path(parts.hostname or "", parts.path)
    colon = text.find(":")
    if colon > 0 and "/" not in text[:colon]:
        host = text[:colon].rpartition("@")[2]
        return _host_path(host, text[colon + 1 :])
    local = Path(text).expanduser()
    if not local.is_absolute():
        local = base / local
    return str(_resolve(local))


def _host_path(host: str, path: str) -> str:
    path = path.strip("/")
    if path.endswith(".git"):
        path = path[: -len(".git")].rstrip("/")
    return f"{host.lower()}/{path}"


__all__ = [
    "DEFAULT_VAULT_MAP_PATH",
    "VAULT_MAP_ENV",
    "VAULT_MAP_VERSION",
    "MappedProject",
    "MappedProjectMatch",
    "MappedVault",
    "VaultMap",
    "VaultMapError",
    "VaultMapOpening",
    "load_vault_map",
    "main_worktree_root",
    "normalize_remote",
    "open_vault_map",
    "origin_url",
    "vault_map_path",
]
