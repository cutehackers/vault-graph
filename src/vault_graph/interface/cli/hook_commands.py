"""Claude Code hook entry points: ``vg hook session-start`` (spec 4.2.3, S4, S13).

Exit code 0 means handled (stdout may be empty). Exit code 3 means recall is not possible and
the hook should use ``recall.sh``. Any other code is an unexpected error. Stdout is written
only after recall finished, so a failure never leaves partial output.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import NoReturn

import typer

from vault_graph.context.pack.recall import (
    DEFAULT_RECALL_MAX_CHARS,
    DEFAULT_RECALL_MAX_TOKENS,
    RECALL_HANDOFF_EXIT_CODE,
    RecallUnavailable,
    recall,
)
from vault_graph.interface.composition.read_only_service_factory import ReadOnlyServiceFactory
from vault_graph.operation.integration.vault_map import VAULT_MAP_ENV, vault_map_path

COMMAND = "vg hook session-start"

hook_app = typer.Typer(no_args_is_help=True)


@hook_app.command("session-start")
def session_start(
    state: Path = typer.Option(
        Path.home() / ".vault-graph",
        "--graph-home",
        help="Vault Graph Data Home path.",
    ),
    vault_map: Path | None = typer.Option(
        None,
        "--vault-map",
        help=f"vault-map.json path. Defaults to ${VAULT_MAP_ENV}, then $HOME/.claude/vault-builder/vault-map.json.",
    ),
    max_tokens: int = typer.Option(
        DEFAULT_RECALL_MAX_TOKENS, "--max-tokens", min=100, help="Token limit. The 9,000 character limit stays."
    ),
) -> None:
    """Print the session start memory bundle for the SessionStart hook JSON on stdin."""

    try:
        cwd, source, session_id = _read_hook_input(sys.stdin.read())
        ports = ReadOnlyServiceFactory(graph_home_path=state).open_session_recall(
            vault_map_path=vault_map_path(vault_map)
        )
    except RecallUnavailable as exc:
        _handoff(str(exc))
    bundle = recall(
        cwd,
        source=source,
        session_id=session_id,
        max_tokens=max_tokens,
        max_chars=DEFAULT_RECALL_MAX_CHARS,
        ports=ports,
    )
    for warning in bundle.warnings:
        typer.echo(f"{COMMAND}: warning: {warning}", err=True)
    if bundle.handoff:
        _handoff(bundle.reason or "Recall is not possible.")
    if bundle.text:
        typer.echo(bundle.text, nl=False)


def _read_hook_input(raw: str) -> tuple[Path, str, str]:
    try:
        payload = json.loads(raw)
    except ValueError as exc:
        raise RecallUnavailable("SessionStart hook input is not JSON.") from exc
    if not isinstance(payload, dict):
        raise RecallUnavailable("SessionStart hook input is not a JSON object.")
    cwd = payload.get("cwd")
    source = payload.get("source")
    session_id = payload.get("session_id")
    return (
        Path(cwd) if isinstance(cwd, str) and cwd else Path.cwd(),
        source if isinstance(source, str) else "",
        session_id if isinstance(session_id, str) else "",
    )


def _handoff(reason: str) -> NoReturn:
    typer.echo(f"{COMMAND}: {reason}", err=True)
    raise typer.Exit(RECALL_HANDOFF_EXIT_CODE)


__all__ = ["hook_app"]
