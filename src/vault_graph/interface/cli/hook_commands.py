"""Claude Code hook entry points: ``vg hook session-start`` (spec 4.2.3, S4, S13) and
``vg hook capture`` (spec 2026-11-02 V5).

session-start: exit code 0 means handled (stdout may be empty). Exit code 3 means recall is not
possible and the hook should use ``recall.sh``. Any other code is an unexpected error. Stdout is
written only after recall finished, so a failure never leaves partial output. Before recall it
indexes changed files of the linked Vaults, metadata only, within ``--refresh-budget`` seconds
(``recall_index_refresh``). A failed refresh is a warning, never a hook failure.

Right after the change scan, before the refresh writes anything, the hook starts one detached
catch-up process, so a hook killed later by its launcher still leaves it running. The process waits
until the hook's refresh is done (or the hook is gone), then runs a normal ``vg index`` (with
embeddings) for Vaults with changed files, and for the other linked Vaults only when their vectors
are stale or missing. A catch-up that was killed is therefore run again at the next session start.
The process holds an flock on ``logs/session-start-index.lock`` while it lives. A hook that finds
the lock taken starts nothing, so session starts never pile up background runs.

capture: runs ``vault_hooks.py capture --direct`` from the ``vault-map.json`` folder with the hook
JSON unchanged. Exit code 0 means the launcher finished (written, no-new-turns and skipped alike).
Exit code 3 means the launcher was missing, failed or ran out of time, so the hook launcher
captures directly. vg never chooses the Vault, never indexes after capture and writes nothing.
"""

from __future__ import annotations

import fcntl
import json
import os
import select
import subprocess
import sys
from pathlib import Path
from time import monotonic
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
from vault_graph.interface.composition.recall_index_refresh import (
    DEFAULT_REFRESH_BUDGET_S,
    refresh_linked_vaults,
    vectors_need_catch_up,
)
from vault_graph.operation.integration.vault_map import VAULT_MAP_ENV, vault_map_path

COMMAND = "vg hook session-start"
CAPTURE_COMMAND = "vg hook capture"
CAPTURE_HANDOFF_EXIT_CODE = 3
# The hook launcher gives `vg hook capture` 25 seconds (계약6). Stop the launcher before that.
DEFAULT_CAPTURE_TIMEOUT_S = 20.0
CATCH_UP_LOG = Path("logs") / "session-start-index.log"
CATCH_UP_PID = Path("logs") / "session-start-index.pid"
CATCH_UP_LOCK = Path("logs") / "session-start-index.lock"
# Longest wait of the catch-up for the hook's refresh. The hook launcher stops the hook at 20 s.
_GATE_TIMEOUT_S = 60.0
_CATCH_UP_LOG_MAX_BYTES = 1_000_000
_CATCH_UP_SCRIPT = "from vault_graph.interface.cli.hook_commands import run_catch_up_index; run_catch_up_index()"
_VG_SCRIPT = "from vault_graph.interface.cli.main import app; app()"

# Same wording as VAULT_MAP_OPTION_HELP in main.py, which imports this module.
_VAULT_MAP_HELP = (
    f"vault-map.json path. Defaults to ${VAULT_MAP_ENV}, then $CLAUDE_CONFIG_DIR/vault-builder/vault-map.json "
    "when CLAUDE_CONFIG_DIR is set, then $HOME/.claude/vault-builder/vault-map.json."
)

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
        help=_VAULT_MAP_HELP,
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

    catch_ups: list[CatchUp] = []

    def start_catch_up(index_vault_ids: tuple[str, ...], check_vault_ids: tuple[str, ...]) -> None:
        handle = _catch_up(state, index_vault_ids, check_vault_ids)
        if handle is not None:
            catch_ups.append(handle)

    try:
        cwd, source, session_id = _read_hook_input(sys.stdin.read())
        factory = ReadOnlyServiceFactory(graph_home_path=state)
        map_path = vault_map_path(vault_map)
        ports = factory.open_session_recall(vault_map_path=map_path)
        try:
            refresh = refresh_linked_vaults(
                cwd, ports=ports, graph_home_path=state, budget_s=refresh_budget, on_scanned=start_catch_up
            )
        finally:
            # The refresh is done, so the catch-up may take the projection lock now.
            for handle in catch_ups:
                handle.release()
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


class CatchUp:
    """A started catch-up process. ``release`` lets it start indexing. Hook exit does the same."""

    def __init__(self, gate_descriptor: int) -> None:
        self._gate_descriptor: int | None = gate_descriptor

    def release(self) -> None:
        if self._gate_descriptor is not None:
            os.close(self._gate_descriptor)
            self._gate_descriptor = None


def start_catch_up_index(
    graph_home: Path, index_vault_ids: tuple[str, ...], check_vault_ids: tuple[str, ...] = ()
) -> CatchUp | None:
    """Start the catch-up in a detached process, or return None when one runs or nothing is asked.

    ``vg index --vault-id <id>`` runs for each of ``index_vault_ids``, then for each of
    ``check_vault_ids`` whose vectors are stale or missing, one after another. The process has its
    own session, reads nothing and writes to ``<graph home>/logs``, so the hook and its launcher
    never wait for it. It inherits this hook's flock on ``logs/session-start-index.lock`` and holds
    it until it ends, killed or not. A process ID left in ``logs/session-start-index.pid`` is only
    information: the lock alone decides whether a catch-up runs.

    The process waits to start indexing until the returned ``CatchUp`` is released or this process
    ends, so its ``vg index`` never takes the projection lock before the hook's own refresh.
    """

    if not index_vault_ids and not check_vault_ids:
        return None
    logs = graph_home / CATCH_UP_LOCK.parent
    logs.mkdir(parents=True, exist_ok=True)
    lock_descriptor = os.open(graph_home / CATCH_UP_LOCK, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        try:
            fcntl.flock(lock_descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return None
        gate_read, gate_write = os.pipe()
        try:
            plan = json.dumps({"index": list(index_vault_ids), "check": list(check_vault_ids)})
            log_path = graph_home / CATCH_UP_LOG
            mode = "wb" if log_path.exists() and log_path.stat().st_size > _CATCH_UP_LOG_MAX_BYTES else "ab"
            with log_path.open(mode) as log:
                process = subprocess.Popen(
                    [sys.executable, "-c", _CATCH_UP_SCRIPT, str(graph_home), str(gate_read), plan],
                    stdin=subprocess.DEVNULL,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                    close_fds=True,
                    pass_fds=(lock_descriptor, gate_read),
                )
        except BaseException:
            os.close(gate_write)
            raise
        finally:
            os.close(gate_read)
    finally:
        # The child holds the same open lock, so closing this copy keeps it locked while the child lives.
        os.close(lock_descriptor)
    (graph_home / CATCH_UP_PID).write_text(f"{process.pid}\n", encoding="utf-8")
    return CatchUp(gate_write)


def run_catch_up_index() -> None:
    """Body of the detached process: ``sys.argv`` is ``-c <graph home> <gate fd> <plan json>``."""

    graph_home, gate, plan_json = sys.argv[1:4]
    try:
        _wait_for_gate(int(gate), timeout_s=_GATE_TIMEOUT_S)
        plan = json.loads(plan_json)
        for vault_id in plan["index"]:
            _run_vg_index(graph_home, vault_id)
        for vault_id in plan["check"]:
            if vectors_need_catch_up(Path(graph_home), vault_id):
                _run_vg_index(graph_home, vault_id)
    finally:
        pid_path = Path(graph_home) / CATCH_UP_PID
        if _read_pid(pid_path) == os.getpid():
            pid_path.unlink(missing_ok=True)


def _run_vg_index(graph_home: str, vault_id: str) -> None:
    subprocess.run(
        [sys.executable, "-c", _VG_SCRIPT, "index", "--graph-home", graph_home, "--vault-id", vault_id],
        stdin=subprocess.DEVNULL,
        check=False,
    )


def _wait_for_gate(descriptor: int, *, timeout_s: float) -> bool:
    """Wait until the hook closes its end of the pipe. False when ``timeout_s`` passed first."""

    deadline = monotonic() + timeout_s
    try:
        while True:
            remaining = deadline - monotonic()
            if remaining <= 0:
                return False
            readable, _, _ = select.select([descriptor], [], [], remaining)
            if readable and not os.read(descriptor, 4096):
                return True
    finally:
        os.close(descriptor)


def _read_pid(pid_path: Path) -> int | None:
    try:
        pid = int(pid_path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None
    return pid if pid > 0 else None


def _catch_up(graph_home: Path, index_vault_ids: tuple[str, ...], check_vault_ids: tuple[str, ...]) -> CatchUp | None:
    try:
        return start_catch_up_index(graph_home, index_vault_ids, check_vault_ids)
    except OSError as exc:
        typer.echo(f"{COMMAND}: warning: cannot start the background `vg index`: {exc}.", err=True)
        return None


@hook_app.command("capture")
def capture(
    vault_map: Path | None = typer.Option(
        None,
        "--vault-map",
        help=f"{_VAULT_MAP_HELP} {LAUNCHER_NAME} is run from its folder.",
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


__all__ = ["CatchUp", "hook_app", "run_catch_up_index", "start_catch_up_index"]
