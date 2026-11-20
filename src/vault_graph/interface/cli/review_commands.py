"""Thin Typer adapter for reviewing memory proposals: `vg review [list|show|accept|reject]` (spec 2026-11-20 D1-D8).

A proposal is a ``memory-proposal`` item in the review queue (``scratch/review/``) of a Vault linked to the project
folder in ``vault-map.json``. Every linked Vault is read, registered in the Graph Home or not (D3).

- `vg review` shows the pending proposals one by one and asks accept, reject, skip or quit. It asks only when
  standard input and standard output are both a terminal. Anywhere else it prints the list and exits 0 (D5, F6).
- `list` and `show` only read. Skip and quit change nothing either (I4).
- `accept` and `reject` run the Vault's own ``review resolve`` through ``VaultReviewCli``. This module is the only
  importer of that adapter (I2), and it never writes a Vault file itself (I1). "accepted" or "rejected" is printed
  only when the Vault answered ``resolved`` (I5). Any other answer is a failure with exit code 1.
- An accept whose ``status`` was set by hand (unpublished) or whose draft cannot be read never reaches the Vault
  (F1, F9). Reject needs a reason. Accept has a default reason (D6).
- After a run that published something, the index of those Vaults starts once in a detached process and the
  command does not wait for it. When it cannot start, or the Vault is not registered, the command prints how to
  index by hand and still exits 0 (D8, F10).

With ``VAULT_GRAPH_FACTS_CHILD=1`` (the Claude session of the fact extractor or the dream judge) every command here
reads nothing, runs nothing and exits 1 (D5, F7).
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

import typer

from vault_graph.errors import VaultGraphError
from vault_graph.interface.cli.hook_commands import FACTS_CHILD_ENV, start_catch_up_index
from vault_graph.interface.composition.adapters.vault_review_cli import (
    TARGET_CHANGED_REASON,
    ResolveStatus,
    ReviewResolveOutcome,
    VaultReviewCli,
)
from vault_graph.interface.composition.adapters.vault_review_queue import (
    MEMORY_PROPOSAL_TYPE,
    REVIEW_QUEUE,
    UNPUBLISHED_FIX,
    ReviewItemState,
    review_item_state,
)
from vault_graph.interface.composition.query_scope_resolution import registered_vault_ids
from vault_graph.operation.integration.vault_map import open_vault_map, vault_map_path
from vault_graph.operation.memory.proposal_change import ProposalChange, build_proposal_change, render_proposal_change
from vault_graph.operation.scope.catalog_service import CatalogService
from vault_graph.operation.scope.graph_home import GraphHomeResolver
from vault_graph.operation.scope.vault_frontmatter import parse_vault_frontmatter, split_frontmatter
from vault_graph.project.context.project_binding_reader import MappedVault

review_app = typer.Typer(invoke_without_command=True)

DEFAULT_ACCEPT_REASON = "Accepted in vg review."
DRAFT_SUFFIX = ".draft.json"
CHILD_REFUSAL = (
    f"review: refused. {FACTS_CHILD_ENV}=1 marks a fact extraction or dream session. Only a person reviews proposals."
)
NO_PENDING = "No pending proposals."
NEEDS_TERMINAL = (
    "Interactive review needs a terminal. Run `vg review` in a terminal, "
    "or use `vg review show ID`, `vg review accept ID` and `vg review reject ID --reason TEXT`."
)
DRAFT_UNREADABLE = "draft cannot be read"

# Module-level option values keep ruff B008 satisfied without a per-file ignore.
_CWD_OPTION = typer.Option(
    None, "--cwd", help="Project folder whose linked Vaults are reviewed. Default: the current folder."
)
_GRAPH_HOME_OPTION = typer.Option(None, "--graph-home", help="Vault Graph Data Home path. Default: $HOME/.vault-graph.")
_VAULT_MAP_OPTION = typer.Option(None, "--vault-map", help="vault-map.json path. Default: the usual lookup.")
_VAULT_OPTION = typer.Option(None, "--vault", help="Vault name, needed when the same ID is in two linked Vaults.")
_ACCEPT_REASON_OPTION = typer.Option(DEFAULT_ACCEPT_REASON, "--reason", help="Why the proposal is accepted.")
_REJECT_REASON_OPTION = typer.Option(..., "--reason", help="Why the proposal is rejected. Required.")
_ID_ARGUMENT = typer.Argument(..., metavar="ID", help="The proposal's review_id, as `vg review list` prints it.")


@dataclass(frozen=True)
class _Options:
    cwd: Path | None = None
    graph_home: Path | None = None
    vault_map: Path | None = None


@dataclass(frozen=True)
class ReviewProposal:
    """One ``memory-proposal`` item as read from a Vault review queue.

    ``change`` is what accepting would change. It is None when the draft cannot be read, and ``draft_problem``
    then says why.
    """

    vault: MappedVault
    review_id: str
    review_path: str
    state: ReviewItemState
    target_path: str
    summary: str
    created: str
    change: ProposalChange | None
    draft_problem: str | None


@dataclass(frozen=True)
class _Queue:
    """What the linked Vaults hold: every memory proposal, and per Vault the pending items of other types."""

    graph_home: Path
    vaults: tuple[MappedVault, ...]
    proposals: tuple[ReviewProposal, ...]
    other_pending: tuple[tuple[str, int], ...]

    @property
    def pending(self) -> tuple[ReviewProposal, ...]:
        return tuple(proposal for proposal in self.proposals if proposal.state == "pending")

    @property
    def unpublished(self) -> tuple[ReviewProposal, ...]:
        return tuple(proposal for proposal in self.proposals if proposal.state == "unpublished")


@dataclass
class _Tally:
    accepted: int = 0
    rejected: int = 0
    skipped: int = 0
    failed: int = 0


@review_app.callback()
def review(
    ctx: typer.Context,
    cwd: Path | None = _CWD_OPTION,
    state: Path | None = _GRAPH_HOME_OPTION,
    vault_map: Path | None = _VAULT_MAP_OPTION,
) -> None:
    """Read the memory proposals of the project's linked Vaults and accept or reject them."""
    if os.environ.get(FACTS_CHILD_ENV) == "1":
        typer.echo(CHILD_REFUSAL)
        raise typer.Exit(1)
    ctx.obj = _Options(cwd, state, vault_map)
    if ctx.invoked_subcommand is not None:
        return
    queue = _open_queue(ctx.obj)
    if not _is_terminal():
        _echo_list(queue)
        if queue.pending:
            typer.echo(NEEDS_TERMINAL)
        return
    _review_interactively(queue)


@review_app.command("list")
def list_proposals(
    ctx: typer.Context,
    cwd: Path | None = _CWD_OPTION,
    state: Path | None = _GRAPH_HOME_OPTION,
    vault_map: Path | None = _VAULT_MAP_OPTION,
) -> None:
    """List pending proposals, accepts that were never published, and the count of other review items."""
    _echo_list(_open_queue(_options(ctx, cwd, state, vault_map)))


@review_app.command("show")
def show(
    ctx: typer.Context,
    review_id: str = _ID_ARGUMENT,
    vault: str | None = _VAULT_OPTION,
    cwd: Path | None = _CWD_OPTION,
    state: Path | None = _GRAPH_HOME_OPTION,
    vault_map: Path | None = _VAULT_MAP_OPTION,
) -> None:
    """Show one proposal: its Vault, target page, summary, the text it changes and its evidence."""
    queue = _open_queue(_options(ctx, cwd, state, vault_map))
    _echo_proposal(_find(queue, review_id, vault))


@review_app.command("accept")
def accept(
    ctx: typer.Context,
    review_id: str = _ID_ARGUMENT,
    reason: str = _ACCEPT_REASON_OPTION,
    vault: str | None = _VAULT_OPTION,
    cwd: Path | None = _CWD_OPTION,
    state: Path | None = _GRAPH_HOME_OPTION,
    vault_map: Path | None = _VAULT_MAP_OPTION,
) -> None:
    """Accept one proposal. The Vault publishes it, then its index starts in the background."""
    resolution = reason.strip() or DEFAULT_ACCEPT_REASON
    queue = _open_queue(_options(ctx, cwd, state, vault_map))
    proposal = _find(queue, review_id, vault)
    problem = _not_resolvable(proposal, "accepted")
    if problem is not None:
        typer.echo(problem)
        raise typer.Exit(1)
    published: list[MappedVault] = []
    resolved = _resolve(proposal, "accepted", resolution, published)
    _start_index(queue.graph_home, published)
    if not resolved:
        raise typer.Exit(1)


@review_app.command("reject")
def reject(
    ctx: typer.Context,
    review_id: str = _ID_ARGUMENT,
    reason: str = _REJECT_REASON_OPTION,
    vault: str | None = _VAULT_OPTION,
    cwd: Path | None = _CWD_OPTION,
    state: Path | None = _GRAPH_HOME_OPTION,
    vault_map: Path | None = _VAULT_MAP_OPTION,
) -> None:
    """Reject one proposal. Nothing is published."""
    if not reason.strip():
        raise typer.BadParameter("A reject needs a reason that is not blank.", param_hint="--reason")
    queue = _open_queue(_options(ctx, cwd, state, vault_map))
    proposal = _find(queue, review_id, vault)
    problem = _not_resolvable(proposal, "rejected")
    if problem is not None:
        typer.echo(problem)
        raise typer.Exit(1)
    if not _resolve(proposal, "rejected", reason.strip(), []):
        raise typer.Exit(1)


def _options(ctx: typer.Context, cwd: Path | None, state: Path | None, vault_map: Path | None) -> _Options:
    """The command's own options, else the ones given before the command name (`vg review --cwd X list`)."""
    group = ctx.obj if isinstance(ctx.obj, _Options) else _Options()
    return _Options(cwd or group.cwd, state or group.graph_home, vault_map or group.vault_map)


def _is_terminal() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def _open_queue(options: _Options) -> _Queue:
    """Read the review queue of every Vault linked to the project folder, or exit 1 when there is none (F8)."""
    cwd = options.cwd or Path.cwd()
    map_path = vault_map_path(options.vault_map)
    opening = open_vault_map(map_path)
    if opening.vault_map is None:
        why = opening.warning or f"No vault map at {map_path}."
        typer.echo(f"review: no linked Vault. {why} Run `vg setup` to link the project to a Vault.")
        raise typer.Exit(1)
    match = opening.vault_map.find_project(cwd)
    if not match.vaults:
        why = match.reason or f"The project of {cwd} has no Vault in {map_path}."
        typer.echo(f"review: no linked Vault. {why} Run `vg setup` to link the project to a Vault.")
        raise typer.Exit(1)
    vaults = tuple(sorted(match.vaults, key=lambda vault: vault.name))
    proposals: list[ReviewProposal] = []
    other_pending: list[tuple[str, int]] = []
    for vault in vaults:
        found, other = _read_vault(vault)
        proposals.extend(found)
        if other:
            other_pending.append((vault.name, other))
    return _Queue(
        graph_home=options.graph_home or Path.home() / ".vault-graph",
        vaults=vaults,
        proposals=tuple(proposals),
        other_pending=tuple(other_pending),
    )


def _read_vault(vault: MappedVault) -> tuple[list[ReviewProposal], int]:
    """Memory proposals of one Vault in ``review_id`` order, and how many pending items of other types it holds."""
    queue = vault.path / REVIEW_QUEUE
    proposals: list[ReviewProposal] = []
    other_pending = 0
    if not queue.is_dir():
        return proposals, other_pending
    for item in sorted(queue.glob("*.md")):
        try:
            block = split_frontmatter(item.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        if block is None:
            continue
        fields = parse_vault_frontmatter(block[0])
        if fields.get("type") != MEMORY_PROPOSAL_TYPE:
            other_pending += fields.get("status") == "pending"
            continue
        review_path = (REVIEW_QUEUE / item.name).as_posix()
        change, problem = _read_change(vault.path, item.stem)
        target = fields.get("target_path")
        proposals.append(
            ReviewProposal(
                vault=vault,
                review_id=item.stem,
                review_path=review_path,
                state=review_item_state(vault.path, review_path),
                target_path=str(target) if target else (change.path if change is not None else "-"),
                summary=str(fields.get("summary") or ""),
                created=str(fields.get("created") or "-"),
                change=change,
                draft_problem=problem,
            )
        )
    return proposals, other_pending


def _read_change(vault_root: Path, review_id: str) -> tuple[ProposalChange | None, str | None]:
    """Read the draft copy and the current target page. Returns the change, or None and why the draft is unusable."""
    draft_name = (REVIEW_QUEUE / f"{review_id}{DRAFT_SUFFIX}").as_posix()
    draft_file = vault_root / draft_name
    if not draft_file.is_file():
        return None, f"{draft_name} is missing."
    try:
        draft = json.loads(draft_file.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        return None, f"{draft_name} is not JSON: {' '.join(str(exc).split())}"
    if not isinstance(draft, dict):
        return None, f"{draft_name} is not a JSON object."
    current_text: str | None = None
    path = draft.get("path")
    if isinstance(path, str) and path:
        target = (vault_root / path).resolve()
        if not target.is_relative_to(vault_root.resolve()):
            return None, f"The draft target {path} is outside the Vault."
        if target.is_file():
            try:
                current_text = target.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                return None, f"The target page {path} cannot be read: {exc}"
    try:
        return build_proposal_change(draft, current_text), None
    except ValueError as exc:
        return None, str(exc)


def _find(queue: _Queue, review_id: str, vault_name: str | None) -> ReviewProposal:
    """The proposal with this ID, or exit 1: no such ID, an unknown Vault name, or the ID in two Vaults (F8)."""
    if vault_name is not None and vault_name not in {vault.name for vault in queue.vaults}:
        linked = ", ".join(vault.name for vault in queue.vaults)
        typer.echo(f"review: Vault {vault_name} is not linked to this project. Linked Vaults: {linked}.")
        raise typer.Exit(1)
    matches = [
        proposal
        for proposal in queue.proposals
        if proposal.review_id == review_id and vault_name in (None, proposal.vault.name)
    ]
    if not matches:
        where = f"Vault {vault_name}" if vault_name is not None else "the linked Vaults"
        typer.echo(f"review: no proposal with ID {review_id} in {where}. Run `vg review list` to see the IDs.")
        raise typer.Exit(1)
    if len(matches) > 1:
        names = ", ".join(proposal.vault.name for proposal in matches)
        typer.echo(f"review: ID {review_id} is in several Vaults: {names}. Pass --vault NAME to pick one.")
        raise typer.Exit(1)
    return matches[0]


def _not_resolvable(proposal: ReviewProposal, status: ResolveStatus) -> str | None:
    """Why this proposal is not sent to the Vault, or None when it may be (F1, F9)."""
    label = _label(proposal)
    if proposal.state == "unpublished":
        return (
            f"review: {label} is marked accepted but nothing was published, so the Vault would refuse it. "
            f"To fix: {UNPUBLISHED_FIX}."
        )
    if proposal.state != "pending":
        return f"review: {label} is already {proposal.state}. Only a pending proposal can be accepted or rejected."
    if status == "accepted" and proposal.change is None:
        return (
            f"review: {label} is not accepted: {DRAFT_UNREADABLE} ({proposal.draft_problem}) "
            "The text it would change cannot be shown. Reject it with `vg review reject` or leave it."
        )
    return None


def _resolve(proposal: ReviewProposal, status: ResolveStatus, resolution: str, published: list[MappedVault]) -> bool:
    """Run the Vault's ``review resolve`` and print what the Vault answered. True only for ``resolved`` (I5)."""
    return _run_resolve(proposal, status, resolution, published).status == "resolved"


def _run_resolve(
    proposal: ReviewProposal, status: ResolveStatus, resolution: str, published: list[MappedVault]
) -> ReviewResolveOutcome:
    """As ``_resolve``, returning the Vault's outcome so the caller can read why it failed."""
    outcome = VaultReviewCli().resolve(proposal.vault.path, proposal.review_path, status=status, resolution=resolution)
    label = _label(proposal)
    if outcome.status == "resolved":
        typer.echo(f"{status}: {label} {proposal.target_path}")
        if status == "accepted" and outcome.written_paths:
            typer.echo(f"published: {', '.join(outcome.written_paths)}")
            if proposal.vault not in published:
                published.append(proposal.vault)
        return outcome
    reason = f" ({outcome.reason})" if outcome.reason else ""
    typer.echo(f"failed: {label} was not {status}{reason}")
    for line in (*outcome.messages, *outcome.guidance):
        typer.echo(f"  {line}")
    return outcome


def _start_index(graph_home: Path, published: list[MappedVault]) -> None:
    """Start one detached index run for the Vaults that published, without waiting. Never changes the exit code."""
    if not published:
        return
    try:
        descriptor = GraphHomeResolver().require_initialized(graph_home)
        catalog = CatalogService(graph_home_path=descriptor.root_path).load_catalog()
    except (VaultGraphError, OSError):
        vault_ids: tuple[str, ...] = ()
        unregistered = tuple(published)
    else:
        graph_home = descriptor.root_path
        vault_ids, unregistered = registered_vault_ids(tuple(published), catalog)
    for vault in unregistered:
        typer.echo(
            f"index: Vault {vault.name} is not registered in the Graph Home, so the accepted memory is not indexed. "
            "Run `vg setup` to register it, then `vg index --vault-id ID` with its registered ID."
        )
    if not vault_ids:
        return
    try:
        catch_up = start_catch_up_index(graph_home, vault_ids)
    except OSError as exc:
        typer.echo(f"index: the background index could not start: {exc}")
        catch_up = None
    if catch_up is None:
        for vault_id in vault_ids:
            typer.echo(
                f"index: not started for {vault_id}. Another background index may be running. "
                f"Run `vg index --vault-id {vault_id}` to make the accepted memory searchable."
            )
        return
    # The detached process waits for this gate. Nothing here indexes first, so it is opened at once.
    catch_up.release()
    typer.echo(f"index: started in the background for {', '.join(vault_ids)}")


def _review_interactively(queue: _Queue) -> None:
    """Show each pending proposal in Vault name then ID order and ask what to do with it (D2)."""
    pending = queue.pending
    if not pending:
        _echo_list(queue)
        return
    tally = _Tally()
    published: list[MappedVault] = []
    for position, proposal in enumerate(pending, start=1):
        typer.echo("")
        typer.echo(f"proposal {position} of {len(pending)}")
        _echo_proposal(proposal)
        if not _ask(proposal, tally, published):
            break
    typer.echo(_tally_line(tally))
    _start_index(queue.graph_home, published)
    if tally.failed:
        raise typer.Exit(1)


def _ask(proposal: ReviewProposal, tally: _Tally, published: list[MappedVault]) -> bool:
    """Ask until this proposal is accepted, rejected or skipped. False means quit."""
    while True:
        try:
            choice = typer.prompt("[a]ccept, [r]eject, [s]kip, [q]uit", default="", show_default=False).strip().lower()
        except typer.Abort:
            typer.echo("")
            return False
        if choice in {"q", "quit"}:
            return False
        if choice in {"s", "skip"}:
            tally.skipped += 1
            return True
        if choice in {"a", "accept"}:
            problem = _not_resolvable(proposal, "accepted")
            if problem is not None:
                typer.echo(problem)
                continue
            outcome = _run_resolve(proposal, "accepted", DEFAULT_ACCEPT_REASON, published)
            if outcome.status != "resolved" and outcome.reason == TARGET_CHANGED_REASON:
                # F2: the page changed after the proposal. Ask again here, so the person can reject it now.
                # The refused accept is still a failure of this run (I5), whatever is chosen next.
                tally.failed += 1
                continue
            _count(tally, "accepted", outcome.status == "resolved")
            return True
        if choice in {"r", "reject"}:
            try:
                reason = typer.prompt("Reason", default="", show_default=False).strip()
            except typer.Abort:
                typer.echo("")
                return False
            if not reason:
                typer.echo("Not rejected: a reject needs a reason.")
                continue
            _count(tally, "rejected", _resolve(proposal, "rejected", reason, published))
            return True


def _count(tally: _Tally, status: ResolveStatus, resolved: bool) -> None:
    if not resolved:
        tally.failed += 1
    elif status == "accepted":
        tally.accepted += 1
    else:
        tally.rejected += 1


def _tally_line(tally: _Tally) -> str:
    line = f"review: accepted={tally.accepted} rejected={tally.rejected} skipped={tally.skipped}"
    return f"{line} failed={tally.failed}" if tally.failed else line


def _echo_list(queue: _Queue) -> None:
    pending = queue.pending
    if not pending:
        typer.echo(NO_PENDING)
    for proposal in pending:
        line = f"{_label(proposal)} {proposal.target_path} created={proposal.created} {proposal.summary}"
        if proposal.change is None:
            line += f" ({DRAFT_UNREADABLE}: {proposal.draft_problem})"
        typer.echo(line)
    unpublished = queue.unpublished
    if unpublished:
        typer.echo(f"unpublished accepts: {len(unpublished)}")
    for proposal in unpublished:
        typer.echo(
            f"unpublished: {_label(proposal)} {proposal.vault.path / proposal.review_path} is marked accepted "
            f"but nothing was published. To fix: {UNPUBLISHED_FIX}."
        )
    for vault_name, count in queue.other_pending:
        typer.echo(f"other pending review items in {vault_name}: {count} (not handled by vg review)")


def _echo_proposal(proposal: ReviewProposal) -> None:
    typer.echo(f"vault: {proposal.vault.name}")
    typer.echo(f"id: {proposal.review_id}")
    typer.echo(f"state: {proposal.state}")
    typer.echo(f"target: {proposal.target_path}")
    typer.echo(f"summary: {proposal.summary}")
    typer.echo(f"created: {proposal.created}")
    if proposal.change is None:
        typer.echo(f"{DRAFT_UNREADABLE}: {proposal.draft_problem}")
        return
    for line in render_proposal_change(proposal.change):
        typer.echo(line)


def _label(proposal: ReviewProposal) -> str:
    return f"[{proposal.vault.name}] {proposal.review_id}"
