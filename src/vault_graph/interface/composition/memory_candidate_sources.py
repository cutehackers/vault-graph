"""Read the cleanup bundle inputs and call the M10 rule (spec 2026-11-05 §4.4.4, §4.4.12, §4.4.13-2).

``memory_candidate_package`` is the one entry for the session start backlog line (task #34) and
the MCP tool ``list_memory_candidates`` (task #36), so both count the same candidates. It reads,
and never writes:

- the ``cwd`` map project and its registered Vaults (``vault-map.json``),
- L1 notes from the Claude Code auto-memory folder and the ``raw_sha256`` values of Vault source
  pages, corrected by the saved Vault ``memory-scan`` reports in Graph Home ``memory/`` (the Vault
  result wins, as in ``memory_scan_runner``),
- indexed session exchanges: one per chunk ``parent_key``, with the exchange line range from the
  chunk ``parent_locators`` and the start time, human text and outcome from those lines of the
  session file (v2 meta ``started=``, v1 turn heading time),
- ``wiki/`` page files for exchange citations, and indexed ``wiki/`` pages for merge and retire,
- page embeddings (merge), the Graph Home ``usage/`` log (retire, ``unused``), and the active code
  projection of the registered repositories (retire, ``code_gone``; M10 cannot import M11),
- ``memory/reviewed.jsonl``,
- comparison material from the search service with ``include_retired`` (§4.4.13-2).

Code references (``code_gone``). A page cites code as a backticked repository path, optionally with
``::Symbol``, ``#Symbol`` or ``:Symbol`` after it (``src/app/x.py``, ``src/app/x.py::run``,
``src/app/x.py:12-40@abc1234``). A reference counts only when its file suffix and its first folder
appear in the code projection, so paths of other tools or of unregistered repositories are not
reported. It is gone when no projected file has the path, or the file has no symbol of that name.
Without registered repositories or an active code projection there is no ``code_gone`` signal.
"""

from __future__ import annotations

import json
import re
from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Protocol
from urllib.parse import unquote

from vault_graph.context.memory.memory_candidates import (
    CANDIDATE_KINDS,
    DEFAULT_MERGE_SIMILARITY,
    CandidateKind,
    L1Note,
    MemoryCandidate,
    MemoryPage,
    PageKey,
    SessionExchange,
    SimilarPage,
    WikiPageText,
    build_memory_candidates,
    is_current_memory_page,
)
from vault_graph.context.memory.project_scope import UNMAPPED_VAULT_SCOPE, VaultProjectScope
from vault_graph.errors import VaultGraphError
from vault_graph.indexing.ingestion.session_exchange_v1_chunker import SESSION_EXCHANGE_V1_VERSION
from vault_graph.indexing.ingestion.session_exchange_v2_chunker import SESSION_EXCHANGE_V2_VERSION
from vault_graph.operation.scope.catalog_service import CatalogService
from vault_graph.operation.scope.graph_home import GraphHomeResolver

if TYPE_CHECKING:
    from vault_graph.context.pack.recall_backlog import MemoryBacklog
    from vault_graph.indexing.ingestion.document_snapshots import ChunkSnapshot, DocumentSnapshot
    from vault_graph.operation.scope.vault_catalog import QueryScope
    from vault_graph.retrieval.search.search_response import SearchMode, SearchOutputFormat, SearchResponse
    from vault_graph.storage.interfaces.metadata_store import MetadataStore

SESSION_PATH_PREFIX = "raw/sessions/"
WIKI_PATH_PREFIX = "wiki/"
# 90 days reach into at most four calendar months, so the retire rule reads four month files.
USAGE_MONTH_FILES = 4
# Comparison search reads the start of a long human turn only.
COMPARISON_QUERY_WORDS = 64
SESSION_CHUNKER_VERSIONS = frozenset({SESSION_EXCHANGE_V1_VERSION, SESSION_EXCHANGE_V2_VERSION})
NO_PROJECT_REASON = "프로젝트를 찾지 못함"
# The kinds the session start backlog line counts (spec 2026-11-05 §4.4.6).
BACKLOG_KINDS: tuple[CandidateKind, ...] = ("l1_note", "session_exchange")

_CODE_SPAN_RE = re.compile(r"`([^`\n]+)`")
_CODE_REF_RE = re.compile(
    r"^(?:\./)?(?P<path>(?:[\w.-]+/)+[\w.-]*\w\.[A-Za-z0-9]+)"
    r"(?:(?:::|#|:)(?P<symbol>[A-Za-z_][\w.]*)|[:#@][\w.@:#-]*)?$"
)
_META_RE = re.compile(r"^<!-- vg:exchange (?P<body>.*) -->$")
_V1_TURN_RE = re.compile(r"^## (?P<at>\d{4}-\d{2}-\d{2}T\S+) (?:subagent \S+ )?(?P<role>user|assistant)$")
_V2_TURN_RE = re.compile(r"^### (?P<role>[^ ·]+)")
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


@dataclass(frozen=True)
class MemoryCandidatePackage:
    """The cleanup bundle of one project. ``reason`` explains an empty bundle; ``warnings`` are one line each."""

    project_id: str | None
    candidates: tuple[MemoryCandidate, ...]
    reason: str | None = None
    warnings: tuple[str, ...] = ()
    # True when L1 notes were asked for and the L1 folder is missing or unreadable (one warning says why).
    l1_unavailable: bool = False

    def count(self, kind: CandidateKind) -> int:
        return sum(1 for candidate in self.candidates if candidate.kind == kind)


@dataclass(frozen=True)
class CodeReference:
    path: str
    symbol: str | None = None


@dataclass(frozen=True)
class ProjectedCode:
    """Relative paths of the active code projection, each with its symbol names and qualified names."""

    symbols_by_path: Mapping[str, frozenset[str]]
    suffixes: frozenset[str] = field(init=False)
    top_folders: frozenset[str] = field(init=False)

    def __post_init__(self) -> None:
        paths = tuple(self.symbols_by_path)
        object.__setattr__(self, "suffixes", frozenset(PurePosixPath(path).suffix for path in paths))
        object.__setattr__(self, "top_folders", frozenset(path.split("/", 1)[0] for path in paths if "/" in path))


class SearchService(Protocol):
    def search(
        self,
        *,
        query_text: str,
        requested_scope: QueryScope,
        limit: int = 10,
        output_format: SearchOutputFormat = "text",
        mode: SearchMode = "knowledge",
        include_retired: bool = False,
    ) -> SearchResponse: ...


def memory_candidate_package(
    graph_home: Path,
    cwd: Path,
    *,
    kinds: Collection[CandidateKind] | None = None,
    limit: int | None = None,
    vault_map_file: Path | None = None,
    environ: Mapping[str, str] | None = None,
    now: datetime | None = None,
    merge_threshold: float = DEFAULT_MERGE_SIMILARITY,
    with_comparison: bool = True,
) -> MemoryCandidatePackage:
    """The cleanup bundle of the ``cwd`` map project, in table order, cut to ``limit``.

    ``kinds`` keeps only those kinds and skips reading what the others need (the backlog line asks
    for ``l1_note`` and ``session_exchange`` only, so it embeds nothing and opens no search).
    A folder the map does not link to a project gives an empty bundle and ``NO_PROJECT_REASON``.
    ``with_comparison=False`` gives the same candidates without comparison material and never opens
    search (merge candidates still need page embeddings).
    """
    from vault_graph.interface.composition.query_scope_resolution import resolve_project_vaults
    from vault_graph.interface.composition.read_only_service_factory import map_vault_scopes
    from vault_graph.operation.integration.vault_map import open_vault_map, vault_map_path
    from vault_graph.storage.local.reviewed_log import JsonlReviewedLog
    from vault_graph.storage.local.sqlite_metadata_store import SQLiteMetadataStore

    wanted = frozenset(CANDIDATE_KINDS if kinds is None else kinds)
    moment = now or datetime.now(UTC)
    descriptor = GraphHomeResolver().resolve(graph_home)
    if not descriptor.initialized:
        return MemoryCandidatePackage(None, (), reason=f"No Graph Home at {descriptor.root_path}. Run `vg setup`.")
    catalog_service = CatalogService(graph_home_path=descriptor.root_path)
    catalog = catalog_service.load_catalog()
    map_file = vault_map_path(vault_map_file, environ=environ)
    opening = open_vault_map(map_file)
    warnings: list[str] = [opening.warning] if opening.warning else []
    resolution = resolve_project_vaults(cwd, vault_map=opening.vault_map, vault_catalog=catalog)
    if (
        opening.vault_map is None
        or resolution.source != "vault-map"
        or resolution.project_id is None
        or not resolution.vault_ids
    ):
        detail = f": {resolution.reason}" if resolution.reason else ""
        return MemoryCandidatePackage(None, (), reason=f"{NO_PROJECT_REASON}{detail}", warnings=tuple(warnings))
    project_id = resolution.project_id
    vault_ids = resolution.vault_ids
    vault_scopes: Mapping[str, VaultProjectScope] = map_vault_scopes(opening.vault_map, catalog)
    roots = {vault_id: catalog.resolve(vault_id).root_path for vault_id in vault_ids}

    metadata: MetadataStore | None = None
    documents: dict[str, tuple[DocumentSnapshot, ...]] = {vault_id: () for vault_id in vault_ids}
    if catalog_service.metadata_path.is_file():
        metadata = SQLiteMetadataStore(catalog_service.metadata_path, initialize=False)
        documents = {
            vault_id: metadata.list_documents(catalog.scope_for_vault_ids((vault_id,))) for vault_id in vault_ids
        }
    else:
        warnings.append("No index in the Graph Home yet. Run `vg index`.")

    l1_notes: tuple[L1Note, ...] = ()
    imported: frozenset[str] = frozenset()
    l1_problem: str | None = None
    if "l1_note" in wanted:
        l1_notes, imported, l1_problem = l1_inputs(
            project_id=project_id,
            project_root=_project_root(map_file, project_id),
            vault_roots=tuple(roots.values()),
            scan_reports=tuple(_scan_report(descriptor.root_path, vault_id) for vault_id in vault_ids),
            environ=environ,
        )
        if l1_problem is not None:
            warnings.append(f"{l1_problem} No L1 note candidates.")

    exchanges: list[SessionExchange] = []
    wiki_pages: list[WikiPageText] = []
    if "session_exchange" in wanted and metadata is not None:
        for vault_id in vault_ids:
            exchanges.extend(session_exchanges(metadata, vault_id, documents[vault_id], roots[vault_id]))
            wiki_pages.extend(_wiki_page_texts(documents[vault_id], roots[vault_id]))

    memory_pages: tuple[MemoryPage, ...] = ()
    page_vectors: dict[PageKey, Sequence[float]] = {}
    missing_code: dict[PageKey, tuple[str, ...]] = {}
    usage_events: tuple[Mapping[str, object], ...] = ()
    if wanted & {"merge", "retire"} and metadata is not None:
        memory_pages = _memory_pages(metadata, documents, vault_scopes)
        current = tuple(page for page in memory_pages if is_current_memory_page(page, project_id))
        if "merge" in wanted:
            page_vectors = _page_vectors(catalog_service, current, warnings)
        if "retire" in wanted:
            usage_events = _usage_events(descriptor.root_path, warnings)
            projected = projected_code(catalog_service, warnings)
            if projected is not None:
                for page in current:
                    gone = missing_code_references(code_references(page.text), projected)
                    if gone:
                        missing_code[page.key] = gone

    try:
        reviewed = JsonlReviewedLog(descriptor.root_path).reviewed_keys()
    except OSError as exc:
        reviewed = frozenset()
        warnings.append(f"memory/reviewed.jsonl was not read: {_one_line(str(exc))}")

    finder = _LazySearchFinder(
        graph_home=descriptor.root_path,
        scope=catalog.scope_for_vault_ids(vault_ids),
        documents=documents,
        vault_scopes=vault_scopes,
    )
    candidates = build_memory_candidates(
        project_id=project_id,
        l1_notes=l1_notes,
        imported_raw_sha256=imported,
        exchanges=exchanges,
        wiki_pages=wiki_pages,
        reviewed_keys=reviewed,
        similar_pages=finder,
        now=moment,
        limit=limit,
        memory_pages=memory_pages,
        page_vectors=page_vectors,
        missing_code=missing_code,
        usage_events=usage_events,
        kinds=wanted,
        merge_threshold=merge_threshold,
        with_comparison=with_comparison,
    )
    return MemoryCandidatePackage(
        project_id, candidates, warnings=(*warnings, *finder.warnings), l1_unavailable=l1_problem is not None
    )


class CandidateBacklogCounter:
    """The session start backlog count (spec 2026-11-05 §4.4.6): L1 notes and session exchanges,
    counted by ``memory_candidate_package`` like ``list_memory_candidates``, without comparison material.

    It never searches, embeds or writes. ``l1_notes`` is None when the L1 folder is missing or unreadable.
    """

    def __init__(self, *, graph_home: Path, vault_map_path: Path, environ: Mapping[str, str] | None = None) -> None:
        self._graph_home = graph_home
        self._vault_map_path = vault_map_path
        self._environ = environ

    def count(self, cwd: Path) -> MemoryBacklog:
        from vault_graph.context.pack.recall_backlog import MemoryBacklog

        package = memory_candidate_package(
            self._graph_home,
            cwd,
            kinds=BACKLOG_KINDS,
            vault_map_file=self._vault_map_path,
            environ=self._environ,
            with_comparison=False,
        )
        return MemoryBacklog(
            l1_notes=None if package.l1_unavailable else package.count("l1_note"),
            session_exchanges=package.count("session_exchange"),
            warnings=package.warnings,
        )


# L1 notes ---------------------------------------------------------------------------------------


def l1_inputs(
    *,
    project_id: str,
    project_root: str | None,
    vault_roots: Iterable[Path],
    scan_reports: Iterable[Mapping[str, object] | None],
    environ: Mapping[str, str] | None = None,
) -> tuple[tuple[L1Note, ...], frozenset[str], str | None]:
    """L1 notes of the project folder, the sha256 values already kept in a linked Vault, and why the
    L1 folder could not be read (None when it could). An unreadable folder gives no notes.

    The vg check (``raw_sha256`` of Vault source pages) is corrected by the saved ``memory-scan``
    reports: a note a report marks imported is kept, one it marks not imported is not.
    """
    from vault_graph.interface.composition.adapters.auto_memory_reader import (
        imported_raw_hashes,
        locate_memory_folder,
        memory_folder_problem,
        read_memory_notes,
    )

    if project_root is None:
        return (), frozenset(), None
    folder = locate_memory_folder(project_root, environ=environ)
    problem = memory_folder_problem(folder.path)
    notes: tuple[L1Note, ...] = ()
    if problem is None:
        try:
            notes = tuple(
                L1Note(path=str(note.path), sha256=note.sha256, text=note.text)
                for note in read_memory_notes(folder.path)
            )
        except OSError as exc:
            problem = f"The L1 memory folder {folder.path} cannot be read: {_one_line(str(exc))}."
    imported: set[str] = set()
    for root in vault_roots:
        imported.update(imported_raw_hashes(root))
    marked_imported: set[str] = set()
    marked_not: set[str] = set()
    for report in scan_reports:
        for sha256, flag in _report_flags(report, project_id):
            (marked_imported if flag else marked_not).add(sha256)
    return notes, frozenset((imported - marked_not) | marked_imported), problem


def _report_flags(report: Mapping[str, object] | None, project_id: str) -> Iterable[tuple[str, bool]]:
    projects = report.get("projects") if report is not None else None
    if not isinstance(projects, list):
        return
    for project in projects:
        if (
            not isinstance(project, dict)
            or project.get("id") != project_id
            or not isinstance(project.get("notes"), list)
        ):
            continue
        for note in project["notes"]:
            if (
                isinstance(note, dict)
                and isinstance(note.get("sha256"), str)
                and isinstance(note.get("imported"), bool)
            ):
                yield note["sha256"], note["imported"]


def _scan_report(graph_home: Path, vault_id: str) -> Mapping[str, object] | None:
    from vault_graph.interface.composition.adapters.memory_scan_runner import memory_scan_path

    try:
        data = json.loads(memory_scan_path(graph_home, vault_id).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _project_root(map_file: Path, project_id: str) -> str | None:
    try:
        entry = json.loads(map_file.read_text(encoding="utf-8"))["projects"][project_id]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    root = entry.get("root") if isinstance(entry, dict) else None
    return root if isinstance(root, str) and root else None


# Session exchanges ------------------------------------------------------------------------------


def session_exchanges(
    metadata: MetadataStore, vault_id: str, documents: Iterable[DocumentSnapshot], vault_root: Path
) -> list[SessionExchange]:
    """One ``SessionExchange`` per indexed exchange ``parent_key`` of the Vault's session files."""
    exchanges: list[SessionExchange] = []
    for document in documents:
        if not document.path.startswith(SESSION_PATH_PREFIX):
            continue
        units: dict[str, ChunkSnapshot] = {}
        for chunk in metadata.list_document_chunks(vault_id=vault_id, document_id=document.document_id):
            if chunk.chunker_version in SESSION_CHUNKER_VERSIONS and chunk.parent_key and chunk.parent_locators:
                units.setdefault(chunk.parent_key, chunk)
        if not units:
            continue
        try:
            lines = (vault_root / document.path).read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        for parent_key, chunk in units.items():
            exchange = _exchange(document, chunk, parent_key, lines)
            if exchange is not None:
                exchanges.append(exchange)
    return exchanges


def _exchange(
    document: DocumentSnapshot, chunk: ChunkSnapshot, parent_key: str, lines: Sequence[str]
) -> SessionExchange | None:
    coordinates = dict(chunk.parent_locators[0].coordinates)
    try:
        first = int(coordinates["line"])
        last = int(coordinates.get("line_end", coordinates["line"]))
    except (KeyError, ValueError):
        return None
    block = lines[first - 1 : last]
    fields: dict[str, str] = {}
    if chunk.chunker_version == SESSION_EXCHANGE_V2_VERSION:
        fields = next((_meta_fields(line) for line in block if _META_RE.match(line)), {})
        started_text = fields.get("started", "")
        human = _turn_text(block, _V2_TURN_RE, top_level_ends_turn=True)
    else:
        started_text = next((match.group("at") for line in block if (match := _V1_TURN_RE.match(line))), "")
        human = _turn_text(block, _V1_TURN_RE, top_level_ends_turn=False)
    started = _time(started_text) or _time(_text(document.frontmatter.get("first_turn_at"))) or _path_day(document.path)
    if started is None:
        return None
    return SessionExchange(
        parent_key=parent_key,
        path=document.path,
        line_start=first,
        line_end=last,
        started_at=started,
        human_text=human,
        outcome=fields.get("outcome", ""),
        exchange_id=fields.get("id") or None,
        session=_text(document.frontmatter.get("session_id")) or document.path,
    )


def _meta_fields(line: str) -> dict[str, str]:
    match = _META_RE.match(line)
    if match is None:
        return {}
    fields: dict[str, str] = {}
    for token in match.group("body").split(" "):
        key, separator, value = token.partition("=")
        if separator and key and key not in fields:
            fields[key] = unquote(value)
    return fields


def _turn_text(block: Sequence[str], heading: re.Pattern[str], *, top_level_ends_turn: bool) -> str:
    """Text of the user turns in an exchange block. v1 ``Tools:`` lines are not human text."""
    role: str | None = None
    kept: list[str] = []
    for line in block:
        match = heading.match(line)
        if match is not None:
            role = match.group("role")
            continue
        if top_level_ends_turn and line.startswith("## "):
            role = None
            continue
        if role == "user" and line.strip() and not line.startswith("Tools: "):
            kept.append(line.strip())
    return "\n".join(kept)


def _wiki_page_texts(documents: Iterable[DocumentSnapshot], vault_root: Path) -> list[WikiPageText]:
    pages: list[WikiPageText] = []
    for document in documents:
        if not document.path.startswith(WIKI_PATH_PREFIX):
            continue
        try:
            text = (vault_root / document.path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        pages.append(WikiPageText(path=document.path, text=text))
    return pages


# Merge and retire -------------------------------------------------------------------------------


def _memory_pages(
    metadata: MetadataStore,
    documents: Mapping[str, Sequence[DocumentSnapshot]],
    vault_scopes: Mapping[str, VaultProjectScope],
) -> tuple[MemoryPage, ...]:
    from vault_graph.interface.composition.read_only_service_factory import metadata_body_reader

    body_text = metadata_body_reader(metadata)
    return tuple(
        MemoryPage(
            vault_id=vault_id,
            path=document.path,
            title=_title(document),
            frontmatter=document.frontmatter,
            vault_scope=vault_scopes.get(vault_id, UNMAPPED_VAULT_SCOPE),
            text=body_text(vault_id, document.document_id),
            evidence_date=_evidence_date(document),
        )
        for vault_id, items in documents.items()
        for document in items
        if document.path.startswith(WIKI_PATH_PREFIX)
    )


def _page_vectors(
    catalog_service: CatalogService, pages: Sequence[MemoryPage], warnings: list[str]
) -> dict[PageKey, Sequence[float]]:
    from vault_graph.interface.composition.adapters.text_embeddings import text_embeddings_for
    from vault_graph.storage.interfaces.text_embeddings import EmbeddingInput

    if len(pages) < 2:
        return {}
    try:
        embeddings = text_embeddings_for(catalog_service, local_files_only=True)
        if not embeddings.can_embed_without_download():
            warnings.append("The embedding model is not downloaded, so no merge candidates. Run `vg index`.")
            return {}
        vectors = embeddings.embed(
            tuple(EmbeddingInput(input_id=str(index), text=_embedding_text(page)) for index, page in enumerate(pages))
        )
    except (VaultGraphError, OSError, ValueError) as exc:
        warnings.append(f"Page embeddings failed, so no merge candidates: {_one_line(str(exc))}")
        return {}
    by_id = {vector.input_id: vector.values for vector in vectors}
    return {page.key: by_id[str(index)] for index, page in enumerate(pages) if str(index) in by_id}


def _embedding_text(page: MemoryPage) -> str:
    return f"{page.title}\n\n{page.text}".strip() or page.path


def _usage_events(graph_home: Path, warnings: list[str]) -> tuple[Mapping[str, object], ...]:
    from vault_graph.storage.local.usage_log import JsonlUsageLog

    try:
        return JsonlUsageLog(graph_home, max_files=USAGE_MONTH_FILES).read_events()
    except OSError as exc:
        warnings.append(f"The usage log was not read, so no unused-page candidates: {_one_line(str(exc))}")
        return ()


def code_references(text: str) -> tuple[CodeReference, ...]:
    """Backticked repository paths in ``text``, with a symbol when one follows ``::``, ``#`` or ``:``."""
    found: dict[CodeReference, None] = {}
    for span in _CODE_SPAN_RE.findall(text):
        match = _CODE_REF_RE.match(span.strip())
        if match is None:
            continue
        path = match.group("path")
        if path.startswith("/") or ".." in path.split("/"):
            continue
        found.setdefault(CodeReference(path=path, symbol=match.group("symbol")), None)
    return tuple(found)


def missing_code_references(references: Iterable[CodeReference], projected: ProjectedCode) -> tuple[str, ...]:
    """References the code projection no longer has, as ``path`` or ``path::symbol``, sorted."""
    missing: set[str] = set()
    for reference in references:
        if PurePosixPath(reference.path).suffix not in projected.suffixes:
            continue
        if reference.path.split("/", 1)[0] not in projected.top_folders:
            continue
        names = projected.symbols_by_path.get(reference.path)
        if names is None:
            missing.add(reference.path)
        elif reference.symbol and not _has_symbol(names, reference.symbol):
            missing.add(f"{reference.path}::{reference.symbol}")
    return tuple(sorted(missing))


def _has_symbol(names: frozenset[str], symbol: str) -> bool:
    return symbol in names or any(name.endswith(f".{symbol}") for name in names)


def projected_code(catalog_service: CatalogService, warnings: list[str]) -> ProjectedCode | None:
    """The active code projection of the enabled registered repositories, or None when there is none."""
    from vault_graph.interface.composition.adapters.code_projection_storage import open_code_projection_reader
    from vault_graph.project.code.code_generation import CodeProjectionGenerationManager
    from vault_graph.project.code.code_models import CODE_PARSER_SPEC_VERSION, code_file_identity
    from vault_graph.project.code.repository_catalog import CodeRepositoryCatalogService

    try:
        entries = CodeRepositoryCatalogService(catalog_service=catalog_service).load().entries()
        repository_ids = tuple(sorted(entry.repository_id for entry in entries if entry.enabled))
        if not repository_ids:
            return None
        layout = CodeProjectionGenerationManager(catalog_service.graph_home_path).active_layout(())
        if layout is None or not layout.database_path.exists():
            warnings.append("No code projection yet, so no gone-code candidates. Run `vg code index`.")
            return None
        store = open_code_projection_reader(layout.database_path, parser_spec_version=CODE_PARSER_SPEC_VERSION)
        if not store.health().schema_compatible:
            warnings.append("The code projection is incompatible, so no gone-code candidates. Run `vg code index`.")
            return None
        snapshots = store.file_snapshots(repository_ids)
        symbols = store.symbols(repository_ids)
    except (VaultGraphError, OSError, ValueError) as exc:
        warnings.append(f"The code projection was not read, so no gone-code candidates: {_one_line(str(exc))}")
        return None
    paths = {code_file_identity(item.repository_id, item.relative_path): item.relative_path for item in snapshots}
    names: dict[str, set[str]] = {item.relative_path: set() for item in snapshots}
    for symbol in symbols:
        path = paths.get(symbol.file_id)
        if path is not None:
            names[path].update((symbol.name, symbol.qualified_name))
    return ProjectedCode({path: frozenset(values) for path, values in names.items()})


# Comparison material ----------------------------------------------------------------------------


class SearchSimilarPageFinder:
    """``SimilarPageFinder`` over the search service with ``include_retired`` (§4.4.13-2).

    Only ``wiki/`` pages of the project Vaults are material. A failed search gives no material and
    one warning line, kept in ``warnings``.
    """

    def __init__(
        self,
        *,
        search: SearchService | None,
        scope: QueryScope,
        documents: Mapping[str, Sequence[DocumentSnapshot]],
        vault_scopes: Mapping[str, VaultProjectScope],
        unavailable: str | None = None,
    ) -> None:
        self._search = search
        self._scope = scope
        self._documents = {
            (document.vault_id, document.document_id): document for items in documents.values() for document in items
        }
        self._vault_scopes = vault_scopes
        self._unavailable = unavailable
        self.warnings: list[str] = []

    def find_similar(self, query: str, *, limit: int) -> Sequence[SimilarPage]:
        text = " ".join(query.split()[:COMPARISON_QUERY_WORDS])
        if not text:
            return ()
        if self._search is None:
            self._warn(self._unavailable or "Search is not available, so no comparison material.")
            return ()
        try:
            response = self._search.search(
                query_text=text,
                requested_scope=self._scope,
                limit=limit,
                output_format="json",
                mode="knowledge",
                include_retired=True,
            )
        except VaultGraphError as exc:
            self._warn(f"Comparison search failed: {_one_line(str(exc))}")
            return ()
        pages: list[SimilarPage] = []
        seen: set[PageKey] = set()
        for result in response.results:
            evidence = result.evidence[0]
            document = self._documents.get((evidence.vault_id, evidence.document_id))
            if document is None or not document.path.startswith(WIKI_PATH_PREFIX):
                continue
            key = (document.vault_id, document.path)
            if key in seen:
                continue
            seen.add(key)
            pages.append(
                SimilarPage(
                    vault_id=document.vault_id,
                    path=document.path,
                    title=_title(document),
                    frontmatter=document.frontmatter,
                    vault_scope=self._vault_scopes.get(document.vault_id, UNMAPPED_VAULT_SCOPE),
                    evidence_date=_evidence_date(document),
                )
            )
        return tuple(pages)

    def _warn(self, message: str) -> None:
        if message not in self.warnings:
            self.warnings.append(message)


class _LazySearchFinder(SearchSimilarPageFinder):
    """Opens search on the first lookup, so a bundle without candidates opens no search or embeddings."""

    def __init__(
        self,
        *,
        graph_home: Path,
        scope: QueryScope,
        documents: Mapping[str, Sequence[DocumentSnapshot]],
        vault_scopes: Mapping[str, VaultProjectScope],
    ) -> None:
        super().__init__(search=None, scope=scope, documents=documents, vault_scopes=vault_scopes)
        self._graph_home = graph_home
        self._opened = False

    def find_similar(self, query: str, *, limit: int) -> Sequence[SimilarPage]:
        if not self._opened:
            self._opened = True
            from vault_graph.interface.composition.read_only_service_factory import ReadOnlyServiceFactory

            try:
                self._search = ReadOnlyServiceFactory(graph_home_path=self._graph_home).open_retrieval_service()
            except (VaultGraphError, OSError) as exc:
                self._unavailable = f"Search is not available, so no comparison material: {_one_line(str(exc))}"
        return super().find_similar(query, limit=limit)


# Small helpers ----------------------------------------------------------------------------------


def _title(document: DocumentSnapshot) -> str:
    title = _text(document.frontmatter.get("title"))
    return title or PurePosixPath(document.path).stem


def _evidence_date(document: DocumentSnapshot) -> str | None:
    for name in ("updated", "date", "created"):
        value = _text(document.frontmatter.get(name))
        if value:
            return value
    return None


def _time(value: str) -> datetime | None:
    if not value:
        return None
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


def _path_day(path: str) -> datetime | None:
    match = _DATE_RE.search(PurePosixPath(path).name)
    if match is None:
        return None
    try:
        return datetime.fromisoformat(match.group(0)).replace(tzinfo=UTC)
    except ValueError:
        return None


def _text(value: object) -> str:
    if value is None or isinstance(value, bool):
        return ""
    return str(value).strip()


def _one_line(text: str) -> str:
    return " ".join(text.split())


__all__ = [
    "BACKLOG_KINDS",
    "NO_PROJECT_REASON",
    "CandidateBacklogCounter",
    "CodeReference",
    "MemoryCandidatePackage",
    "ProjectedCode",
    "SearchSimilarPageFinder",
    "code_references",
    "l1_inputs",
    "memory_candidate_package",
    "missing_code_references",
    "projected_code",
    "session_exchanges",
]
