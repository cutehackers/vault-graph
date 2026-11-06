"""Thin Typer adapter for `vg session export` (spec 2026-11-05 §4.2.4, §6 export 행).

Exports agent sessions to a folder the user chose outside every Vault: a byte copy of the source
files under ``raw/`` and the ``vg-session-jsonl/1`` file under ``normalized/``. Codex has no adapter
until backlog B-1. ``--recapture`` belongs to S6 and is not offered here.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import NoReturn

import typer

from vault_graph.errors import VaultGraphError
from vault_graph.interface.composition.adapters.session_export_files import (
    claude_config_dir,
    export_claude_code_session,
    find_claude_code_sessions,
    location_warnings,
    select_sessions,
    valid_session_id,
    vault_containing,
)
from vault_graph.operation.integration.vault_map import open_vault_map, vault_map_path
from vault_graph.operation.scope.catalog_service import CatalogService
from vault_graph.operation.scope.session_export_settings import SESSION_EXPORT_AGENTS

session_app = typer.Typer(no_args_is_help=True)

# Module-level option values keep ruff B008 satisfied without a per-file ignore.
_AGENT_OPTION = typer.Option(
    ..., "--agent", help=f"Agent whose sessions to export: {', '.join(SESSION_EXPORT_AGENTS)}."
)
_OUT_OPTION = typer.Option(..., "--out", help="Export folder. Must be outside every registered or mapped Vault.")
_SESSION_OPTION = typer.Option(None, "--session", help="Export one session by id.")
_SINCE_OPTION = typer.Option(
    None, "--since", help="Export sessions whose transcript changed on or after this ISO date or time (local time)."
)
_ALL_OPTION = typer.Option(False, "--all", help="Export every session.")
_RAW_OPTION = typer.Option(True, "--raw/--no-raw", help="Also copy the source files byte for byte, unredacted.")
_GRAPH_HOME_OPTION = typer.Option(Path.home() / ".vault-graph", "--graph-home", help="Vault Graph Data Home path.")
_VAULT_MAP_OPTION = typer.Option(
    None, "--vault-map", help="vault-map.json path. Defaults to $VAULT_GRAPH_VAULT_MAP, then the vault-builder path."
)


@session_app.command("export")
def export(
    agent: str = _AGENT_OPTION,
    out: Path = _OUT_OPTION,
    session: str | None = _SESSION_OPTION,
    since: str | None = _SINCE_OPTION,
    export_all: bool = _ALL_OPTION,
    raw: bool = _RAW_OPTION,
    state: Path = _GRAPH_HOME_OPTION,
    vault_map: Path | None = _VAULT_MAP_OPTION,
) -> None:
    """Copy agent session files and write normalized session files to a folder outside every Vault."""
    if agent not in SESSION_EXPORT_AGENTS:
        _fail(f"unsupported_agent: {agent}. Choose one of {', '.join(SESSION_EXPORT_AGENTS)}", code=2)
    if agent == "codex":
        _fail("codex_adapter_missing: Codex adapter 없음. backlog B-1 전까지는 --agent claude-code만 export한다")
    if sum((session is not None, since is not None, export_all)) != 1:
        _fail("session_selection_required: give exactly one of --session ID, --since DATE, --all", code=2)
    if session is not None and not valid_session_id(session):
        _fail(f"invalid_session_id: {session}", code=2)
    since_time = _since(since) if since is not None else None

    target = Path(out).expanduser()
    vault = vault_containing(target, _vault_roots(state, vault_map))
    if vault is not None:
        _fail(f"export_out_inside_vault: {target} is inside Vault {vault}. Nothing was written")
    for warning in location_warnings(target):
        typer.echo(f"warning: {warning}", err=True)

    found, duplicates = find_claude_code_sessions(claude_config_dir() / "projects")
    for session_id in duplicates:
        if session is None or session == session_id:
            typer.echo(f"warning: session {session_id} is in more than one project folder; skipped", err=True)
    selected = select_sessions(found, session_id=session, since=since_time)
    if session is not None and not selected:
        _fail(f"session_not_found: {session} under {claude_config_dir() / 'projects'}")

    for item in selected:
        try:
            result = export_claude_code_session(item, target, raw=raw)
        except OSError as exc:
            _fail(f"session_export_failed: {item.session_id}: {exc}")
        unknown = ",".join(f"{name}:{count}" for name, count in result.unknown_record_types.items()) or "-"
        typer.echo(
            f"{result.session_id} normalized={'written' if result.normalized_written else 'unchanged'} "
            f"raw_written={result.raw_files_written} raw_unchanged={result.raw_files_unchanged} "
            f"invalid_lines={result.invalid_lines} unknown_record_types={unknown}"
        )
    typer.echo(f"exported_sessions: {len(selected)} out: {target}")


def _vault_roots(state: Path, explicit_map: Path | None) -> list[Path]:
    roots: list[Path] = []
    graph_home = state.expanduser()
    if (graph_home / "configs" / "vaults.yaml").exists():
        try:
            catalog = CatalogService(graph_home_path=graph_home).load_catalog()
        except VaultGraphError as exc:
            _fail(f"vault_check_failed: cannot read the Graph Home Vault list: {exc}")
        roots.extend(entry.root_path for entry in catalog.entries())
    opening = open_vault_map(vault_map_path(explicit_map))
    if opening.state == "invalid":
        _fail(f"vault_check_failed: {opening.warning}. Fix vault-map.json so --out can be checked")
    if opening.vault_map is not None:
        roots.extend(vault.path for vault in opening.vault_map.vaults)
    return roots


def _since(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        _fail(f"invalid_since: {value}. Use an ISO date such as 2026-11-01", code=2)
    return parsed if parsed.tzinfo is not None else parsed.astimezone()


def _fail(message: str, *, code: int = 1) -> NoReturn:
    typer.echo(message, err=True)
    raise typer.Exit(code)
