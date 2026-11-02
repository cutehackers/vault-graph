"""Claude Code hook entry points: ``vg hook session-start`` (spec 4.2.3, S4, S13) and
``vg hook capture`` (spec 2026-11-02 V5).

session-start: exit code 0 means handled (stdout may be empty). Exit code 3 means recall is not
possible and the hook should use ``recall.sh``. Any other code is an unexpected error. Stdout is
written only after recall finished, so a failure never leaves partial output. Before recall it
indexes changed files of the linked Vaults, metadata only, within ``--refresh-budget`` seconds
(``recall_index_refresh``). A failed refresh is a warning, never a hook failure. After stdout is
written, Vaults with changed files get a normal ``vg index`` (with embeddings) in a detached process,
so their vectors catch up and search by meaning comes back without the hook waiting for it.

capture: runs ``vault_hooks.py capture --direct`` from the ``vault-map.json`` folder with the hook
JSON unchanged. Exit code 0 means the launcher finished (written, no-new-turns and skipped alike).
Exit code 3 means the launcher was missing, failed or ran out of time, so the hook launcher
captures directly. vg never chooses the Vault, never indexes after capture and writes nothing.
"""

from __future__ import annotations

import json
import os
import subprocess
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
CATCH_UP_LOG = Path("logs") / "session-start-index.log"
CATCH_UP_PID = Path("logs") / "session-start-index.pid"
_CATCH_UP_LOG_MAX_BYTES = 1_000_000
_CATCH_UP_SCRIPT = "from vault_graph.interface.cli.hook_commands import run_catch_up_index; run_catch_up_index()"
_VG_SCRIPT = "from vault_graph.interface.cli.main import app; app()"

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

    catch_up: tuple[str, ...] = ()
    try:
        cwd, source, session_id = _read_hook_input(sys.stdin.read())
        factory = ReadOnlyServiceFactory(graph_home_path=state)
        map_path = vault_map_path(vault_map)
        ports = factory.open_session_recall(vault_map_path=map_path)
        refresh = refresh_linked_vaults(cwd, ports=ports, graph_home_path=state, budget_s=refresh_budget)
        catch_up = refresh.catch_up_vault_ids
        if refresh.warning:
            typer.echo(f"{COMMAND}: warning: {refresh.warning}", err=True)
        if refresh.status == "refreshed":
            # The ports read the generation that was active when they opened. Read the new one.
            ports = factory.open_session_recall(vault_map_path=map_path)
    except RecallUnavailable as exc:
        _catch_up(state, catch_up)
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
        _catch_up(state, catch_up)
        _handoff(bundle.reason or "Recall is not possible.")
    if bundle.text:
        typer.echo(bundle.text, nl=False)
    _catch_up(state, catch_up)


def start_catch_up_index(graph_home: Path, vault_ids: tuple[str, ...]) -> None:
    """Start ``vg index --vault-id <id>`` for each Vault, one after another, in a detached process.

    The process has its own session, reads nothing and writes to ``<graph home>/logs`` so the hook
    and its launcher never wait for it. Its process ID is kept in ``logs/session-start-index.pid``
    while it runs. When that process is still alive, no second one is started, so session starts
    never pile up background index runs. The next session start after it ends tries again.
    """

    pid_path = graph_home / CATCH_UP_PID
    pid_path.parent.mkdir(parents=True, exist_ok=True)
    if not _claim_pid_file(pid_path):
        return
    try:
        log_path = graph_home / CATCH_UP_LOG
        mode = "wb" if log_path.exists() and log_path.stat().st_size > _CATCH_UP_LOG_MAX_BYTES else "ab"
        with log_path.open(mode) as log:
            process = subprocess.Popen(
                [sys.executable, "-c", _CATCH_UP_SCRIPT, str(graph_home), *vault_ids],
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                close_fds=True,
            )
    except BaseException:
        pid_path.unlink(missing_ok=True)
        raise
    pid_path.write_text(f"{process.pid}\n", encoding="utf-8")


def run_catch_up_index() -> None:
    """Body of the detached process: ``sys.argv`` is ``-c <graph home> <vault id>...``."""

    graph_home, *vault_ids = sys.argv[1:]
    try:
        for vault_id in vault_ids:
            subprocess.run(
                [sys.executable, "-c", _VG_SCRIPT, "index", "--graph-home", graph_home, "--vault-id", vault_id],
                stdin=subprocess.DEVNULL,
                check=False,
            )
    finally:
        pid_path = Path(graph_home) / CATCH_UP_PID
        if _read_pid(pid_path) == os.getpid():
            pid_path.unlink(missing_ok=True)


def _claim_pid_file(pid_path: Path) -> bool:
    """Create the pid file for a new catch-up, or return False when a live catch-up holds it.

    The file is created with O_EXCL, so two session starts at once never both start a process. A
    file whose process is gone, or whose content is not a process ID, is removed and claimed again.
    Until the new process ID is written, the file holds this hook's own process ID.
    """

    for _ in range(2):
        try:
            descriptor = os.open(pid_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        except FileExistsError:
            pid = _read_pid(pid_path)
            if pid is not None and _process_alive(pid):
                return False
            pid_path.unlink(missing_ok=True)
            continue
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(f"{os.getpid()}\n")
        return True
    return False


def _read_pid(pid_path: Path) -> int | None:
    try:
        pid = int(pid_path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None
    return pid if pid > 0 else None


def _process_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _catch_up(graph_home: Path, vault_ids: tuple[str, ...]) -> None:
    if not vault_ids:
        return
    try:
        start_catch_up_index(graph_home, vault_ids)
    except OSError as exc:
        typer.echo(f"{COMMAND}: warning: cannot start the background `vg index`: {exc}.", err=True)


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


__all__ = ["hook_app", "run_catch_up_index", "start_catch_up_index"]
