"""Claude Code hook entry points: ``vg hook session-start`` (spec 4.2.3, S4, S13) and
``vg hook capture`` (spec 2026-11-02 V5).

session-start: exit code 0 means handled (stdout may be empty). Exit code 3 means recall is not
possible and the hook should use ``recall.sh``. Any other code is an unexpected error. Stdout is
written only after recall finished, so a failure never leaves partial output. Before recall it
indexes changed files of the linked Vaults, metadata only, within ``--refresh-budget`` seconds
(``recall_index_refresh``). A failed refresh is a warning, never a hook failure.

capture: runs ``vault_hooks.py capture --direct`` from the ``vault-map.json`` folder with the hook
JSON unchanged. Exit code 0 means the launcher finished (written, no-new-turns and skipped alike).
Exit code 3 means the launcher was missing, failed or ran out of time, so the hook launcher
captures directly. vg never chooses the Vault, never indexes after capture and writes nothing.
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
from vault_graph.interface.composition.adapters.vault_capture_cli import LAUNCHER_NAME, run_capture
from vault_graph.interface.composition.read_only_service_factory import ReadOnlyServiceFactory
from vault_graph.interface.composition.recall_index_refresh import DEFAULT_REFRESH_BUDGET_S, refresh_linked_vaults
from vault_graph.operation.integration.vault_map import VAULT_MAP_ENV, vault_map_path

COMMAND = "vg hook session-start"
CAPTURE_COMMAND = "vg hook capture"
CAPTURE_HANDOFF_EXIT_CODE = 3
# The hook launcher gives `vg hook capture` 25 seconds (계약6). Stop the launcher before that.
DEFAULT_CAPTURE_TIMEOUT_S = 20.0

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
    refresh_budget: float = typer.Option(
        DEFAULT_REFRESH_BUDGET_S,
        "--refresh-budget",
        min=0.0,
        help="Seconds to bring the linked Vaults' metadata index up to date before recall. 0 skips it.",
    ),
) -> None:
    """Print the session start memory bundle for the SessionStart hook JSON on stdin.

    Before recall, changed files of the linked, indexed Vaults are indexed (metadata only, no
    embeddings). A refresh that fails or runs out of time prints one warning and recall reads the
    existing index.
    """

    try:
        cwd, source, session_id = _read_hook_input(sys.stdin.read())
        factory = ReadOnlyServiceFactory(graph_home_path=state)
        map_path = vault_map_path(vault_map)
        ports = factory.open_session_recall(vault_map_path=map_path)
        refresh = refresh_linked_vaults(cwd, ports=ports, graph_home_path=state, budget_s=refresh_budget)
        if refresh.warning:
            typer.echo(f"{COMMAND}: warning: {refresh.warning}", err=True)
        if refresh.status == "refreshed":
            # The ports read the generation that was active when they opened. Read the new one.
            ports = factory.open_session_recall(vault_map_path=map_path)
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


@hook_app.command("capture")
def capture(
    vault_map: Path | None = typer.Option(
        None,
        "--vault-map",
        help=(
            f"vault-map.json path. {LAUNCHER_NAME} is run from its folder. "
            f"Defaults to ${VAULT_MAP_ENV}, then $HOME/.claude/vault-builder/vault-map.json."
        ),
    ),
    timeout: float = typer.Option(
        DEFAULT_CAPTURE_TIMEOUT_S, "--timeout", min=0.1, help="Seconds before the launcher is stopped."
    ),
) -> None:
    """Hand the PreCompact or SessionEnd hook JSON on stdin to the Vault hook launcher."""

    hook_json = sys.stdin.buffer.read()
    launcher = vault_map_path(vault_map).parent / LAUNCHER_NAME
    outcome = run_capture(hook_json, launcher=launcher, timeout_s=timeout)
    if outcome.stderr:
        typer.echo(outcome.stderr, err=True, nl=not outcome.stderr.endswith("\n"))
    if not outcome.finished:
        typer.echo(f"{CAPTURE_COMMAND}: {outcome.problem}", err=True)
        raise typer.Exit(CAPTURE_HANDOFF_EXIT_CODE)
    typer.echo(
        f"{CAPTURE_COMMAND}: status={outcome.status} vault={outcome.vault or '-'} path={outcome.path or '-'}",
        err=True,
    )


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
