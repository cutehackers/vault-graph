"""The six MCP tools that write Vault memory: ``remember``, ``update_memory``, ``retire_memory``,
``import_auto_memory``, ``supersede_claim`` and ``restore_memory`` (spec 2026-11-05 §4.4.4, §4.4.5, §4.4.13).

Split from ``mcp_tools`` (정리 발견1). Every write runs through the M18 ``MemoryWriteService`` that the
service factory opens, so this module never writes a Vault file. A ``published`` write starts a
background index of that Vault (finding F1). Each tool takes an optional ``candidate_key``: the write
service records it in the Graph Home review log when the result is ``published`` or ``proposed``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Literal, Protocol, cast

from vault_graph.interface.mcp.mcp_service_factory import McpServiceFactory
from vault_graph.interface.mcp.mcp_tool_body import (
    McpToolBody,
    McpToolName,
    McpToolServer,
    invalid_arguments,
    map_tool_exception,
    tool_body,
)

MemoryBasis = Literal["stated", "inferred"]
PageKind = Literal["decision", "system"]
MemoryKind = Literal["rule", "correction", "decision", "preference"]


@dataclass(frozen=True)
class RememberInput:
    title: str
    kind: str
    body: str
    evidence: tuple[str, ...]
    basis: str
    cwd: str | None = None
    vault: str | None = None
    pin: bool = False
    memory_kind: str | None = None
    candidate_key: str | None = None


@dataclass(frozen=True)
class UpdateMemoryInput:
    path: str
    body: str
    evidence: tuple[str, ...]
    basis: str
    vault: str | None = None
    cwd: str | None = None
    title: str | None = None
    pin: bool | None = None
    memory_kind: str | None = None
    candidate_key: str | None = None


@dataclass(frozen=True)
class RetireMemoryInput:
    path: str
    reason: str
    basis: str
    vault: str | None = None
    cwd: str | None = None
    replaced_by: str | None = None
    candidate_key: str | None = None


@dataclass(frozen=True)
class SupersedeClaimInput:
    path: str
    claim: str
    new_claim: str
    evidence: str
    basis: str
    cwd: str | None = None
    vault: str | None = None
    candidate_key: str | None = None


@dataclass(frozen=True)
class RestoreMemoryInput:
    path: str
    reason: str
    basis: str
    cwd: str | None = None
    vault: str | None = None
    candidate_key: str | None = None


@dataclass(frozen=True)
class ImportAutoMemoryInput:
    note: str
    cwd: str | None = None
    vault: str | None = None
    candidate_key: str | None = None


class McpMemoryTools:
    """Run the six write tools. ``on_index_finished`` receives whether the background index published."""

    def __init__(self, *, service_factory: McpServiceFactory, on_index_finished: Callable[[bool], None]) -> None:
        self._service_factory = service_factory
        self._on_index_finished = on_index_finished

    def remember(self, request: RememberInput) -> McpToolBody:
        """Add one new memory page through the Vault publish-draft (spec 2026-11-02 V3)."""

        from vault_graph.operation.memory.memory_requests import RememberRequest

        cwd = _write_cwd(request.cwd)
        return self._memory_write(
            "remember",
            lambda service: service.remember(
                RememberRequest(
                    title=request.title,
                    kind=request.kind,
                    body=request.body,
                    evidence=request.evidence,
                    basis=cast(Any, request.basis),
                    cwd=cwd,
                    vault=request.vault,
                    pin=request.pin,
                    memory_kind=request.memory_kind,
                    project_id=_project_id(cwd),
                    candidate_key=request.candidate_key,
                )
            ),
        )

    def update_memory(self, request: UpdateMemoryInput) -> McpToolBody:
        """Replace the body of one existing memory page through the Vault publish-draft."""

        from vault_graph.operation.memory.memory_requests import UpdateRequest

        return self._memory_write(
            "update_memory",
            lambda service: service.update(
                UpdateRequest(
                    path=request.path,
                    body=request.body,
                    evidence=request.evidence,
                    basis=cast(Any, request.basis),
                    vault=request.vault,
                    cwd=_write_cwd(request.cwd),
                    title=request.title,
                    pin=request.pin,
                    memory_kind=request.memory_kind,
                    candidate_key=request.candidate_key,
                )
            ),
        )

    def retire_memory(self, request: RetireMemoryInput) -> McpToolBody:
        """Retire one existing memory page through the Vault publish-draft. The file stays in the Vault."""

        from vault_graph.operation.memory.memory_requests import RetireRequest

        return self._memory_write(
            "retire_memory",
            lambda service: service.retire(
                RetireRequest(
                    path=request.path,
                    reason=request.reason,
                    basis=cast(Any, request.basis),
                    vault=request.vault,
                    cwd=_write_cwd(request.cwd),
                    replaced_by=request.replaced_by,
                    candidate_key=request.candidate_key,
                )
            ),
        )

    def supersede_claim(self, request: SupersedeClaimInput) -> McpToolBody:
        """Replace one claim row of a page with a ``patch-page`` ``supersede-claim`` edit (spec §4.4.4)."""

        from vault_graph.operation.memory.memory_requests import SupersedeClaimRequest

        return self._memory_write(
            "supersede_claim",
            lambda service: service.supersede_claim(
                SupersedeClaimRequest(
                    path=request.path,
                    claim=request.claim,
                    new_claim=request.new_claim,
                    evidence=request.evidence,
                    basis=cast(Any, request.basis),
                    vault=request.vault,
                    cwd=_write_cwd(request.cwd),
                    candidate_key=request.candidate_key,
                )
            ),
        )

    def restore_memory(self, request: RestoreMemoryInput) -> McpToolBody:
        """Make a retired page current again through the Vault publish-draft (spec §4.4.13-3)."""

        from vault_graph.operation.memory.memory_requests import RestoreRequest

        return self._memory_write(
            "restore_memory",
            lambda service: service.restore(
                RestoreRequest(
                    path=request.path,
                    reason=request.reason,
                    basis=cast(Any, request.basis),
                    vault=request.vault,
                    cwd=_write_cwd(request.cwd),
                    candidate_key=request.candidate_key,
                )
            ),
        )

    def import_auto_memory(self, request: ImportAutoMemoryInput) -> McpToolBody:
        """Have the Vault keep a copy of one auto-memory note with its ``import-source`` (path 4, spec §4.4.5)."""

        from vault_graph.operation.memory.memory_requests import ImportRequest

        return self._memory_write(
            "import_auto_memory",
            lambda service: service.import_auto_memory(
                ImportRequest(
                    note=request.note,
                    cwd=_write_cwd(request.cwd),
                    vault=request.vault,
                    candidate_key=request.candidate_key,
                )
            ),
        )

    def _memory_write(self, tool_name: McpToolName, run: Callable[[Any], Any]) -> McpToolBody:
        """Run one Vault memory write. Every outcome, including rejected, is a payload, not a protocol error."""

        try:
            from vault_graph.interface.mcp.mcp_tool_serialization import memory_write_result_to_payload

            result = self._index_after_publish(run(self._service_factory.open_memory_write_service()))
            return tool_body(
                tool_name=tool_name,
                payload=memory_write_result_to_payload(result),
                resource_links=(),
                warnings=(),
            )
        except Exception as exc:
            raise map_tool_exception(exc, service_factory=self._service_factory) from exc

    def _index_after_publish(self, result: Any) -> Any:
        """Start a background index of the Vault a ``published`` write changed (spec V3, finding F1).

        The tool result never waits for the index run and never fails because of it. When the index
        cannot start, the result keeps the message that asks for ``vg index``.
        """
        from vault_graph.operation.memory.memory_write_service import NEXT_INDEX_MESSAGE

        if result.status != "published" or result.vault is None:
            return result
        try:
            start = self._service_factory.start_background_index
            vault_id = start(result.vault, on_finished=self._on_index_finished)
        except Exception:  # noqa: BLE001 - indexing is optional; the Vault write already succeeded.
            return result
        if vault_id is None:
            return result
        messages = tuple(
            background_index_message(result.vault) if message == NEXT_INDEX_MESSAGE else message
            for message in result.messages
        )
        return replace(result, messages=messages)


class MemoryToolRunner(Protocol):
    def remember(self, request: RememberInput) -> McpToolBody: ...

    def update_memory(self, request: UpdateMemoryInput) -> McpToolBody: ...

    def retire_memory(self, request: RetireMemoryInput) -> McpToolBody: ...

    def import_auto_memory(self, request: ImportAutoMemoryInput) -> McpToolBody: ...

    def supersede_claim(self, request: SupersedeClaimInput) -> McpToolBody: ...

    def restore_memory(self, request: RestoreMemoryInput) -> McpToolBody: ...


def register_memory_tools(server: McpToolServer, registry: MemoryToolRunner) -> None:
    """Register the six write tools on ``server``. Each one parses its arguments and calls ``registry``."""

    @server.tool("remember", structured_output=True)
    def remember(
        title: str,
        kind: PageKind,
        body: str,
        evidence: list[str],
        basis: MemoryBasis,
        cwd: str | None = None,
        vault: str | None = None,
        pin: bool = False,
        memory_kind: MemoryKind | None = None,
        candidate_key: str | None = None,
    ) -> dict[str, object]:
        """Add one new memory page to a Vault. To change an existing page use update_memory.

        ``kind`` is the page type and folder: ``decision`` (wiki/decisions/) or ``system`` (wiki/systems/).
        ``memory_kind`` is optional and says what sort of memory it is: ``rule``, ``correction``, ``decision``
        or ``preference``. It does not choose the Vault or the folder. ``evidence`` lists at least one source
        such as a file path, URL or quote. ``pin`` puts the page first in session-start recall.

        ``basis`` (required): ``stated`` when the user said the fact; the page is published and the tool
        returns ``published`` or ``rejected``. ``inferred`` when you concluded it yourself; nothing is published,
        the tool returns ``proposed`` with a ``review_path`` in the Vault review queue, and the fact is not in
        recall or search until a person accepts it.

        ``cwd`` is the project folder; without it the server working folder is used. The target Vault must be
        linked to that project in vault-map.json. ``vault`` names one of those Vaults. If the result status is
        ``vault_required``, nothing was written: call the tool again with ``vault`` set to one of the names in
        ``candidates``. The new page records the ``cwd`` project id in ``project``.

        ``candidate_key`` (optional) is the ``key`` of the list_memory_candidates candidate this write handles.
        A ``published`` or ``proposed`` result records it, so the candidate is not offered again.
        """
        request = parse_remember_input(
            title=title,
            kind=kind,
            body=body,
            evidence=evidence,
            basis=basis,
            cwd=cwd,
            vault=vault,
            pin=pin,
            memory_kind=memory_kind,
            candidate_key=candidate_key,
        )
        return registry.remember(request).to_json_dict()

    @server.tool("update_memory", structured_output=True)
    def update_memory(
        path: str,
        body: str,
        evidence: list[str],
        basis: MemoryBasis,
        vault: str | None = None,
        cwd: str | None = None,
        title: str | None = None,
        pin: bool | None = None,
        memory_kind: MemoryKind | None = None,
        candidate_key: str | None = None,
    ) -> dict[str, object]:
        """Replace the body of one existing memory page.

        ``path`` is the Vault-relative page path, such as ``wiki/decisions/use-sqlite.md``, as returned in
        ``written_paths`` or by search. ``title``, ``pin`` and ``memory_kind`` (``rule``, ``correction``,
        ``decision`` or ``preference``) are optional; leaving them out keeps the page's current value.
        Without ``vault``, the tool looks for ``path`` in the project's Vaults.

        ``basis`` (required): ``stated`` when the user said the fact; the page is published and the tool
        returns ``published`` or ``rejected``. ``inferred`` when you concluded it yourself; nothing is published,
        the tool returns ``proposed`` with a ``review_path`` in the Vault review queue, and the fact is not in
        recall or search until a person accepts it.

        ``cwd`` is the project folder; without it the server working folder is used. The target Vault must be
        linked to that project in vault-map.json. ``vault`` names one of those Vaults. If the result status is
        ``vault_required``, nothing was written: call the tool again with ``vault`` set to one of the names in
        ``candidates``.

        ``candidate_key`` (optional) is the ``key`` of the list_memory_candidates candidate this write handles.
        A ``published`` or ``proposed`` result records it, so the candidate is not offered again.
        """
        request = parse_update_memory_input(
            path=path,
            body=body,
            evidence=evidence,
            basis=basis,
            vault=vault,
            cwd=cwd,
            title=title,
            pin=pin,
            memory_kind=memory_kind,
            candidate_key=candidate_key,
        )
        return registry.update_memory(request).to_json_dict()

    @server.tool("retire_memory", structured_output=True)
    def retire_memory(
        path: str,
        reason: str,
        basis: MemoryBasis,
        vault: str | None = None,
        cwd: str | None = None,
        replaced_by: str | None = None,
        candidate_key: str | None = None,
    ) -> dict[str, object]:
        """Mark one existing memory page as retired. The file stays in the Vault.

        ``path`` is the Vault-relative page path, such as ``wiki/decisions/use-sqlite.md``. ``reason`` is one
        line. ``replaced_by`` is an optional ``wiki/...md`` path of the page that replaces it, in the same Vault.
        Without ``vault``, the tool looks for ``path`` in the project's Vaults.

        ``basis`` (required): ``stated`` when the user said the fact; the page is published and the tool
        returns ``published`` or ``rejected``. ``inferred`` when you concluded it yourself; nothing is published,
        the tool returns ``proposed`` with a ``review_path`` in the Vault review queue, and the fact is not in
        recall or search until a person accepts it.

        ``cwd`` is the project folder; without it the server working folder is used. The target Vault must be
        linked to that project in vault-map.json. ``vault`` names one of those Vaults. If the result status is
        ``vault_required``, nothing was written: call the tool again with ``vault`` set to one of the names in
        ``candidates``.

        ``candidate_key`` (optional) is the ``key`` of the list_memory_candidates candidate this write handles.
        A ``published`` or ``proposed`` result records it, so the candidate is not offered again.
        """
        request = parse_retire_memory_input(
            path=path,
            reason=reason,
            basis=basis,
            vault=vault,
            cwd=cwd,
            replaced_by=replaced_by,
            candidate_key=candidate_key,
        )
        return registry.retire_memory(request).to_json_dict()

    @server.tool("import_auto_memory", structured_output=True)
    def import_auto_memory(
        note: str,
        cwd: str | None = None,
        vault: str | None = None,
        candidate_key: str | None = None,
    ) -> dict[str, object]:
        """Keep a copy of one Claude Code auto-memory note in a Vault, to cite it as evidence.

        ``note`` is the absolute path of the note file, the ``location`` of an ``l1_note`` candidate. The Vault's
        own ``import-source`` copies the file under ``raw/imports/claude-memory/`` and makes a source page;
        vault-graph does not change, move or delete the note. The result has ``raw_path`` (cite this path as
        evidence) and ``source_page``. A note the Vault already holds returns the existing paths.

        ``cwd`` is the project folder; without it the server working folder is used. The target Vault must be
        linked to that project in vault-map.json. ``vault`` names one of those Vaults. If the result status is
        ``vault_required``, nothing was written: call the tool again with ``vault`` set to one of the names in
        ``candidates``.

        ``candidate_key`` (optional) is the ``key`` of the list_memory_candidates candidate this write handles.
        A ``published`` or ``proposed`` result records it, so the candidate is not offered again.
        """
        request = parse_import_auto_memory_input(note=note, cwd=cwd, vault=vault, candidate_key=candidate_key)
        return registry.import_auto_memory(request).to_json_dict()

    @server.tool("supersede_claim", structured_output=True)
    def supersede_claim(
        path: str,
        claim: str,
        new_claim: str,
        evidence: str,
        basis: MemoryBasis,
        cwd: str | None = None,
        vault: str | None = None,
        candidate_key: str | None = None,
    ) -> dict[str, object]:
        """Replace one claim row of an existing page with a new claim. The old row stays, marked superseded.

        ``path`` is the Vault-relative page path. ``claim`` is the text of the current claim row; it must match
        exactly one row of the page's claim table. ``new_claim`` and ``evidence`` become the new row; each is one
        line without ``|``. For a session exchange, write its location ``<path> L<a>-L<b>`` in ``evidence``.
        A page without a claim table is rejected; to replace a whole page use retire_memory(replaced_by=...).

        ``basis`` (required): ``stated`` when the user said the fact; the change is published and the tool
        returns ``published`` or ``rejected``. ``inferred`` when you concluded it yourself; nothing is published,
        the tool returns ``proposed`` with a ``review_path`` in the Vault review queue.

        ``cwd`` is the project folder; without it the server working folder is used. Without ``vault``, the tool
        looks for ``path`` in the project's Vaults.

        ``candidate_key`` (optional) is the ``key`` of the list_memory_candidates candidate this write handles.
        A ``published`` or ``proposed`` result records it, so the candidate is not offered again.
        """
        request = parse_supersede_claim_input(
            path=path,
            claim=claim,
            new_claim=new_claim,
            evidence=evidence,
            basis=basis,
            cwd=cwd,
            vault=vault,
            candidate_key=candidate_key,
        )
        return registry.supersede_claim(request).to_json_dict()

    @server.tool("restore_memory", structured_output=True)
    def restore_memory(
        path: str,
        reason: str,
        basis: MemoryBasis,
        cwd: str | None = None,
        vault: str | None = None,
        candidate_key: str | None = None,
    ) -> dict[str, object]:
        """Make a retired, deprecated or superseded page current again. Only its frontmatter changes.

        Use this instead of writing the same fact again when search with ``include_retired`` or the cleanup
        comparison material shows the page as retired ("폐기됨"). ``path`` is the Vault-relative page path and
        ``reason`` is one line. A page that is not retired is rejected.

        ``basis`` (required): ``stated`` when the user said the fact; the change is published and the tool
        returns ``published`` or ``rejected``. ``inferred`` when you concluded it yourself; nothing is published,
        the tool returns ``proposed`` with a ``review_path`` in the Vault review queue.

        ``cwd`` is the project folder; without it the server working folder is used. Without ``vault``, the tool
        looks for ``path`` in the project's Vaults.

        ``candidate_key`` (optional) is the ``key`` of the list_memory_candidates candidate this write handles.
        A ``published`` or ``proposed`` result records it, so the candidate is not offered again.
        """
        request = parse_restore_memory_input(
            path=path, reason=reason, basis=basis, cwd=cwd, vault=vault, candidate_key=candidate_key
        )
        return registry.restore_memory(request).to_json_dict()


def background_index_message(vault_name: str) -> str:
    return (
        f"vault-graph started indexing Vault {vault_name} in the background. The page becomes searchable "
        "and recallable when that run finishes. If it is still missing later, run vg index."
    )


def _write_cwd(cwd: str | None) -> str | None:
    """The folder whose project picks the target Vault: ``cwd``, else the server working folder (결정12)."""
    if cwd is not None:
        return cwd
    try:
        return str(Path.cwd())
    except OSError:
        return None


def _project_id(cwd: str | None) -> str | None:
    """The ``vault-map.json`` project id of ``cwd``, or None outside a single project (spec 2026-11-05 §4.4.3).

    Reads the same map file as the read tools' project scope (``vault_map_path()``, ``mcp_tools``).
    """
    if cwd is None:
        return None
    from vault_graph.operation.integration.vault_map import open_vault_map, vault_map_path

    vault_map = open_vault_map(vault_map_path()).vault_map
    return None if vault_map is None else vault_map.find_project(Path(cwd)).project_id


def parse_remember_input(
    *,
    title: str,
    kind: str,
    body: str,
    evidence: list[str],
    basis: str,
    cwd: str | None = None,
    vault: str | None = None,
    pin: bool = False,
    memory_kind: str | None = None,
    candidate_key: str | None = None,
) -> RememberInput:
    """Check only types here. Empty fields, unknown kinds and bases come back as a ``rejected`` result."""

    _require_strings(title=title, kind=kind, body=body, basis=basis)
    _require_optional_strings(cwd=cwd, vault=vault, memory_kind=memory_kind, candidate_key=candidate_key)
    if not isinstance(pin, bool):
        raise invalid_arguments("pin must be a boolean")
    return RememberInput(
        title=title,
        kind=kind,
        body=body,
        evidence=_evidence_tuple(evidence),
        basis=basis,
        cwd=cwd,
        vault=vault,
        pin=pin,
        memory_kind=memory_kind,
        candidate_key=candidate_key,
    )


def parse_update_memory_input(
    *,
    path: str,
    body: str,
    evidence: list[str],
    basis: str,
    vault: str | None = None,
    cwd: str | None = None,
    title: str | None = None,
    pin: bool | None = None,
    memory_kind: str | None = None,
    candidate_key: str | None = None,
) -> UpdateMemoryInput:
    """Check only types here. Bad paths and empty fields come back as a ``rejected`` result."""

    _require_strings(path=path, body=body, basis=basis)
    _require_optional_strings(vault=vault, cwd=cwd, title=title, memory_kind=memory_kind, candidate_key=candidate_key)
    if pin is not None and not isinstance(pin, bool):
        raise invalid_arguments("pin must be a boolean")
    return UpdateMemoryInput(
        path=path,
        body=body,
        evidence=_evidence_tuple(evidence),
        basis=basis,
        vault=vault,
        cwd=cwd,
        title=title,
        pin=pin,
        memory_kind=memory_kind,
        candidate_key=candidate_key,
    )


def parse_retire_memory_input(
    *,
    path: str,
    reason: str,
    basis: str,
    vault: str | None = None,
    cwd: str | None = None,
    replaced_by: str | None = None,
    candidate_key: str | None = None,
) -> RetireMemoryInput:
    """Check only types here. Bad paths and empty reasons come back as a ``rejected`` result."""

    _require_strings(path=path, reason=reason, basis=basis)
    _require_optional_strings(vault=vault, cwd=cwd, replaced_by=replaced_by, candidate_key=candidate_key)
    return RetireMemoryInput(
        path=path,
        reason=reason,
        basis=basis,
        vault=vault,
        cwd=cwd,
        replaced_by=replaced_by,
        candidate_key=candidate_key,
    )


def parse_supersede_claim_input(
    *,
    path: str,
    claim: str,
    new_claim: str,
    evidence: str,
    basis: str,
    cwd: str | None = None,
    vault: str | None = None,
    candidate_key: str | None = None,
) -> SupersedeClaimInput:
    """Check only types here. Empty cells, ``|`` and line breaks come back as a ``rejected`` result."""

    _require_strings(path=path, claim=claim, new_claim=new_claim, evidence=evidence, basis=basis)
    _require_optional_strings(cwd=cwd, vault=vault, candidate_key=candidate_key)
    return SupersedeClaimInput(
        path=path,
        claim=claim,
        new_claim=new_claim,
        evidence=evidence,
        basis=basis,
        cwd=cwd,
        vault=vault,
        candidate_key=candidate_key,
    )


def parse_restore_memory_input(
    *,
    path: str,
    reason: str,
    basis: str,
    cwd: str | None = None,
    vault: str | None = None,
    candidate_key: str | None = None,
) -> RestoreMemoryInput:
    """Check only types here. Bad paths, empty reasons and pages that are not retired come back as ``rejected``."""

    _require_strings(path=path, reason=reason, basis=basis)
    _require_optional_strings(cwd=cwd, vault=vault, candidate_key=candidate_key)
    return RestoreMemoryInput(path=path, reason=reason, basis=basis, cwd=cwd, vault=vault, candidate_key=candidate_key)


def parse_import_auto_memory_input(
    *,
    note: str,
    cwd: str | None = None,
    vault: str | None = None,
    candidate_key: str | None = None,
) -> ImportAutoMemoryInput:
    """Check only types here. A relative or empty note path comes back as a ``rejected`` result."""

    _require_strings(note=note)
    _require_optional_strings(cwd=cwd, vault=vault, candidate_key=candidate_key)
    return ImportAutoMemoryInput(note=note, cwd=cwd, vault=vault, candidate_key=candidate_key)


def _require_strings(**values: object) -> None:
    for field_name, value in values.items():
        if not isinstance(value, str):
            raise invalid_arguments(f"{field_name} must be a string")


def _require_optional_strings(**values: object) -> None:
    for field_name, value in values.items():
        if value is not None and not isinstance(value, str):
            raise invalid_arguments(f"{field_name} must be a string")


def _evidence_tuple(evidence: object) -> tuple[str, ...]:
    if not isinstance(evidence, list | tuple) or not all(isinstance(item, str) for item in evidence):
        raise invalid_arguments("evidence must be a list of strings")
    return tuple(evidence)


__all__ = [
    "ImportAutoMemoryInput",
    "McpMemoryTools",
    "MemoryToolRunner",
    "MemoryBasis",
    "MemoryKind",
    "PageKind",
    "RememberInput",
    "RestoreMemoryInput",
    "RetireMemoryInput",
    "SupersedeClaimInput",
    "UpdateMemoryInput",
    "background_index_message",
    "parse_import_auto_memory_input",
    "parse_remember_input",
    "parse_restore_memory_input",
    "parse_retire_memory_input",
    "parse_supersede_claim_input",
    "parse_update_memory_input",
    "register_memory_tools",
]
