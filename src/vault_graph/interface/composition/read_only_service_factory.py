from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from vault_graph.errors import VaultGraphError
from vault_graph.interface.composition.graph_store_factory import open_graph_store
from vault_graph.operation.scope.catalog_service import CatalogService
from vault_graph.operation.scope.graph_home import GraphHomeResolver
from vault_graph.operation.scope.vault_catalog import QueryScope, VaultCatalog
from vault_graph.storage.interfaces.metadata_store import MetadataStore

if TYPE_CHECKING:
    from vault_graph.context.answer.answer_service import AnswerService
    from vault_graph.context.memory.decision_memory import DecisionMemoryService
    from vault_graph.context.memory.issue_memory import IssueMemoryService
    from vault_graph.context.memory.memory_source_reader import MemorySourceReader
    from vault_graph.context.memory.project_memory import ProjectMemoryService
    from vault_graph.context.memory.timeline_memory import TimelineMemoryService
    from vault_graph.context.pack.context_pack_builder import ContextPackBuilder
    from vault_graph.context.pack.context_pack_renderer import ContextPackRenderer
    from vault_graph.context.pack.recall import RecallPorts, RecallScope
    from vault_graph.indexing.index_service import IndexService
    from vault_graph.indexing.ingestion.document_normalizer import ChunkSnapshot, DocumentSnapshot
    from vault_graph.interface.composition.adapters.text_embeddings import FastEmbedTextEmbeddings
    from vault_graph.operation.diagnostics.health_explorer import HealthExplorerService
    from vault_graph.operation.integration.vault_map import MappedVaultScope, VaultMap
    from vault_graph.operation.readiness.search_readiness import SearchReadiness
    from vault_graph.project.context.project_binding_reader import ProjectBindingReader
    from vault_graph.retrieval.evidence.evidence_linking import EvidenceLinker
    from vault_graph.retrieval.graph.graph_resource_service import GraphResourceService
    from vault_graph.retrieval.graph.graph_retrieval_service import GraphRetrievalService
    from vault_graph.retrieval.search.graph_candidates import GraphSearchCandidateProvider
    from vault_graph.retrieval.search.retrieval_service import RetrievalService
    from vault_graph.storage.interfaces.keyword_index import KeywordIndex
    from vault_graph.storage.interfaces.text_embeddings import TextEmbeddings
    from vault_graph.storage.interfaces.vector_store import VectorStore


class VectorIndexerStaleCounter:
    """Counts stale vector records with the M03 VectorIndexer plan, for M14 search readiness."""

    def __init__(
        self,
        *,
        metadata_store: MetadataStore,
        vector_store: VectorStore,
        text_embeddings: TextEmbeddings,
    ) -> None:
        self._metadata_store = metadata_store
        self._vector_store = vector_store
        self._text_embeddings = text_embeddings

    def stale_count(self, *, scope: QueryScope) -> int | None:
        from vault_graph.indexing.vector_index_adapter import VectorIndexer

        plan = VectorIndexer(
            chunk_store=self._metadata_store,
            vector_store=self._vector_store,
            text_embeddings=self._text_embeddings,
        ).plan(scopes=(scope,), full=False)
        return plan.upsert_count + plan.tombstone_count


@dataclass(frozen=True)
class ReadOnlyServices:
    catalog_service: CatalogService
    catalog: VaultCatalog
    metadata_store: MetadataStore
    retrieval_service: RetrievalService
    context_pack_builder: ContextPackBuilder
    context_pack_renderer: ContextPackRenderer


@dataclass(frozen=True)
class _RetrievalComponents:
    catalog_service: CatalogService
    catalog: VaultCatalog
    metadata_store: MetadataStore
    keyword_index: KeywordIndex
    vector_store: VectorStore
    text_embeddings: FastEmbedTextEmbeddings
    readiness: SearchReadiness


class ReadOnlyServiceFactory:
    def __init__(self, *, graph_home_path: Path) -> None:
        self._graph_home_path = graph_home_path

    def open_evidence_linker(self) -> EvidenceLinker:
        """Open explicit evidence/owner lookup without embeddings or a vector writer."""
        from vault_graph.operation.readiness.graph_readiness_service import ReadOnlyGraphReadiness
        from vault_graph.retrieval.evidence.evidence_read_context import build_evidence_linker
        from vault_graph.retrieval.graph.graph_contracts import current_graph_extraction_spec
        from vault_graph.storage.local.sqlite_metadata_store import SQLiteMetadataStore

        catalog_service, _ = self._catalog()
        metadata = SQLiteMetadataStore(catalog_service.metadata_path, initialize=False)
        graph = open_graph_store(catalog_service, metadata_store=metadata)
        readiness = ReadOnlyGraphReadiness(
            metadata_store=metadata,
            graph_store=graph,
            expected_spec=current_graph_extraction_spec(),
        )
        return build_evidence_linker(
            metadata_store=metadata,
            graph_store=graph,
            readiness=readiness,
            read_context_id=str(catalog_service.metadata_path.parent.parent),
        )

    def open_session_recall(self, *, vault_map_path: Path) -> RecallPorts:
        """Open session start recall ports: metadata reads, map lookup and ``usage/`` only.

        No keyword index, vector store or embeddings are opened. Raises ``RecallUnavailable``
        without creating anything when the Graph Home is not set up.
        """
        from vault_graph.context.pack.recall import RecallPorts, RecallUnavailable
        from vault_graph.interface.composition.adapters.vault_review_queue import VaultReviewQueue
        from vault_graph.storage.local.sqlite_metadata_store import SQLiteMetadataStore
        from vault_graph.storage.local.usage_log import JsonlUsageLog

        descriptor = GraphHomeResolver().resolve(self._graph_home_path)
        if not descriptor.initialized:
            raise RecallUnavailable(f"No Graph Home at {descriptor.root_path}. Run `vg setup`.")
        catalog_service = CatalogService(graph_home_path=descriptor.root_path)
        catalog = catalog_service.load_catalog()
        metadata_path = catalog_service.metadata_path
        return RecallPorts(
            scope=_ProjectRecallScope(
                vault_map_path=vault_map_path,
                catalog_service=catalog_service,
                catalog=catalog,
            ),
            documents=_MetadataRecallDocuments(
                catalog=catalog,
                metadata_store=SQLiteMetadataStore(metadata_path, initialize=False),
                metadata_path=metadata_path,
            ),
            usage=JsonlUsageLog(descriptor.root_path),
            proposals=VaultReviewQueue(catalog=catalog),
        )

    def open_read_only(self) -> ReadOnlyServices:
        from vault_graph.context.pack.context_pack_renderer import DefaultContextPackRenderer

        components = self._open_retrieval_components()
        retrieval_service = self._build_retrieval_service(components=components, include_graph=False)
        context_pack_builder = self._build_context_pack_builder(
            components=components,
            retrieval_service=retrieval_service,
        )
        return ReadOnlyServices(
            catalog_service=components.catalog_service,
            catalog=components.catalog,
            metadata_store=components.metadata_store,
            retrieval_service=retrieval_service,
            context_pack_builder=context_pack_builder,
            context_pack_renderer=DefaultContextPackRenderer(),
        )

    def open_retrieval_service(self, *, include_graph: bool = False) -> RetrievalService:
        components = self._open_retrieval_components()
        return self._build_retrieval_service(components=components, include_graph=include_graph)

    def open_context_pack_builder(self, *, include_graph: bool = False) -> ContextPackBuilder:
        components = self._open_retrieval_components()
        retrieval_service = self._build_retrieval_service(components=components, include_graph=include_graph)
        return self._build_context_pack_builder(components=components, retrieval_service=retrieval_service)

    def open_answer_service(self, *, include_graph: bool = False) -> AnswerService:
        from vault_graph.context.answer.answer_composer import ExtractiveAnswerComposer
        from vault_graph.context.answer.answer_service import AnswerService
        from vault_graph.context.answer.citation_guard import CitationGuard
        from vault_graph.context.answer.evidence_planner import EvidencePlanner

        return AnswerService(
            planner=EvidencePlanner(
                retrieval_service=self.open_retrieval_service(include_graph=include_graph),
                graph_service=self.open_graph_retrieval_service() if include_graph else None,
                project_memory_service=self.open_project_memory_service(),
                open_questions_service=self.open_issue_memory_service(),
            ),
            composer=ExtractiveAnswerComposer(),
            citation_guard=CitationGuard(),
        )

    def open_status_service(self) -> IndexService:
        from vault_graph.indexing.index_service import IndexService
        from vault_graph.operation.diagnostics.index_status_reader import IndexStatusReader
        from vault_graph.operation.readiness.graph_readiness_service import ReadOnlyGraphReadiness
        from vault_graph.retrieval.graph.graph_contracts import current_graph_extraction_spec
        from vault_graph.storage.local.chroma_vector_store import ChromaVectorStore
        from vault_graph.storage.local.graph_status_store import LocalGraphStatusStore
        from vault_graph.storage.local.sqlite_metadata_store import SQLiteMetadataStore
        from vault_graph.storage.local.vector_status_store import LocalVectorStatusStore

        catalog_service, catalog = self._catalog()
        metadata_store = SQLiteMetadataStore(catalog_service.metadata_path, initialize=False)
        graph_store = open_graph_store(catalog_service, metadata_store=metadata_store)
        text_embeddings = self._search_text_embeddings(catalog_service)
        vector_store = ChromaVectorStore(catalog_service.vector_path, initialize=False, read_only=True)
        vector_status_store = LocalVectorStatusStore(catalog_service.vector_status_path)
        graph_status_store = LocalGraphStatusStore(catalog_service.graph_status_path)
        return IndexService(
            catalog=catalog,
            metadata_store=metadata_store,
            vector_store=vector_store,
            text_embeddings=text_embeddings,
            vector_status_store=vector_status_store,
            embedding_batch_size=text_embeddings.config.embedding_batch_size,
            embedding_parallelism=text_embeddings.config.embedding_parallelism,
            embedding_lazy_load=text_embeddings.config.embedding_lazy_load,
            graph_store=graph_store,
            graph_extraction_spec=current_graph_extraction_spec(),
            graph_status_store=graph_status_store,
            status_reader=IndexStatusReader(
                catalog=catalog,
                metadata_store=metadata_store,
                vector_store=vector_store,
                text_embeddings=text_embeddings,
                vector_status_store=vector_status_store,
                embedding_batch_size=text_embeddings.config.embedding_batch_size,
                embedding_parallelism=text_embeddings.config.embedding_parallelism,
                embedding_lazy_load=text_embeddings.config.embedding_lazy_load,
                graph_readiness=ReadOnlyGraphReadiness(
                    metadata_store=metadata_store,
                    graph_store=graph_store,
                    expected_spec=current_graph_extraction_spec(),
                ),
                graph_extraction_spec=current_graph_extraction_spec(),
                graph_status_store=graph_status_store,
            ),
        )

    def open_graph_retrieval_service(self) -> GraphRetrievalService:
        from vault_graph.operation.readiness.graph_readiness_service import ReadOnlyGraphReadiness
        from vault_graph.retrieval.graph.graph_contracts import current_graph_extraction_spec
        from vault_graph.retrieval.graph.graph_retrieval_service import GraphRetrievalService
        from vault_graph.retrieval.graph.projection.vault_graph_projection_adapter import VaultGraphProjectionAdapter
        from vault_graph.storage.local.sqlite_metadata_store import SQLiteMetadataStore

        catalog_service, catalog = self._catalog()
        metadata_store = SQLiteMetadataStore(catalog_service.metadata_path, initialize=False)
        graph_store = open_graph_store(catalog_service, metadata_store=metadata_store)
        readiness = ReadOnlyGraphReadiness(
            metadata_store=metadata_store,
            graph_store=graph_store,
            expected_spec=current_graph_extraction_spec(),
        )
        return GraphRetrievalService(
            catalog=catalog,
            metadata_store=metadata_store,
            graph_store=graph_store,
            graph_readiness=readiness,
            projection=VaultGraphProjectionAdapter(),
        )

    def open_graph_resource_service(self) -> GraphResourceService:
        from vault_graph.operation.readiness.graph_readiness_service import ReadOnlyGraphReadiness
        from vault_graph.retrieval.graph.graph_contracts import current_graph_extraction_spec
        from vault_graph.retrieval.graph.graph_resource_service import GraphResourceService
        from vault_graph.storage.local.sqlite_metadata_store import SQLiteMetadataStore

        catalog_service, catalog = self._catalog()
        metadata_store = SQLiteMetadataStore(catalog_service.metadata_path, initialize=False)
        graph_store = open_graph_store(catalog_service, metadata_store=metadata_store)
        readiness = ReadOnlyGraphReadiness(
            metadata_store=metadata_store,
            graph_store=graph_store,
            expected_spec=current_graph_extraction_spec(),
        )
        return GraphResourceService(
            catalog=catalog,
            metadata_store=metadata_store,
            graph_store=graph_store,
            graph_readiness=readiness,
        )

    def open_graph_search_candidate_provider(self) -> GraphSearchCandidateProvider:
        from vault_graph.retrieval.search.graph_candidates import GraphSearchCandidateProvider

        return GraphSearchCandidateProvider(graph_retrieval_service=self.open_graph_retrieval_service())

    def open_memory_source_reader(self) -> MemorySourceReader:
        from vault_graph.context.memory.memory_source_reader import MemorySourceReader
        from vault_graph.storage.local.sqlite_metadata_store import SQLiteMetadataStore

        catalog_service, _ = self._catalog()
        return MemorySourceReader(
            metadata_store=SQLiteMetadataStore(catalog_service.metadata_path, initialize=False),
        )

    def open_decision_memory_service(self) -> DecisionMemoryService:
        from vault_graph.context.memory.decision_memory import DecisionMemoryService

        _, catalog = self._catalog()
        return DecisionMemoryService(
            catalog=catalog,
            source_reader=self.open_memory_source_reader(),
            status_service=self.open_status_service(),
            decision_trace_provider_factory=self.open_graph_retrieval_service,
        )

    def open_issue_memory_service(self) -> IssueMemoryService:
        from vault_graph.context.memory.issue_memory import IssueMemoryService

        _, catalog = self._catalog()
        return IssueMemoryService(
            catalog=catalog,
            source_reader=self.open_memory_source_reader(),
            status_service=self.open_status_service(),
        )

    def open_project_memory_service(self) -> ProjectMemoryService:
        from vault_graph.context.memory.decision_memory import DecisionMemoryService
        from vault_graph.context.memory.issue_memory import IssueMemoryService
        from vault_graph.context.memory.project_memory import ProjectMemoryService

        _, catalog = self._catalog()
        source_reader = self.open_memory_source_reader()
        status_service = self.open_status_service()
        decision_service = DecisionMemoryService(
            catalog=catalog,
            source_reader=source_reader,
            status_service=status_service,
            decision_trace_provider_factory=self.open_graph_retrieval_service,
        )
        issue_service = IssueMemoryService(
            catalog=catalog,
            source_reader=source_reader,
            status_service=status_service,
        )
        return ProjectMemoryService(
            catalog=catalog,
            source_reader=source_reader,
            decision_service=decision_service,
            issue_service=issue_service,
            status_service=status_service,
        )

    def open_timeline_memory_service(self) -> TimelineMemoryService:
        from vault_graph.context.memory.timeline_memory import TimelineMemoryService
        from vault_graph.storage.local.sqlite_metadata_store import SQLiteMetadataStore

        catalog_service, catalog = self._catalog()
        return TimelineMemoryService(
            catalog=catalog,
            metadata_store=SQLiteMetadataStore(catalog_service.metadata_path, initialize=False),
            status_service=self.open_status_service(),
        )

    def open_health_explorer_service(self) -> HealthExplorerService:
        from vault_graph.operation.diagnostics.health_explorer import HealthExplorerService

        _, catalog = self._catalog()
        return HealthExplorerService(
            catalog=catalog,
            status_service=self.open_status_service(),
        )

    def _open_retrieval_components(self) -> _RetrievalComponents:
        from vault_graph.operation.readiness.search_readiness_service import ReadOnlySearchReadiness
        from vault_graph.storage.local.chroma_vector_store import ChromaVectorStore
        from vault_graph.storage.local.sqlite_keyword_index import SQLiteKeywordIndex
        from vault_graph.storage.local.sqlite_metadata_store import SQLiteMetadataStore

        catalog_service, catalog = self._catalog()
        metadata_store = SQLiteMetadataStore(catalog_service.metadata_path, initialize=False)
        keyword_index = SQLiteKeywordIndex(catalog_service.metadata_path)
        vector_store = ChromaVectorStore(catalog_service.vector_path, initialize=False, read_only=True)
        text_embeddings = self._search_text_embeddings(catalog_service)
        readiness = ReadOnlySearchReadiness(
            metadata_store=metadata_store,
            keyword_index=keyword_index,
            vector_store=vector_store,
            text_embeddings=text_embeddings,
            vector_stale_counter=VectorIndexerStaleCounter(
                metadata_store=metadata_store,
                vector_store=vector_store,
                text_embeddings=text_embeddings,
            ),
        )
        return _RetrievalComponents(
            catalog_service=catalog_service,
            catalog=catalog,
            metadata_store=metadata_store,
            keyword_index=keyword_index,
            vector_store=vector_store,
            text_embeddings=text_embeddings,
            readiness=readiness,
        )

    def _build_retrieval_service(
        self,
        *,
        components: _RetrievalComponents,
        include_graph: bool,
    ) -> RetrievalService:
        from vault_graph.retrieval.search.context_expansion import ContextExpander
        from vault_graph.retrieval.search.retrieval_service import RetrievalService

        return RetrievalService(
            catalog=components.catalog,
            metadata_store=components.metadata_store,
            keyword_index=components.keyword_index,
            vector_store=components.vector_store,
            text_embeddings=components.text_embeddings,
            readiness=components.readiness,
            graph_candidate_provider=(self.open_graph_search_candidate_provider() if include_graph else None),
            context_expander=ContextExpander(metadata_store=components.metadata_store),
        )

    def _build_context_pack_builder(
        self,
        *,
        components: _RetrievalComponents,
        retrieval_service: RetrievalService,
    ) -> ContextPackBuilder:
        from vault_graph.context.pack.context_pack_builder import (
            MetadataContextEvidenceResolver,
            SearchContextPackBuilder,
        )

        return SearchContextPackBuilder(
            catalog=components.catalog,
            retrieval_service=retrieval_service,
            evidence_resolver=MetadataContextEvidenceResolver(metadata_store=components.metadata_store),
        )

    def _catalog(self) -> tuple[CatalogService, VaultCatalog]:
        descriptor = GraphHomeResolver().require_initialized(self._graph_home_path)
        catalog_service = CatalogService(graph_home_path=descriptor.root_path)
        catalog = catalog_service.load_catalog()
        return catalog_service, catalog

    def _search_text_embeddings(self, catalog_service: CatalogService) -> FastEmbedTextEmbeddings:
        from vault_graph.interface.composition.adapters.text_embeddings import text_embeddings_for

        return text_embeddings_for(catalog_service, local_files_only=True)


@dataclass(frozen=True)
class ProjectMemoryScope:
    """The map project of a folder and the project scope of each registered map Vault (spec 2026-11-05 §4.4.2)."""

    project_id: str
    vault_scopes: Mapping[str, MappedVaultScope]


def _body_chunks(metadata_store: MetadataStore, vault_id: str, document_id: str) -> tuple[ChunkSnapshot, ...]:
    """The chunks that make up a page body. The page card repeats the title and summary, so it is left out."""
    return tuple(
        chunk
        for chunk in metadata_store.list_document_chunks(vault_id=vault_id, document_id=document_id)
        if chunk.chunk_kind != "page_card"
    )


def metadata_body_reader(metadata_store: MetadataStore) -> Callable[[str, str], str]:
    """Read the indexed body of a page as Markdown, section headings included, by ``(vault_id, document_id)``.

    Recall and ``summarize_project_memory`` read claim tables through this one reader. Empty when
    nothing is indexed.
    """

    def body_text(vault_id: str, document_id: str) -> str:
        chunks = _body_chunks(metadata_store, vault_id, document_id)
        return "\n\n".join(f"## {chunk.section}\n\n{chunk.text}" if chunk.section else chunk.text for chunk in chunks)

    return body_text


def map_vault_scopes(vault_map: VaultMap, catalog: VaultCatalog) -> dict[str, MappedVaultScope]:
    """Linked projects and ``sharable`` of every registered Vault found in the map, by Vault id."""
    from vault_graph.interface.composition.vault_labels import vault_labels

    return {
        vault_id: vault_map.project_scope(label.name) for vault_id, label in vault_labels(vault_map, catalog).items()
    }


def project_memory_scope(cwd: Path, *, vault_map_file: Path, catalog: VaultCatalog) -> ProjectMemoryScope | None:
    """The memory scope of the ``cwd`` map project, or None when the map does not choose one.

    None means project memory is not narrowed: every page of the requested scope counts.
    """
    from vault_graph.interface.composition.query_scope_resolution import resolve_project_vaults
    from vault_graph.operation.integration.vault_map import open_vault_map

    vault_map = open_vault_map(vault_map_file).vault_map
    if vault_map is None:
        return None
    resolution = resolve_project_vaults(cwd, vault_map=vault_map, vault_catalog=catalog)
    if resolution.source != "vault-map" or resolution.project_id is None:
        return None
    return ProjectMemoryScope(project_id=resolution.project_id, vault_scopes=map_vault_scopes(vault_map, catalog))


class _ProjectRecallScope:
    """Find the registered Vaults of a folder: ``vault-map.json`` first, then project bindings."""

    def __init__(self, *, vault_map_path: Path, catalog_service: CatalogService, catalog: VaultCatalog) -> None:
        self._vault_map_path = vault_map_path
        self._catalog_service = catalog_service
        self._catalog = catalog

    def resolve(self, cwd: Path) -> RecallScope:
        from vault_graph.context.pack.recall import RecallScope
        from vault_graph.interface.composition.query_scope_resolution import resolve_project_vaults
        from vault_graph.interface.composition.vault_labels import vault_labels
        from vault_graph.operation.integration.vault_map import open_vault_map

        opening = open_vault_map(self._vault_map_path)
        warnings = [opening.warning] if opening.warning else []
        resolution = resolve_project_vaults(cwd, vault_map=opening.vault_map, vault_catalog=self._catalog)
        if resolution.source is None and self._bindings_path.exists():
            try:
                bindings, roots = self._bindings()
            except (OSError, ValueError, VaultGraphError) as exc:
                warnings.append(f"Project bindings were not read: {exc}")
            else:
                resolution = resolve_project_vaults(
                    cwd,
                    vault_map=opening.vault_map,
                    vault_catalog=self._catalog,
                    bindings=bindings,
                    repository_roots=roots,
                )
        unregistered = ", ".join(vault.name for vault in resolution.unregistered_vaults)
        if unregistered and resolution.vault_ids:
            warnings.append(f"Map Vault {unregistered} is not registered. Run `vg setup`.")
        reason = resolution.reason
        if unregistered and not resolution.vault_ids:
            reason = f"Map Vault {unregistered} is not registered in the Graph Home. Run `vg setup`."
        return RecallScope(
            project_id=resolution.project_id,
            vault_ids=resolution.vault_ids,
            reason=reason,
            warnings=tuple(warnings),
            vault_names={
                vault_id: label.name for vault_id, label in vault_labels(opening.vault_map, self._catalog).items()
            },
            # Map links name map projects, so they apply only when the map chose the project.
            vault_scopes=map_vault_scopes(opening.vault_map, self._catalog)
            if resolution.source == "vault-map" and opening.vault_map is not None
            else {},
        )

    @property
    def _bindings_path(self) -> Path:
        return self._catalog_service.graph_home_path / "configs" / "project-bindings.json"

    def _bindings(self) -> tuple[ProjectBindingReader, dict[str, Path]]:
        from vault_graph.operation.integration.project_binding_catalog import ProjectBindingCatalogService
        from vault_graph.project.code.repository_catalog import CodeRepositoryCatalogService

        repositories = CodeRepositoryCatalogService(catalog_service=self._catalog_service).load()
        bindings = ProjectBindingCatalogService(
            catalog_service=self._catalog_service,
            repository_catalog=repositories,
            vault_catalog=self._catalog,
        ).load()
        return bindings, {entry.repository_id: entry.root_path for entry in repositories.entries()}


class _MetadataRecallDocuments:
    """Read indexed document metadata for recall from the read-only metadata SQLite file."""

    def __init__(self, *, catalog: VaultCatalog, metadata_store: MetadataStore, metadata_path: Path) -> None:
        self._catalog = catalog
        self._metadata_store = metadata_store
        self._metadata_path = metadata_path

    def is_indexed(self, vault_id: str) -> bool:
        if not self._metadata_path.is_file():
            return False
        return any(state.document_id is not None for state in self._metadata_store.list_document_states((vault_id,)))

    def documents(self, vault_id: str) -> tuple[DocumentSnapshot, ...]:
        return self._metadata_store.list_documents(self._catalog.scope_for_vault_ids((vault_id,)))

    def body_tokens(self, vault_id: str, document_id: str) -> int:
        chunks = _body_chunks(self._metadata_store, vault_id, document_id)
        return sum(chunk.token_count for chunk in chunks)

    def body_text(self, vault_id: str, document_id: str) -> str:
        return metadata_body_reader(self._metadata_store)(vault_id, document_id)
