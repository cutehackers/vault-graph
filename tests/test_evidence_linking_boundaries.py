"""Acceptance checks for bounded, read-only evidence linking."""

from __future__ import annotations

import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest
from pytest import MonkeyPatch
from typer.testing import CliRunner

from tests.test_cli_graph_indexing import write_page
from tests.test_evidence_linking import Lookup, linked_store
from tests.test_graph_module_public_integration import fingerprints, indexed_home
from tests.test_graph_resource_reader import make_readiness
from vault_graph.app.read_only_service_factory import ReadOnlyServiceFactory
from vault_graph.cli.main import app
from vault_graph.errors import RetrievalContractError
from vault_graph.graph.graph_readiness import GraphReadiness
from vault_graph.ingestion.vault_catalog import QueryScope
from vault_graph.projection_publication.projection_generation import ProjectionGenerationManager
from vault_graph.storage.interfaces.evidence_owner_lookup import EvidenceOwnerRecord
from vault_graph.storage.interfaces.metadata_store import EvidenceReference, MetadataStore
from vault_graph.storage.local.sqlite_metadata_store import SQLiteMetadataStore
from vault_graph.vault_adapter.evidence_linking import (
    EvidenceKey,
    EvidenceLinker,
    EvidenceSourceRevision,
    GraphLinksRequest,
)
from vault_graph.vault_scope.catalog_service import CatalogService


class MetadataSpy:
    def __init__(self, calls: list[str], evidence: EvidenceReference | None = None) -> None:
        self.calls = calls
        self.evidence = evidence

    def resolve_chunk_evidence(self, **kwargs: object) -> EvidenceReference | None:
        self.calls.append("metadata")
        return self.evidence


class OwnerSpy:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls

    def lookup_evidence_owners(self, **kwargs: object) -> tuple[EvidenceOwnerRecord, ...]:
        self.calls.append("lookup")
        return ()


@pytest.mark.parametrize(
    ("keys", "max_keys"),
    [
        ((("main", "doc", "chunk"),), 0),
        ((("main", "doc", "chunk"),), -1),
        ((("main", "doc", "chunk"),), True),
        ((("main", "doc", "chunk"),), 1.5),
        ((("main", "doc", "a"), ("main", "doc", "b")), 1),
        ((("main", "", "chunk"),), 1),
        ((("main", "doc", "  "),), 1),
        ((("main", "doc"),), 1),
        ((["main", "doc", "chunk"],), 1),
        ((("main", "doc", 7),), 1),
    ],
)
def test_invalid_requests_are_denied_before_any_provider_access(keys: object, max_keys: object) -> None:
    calls: list[str] = []
    scope = QueryScope(("main",), ("wiki",))

    def revisions(scopes: tuple[QueryScope, ...]) -> tuple[EvidenceSourceRevision, ...]:
        calls.append("revision")
        return (EvidenceSourceRevision("graph", "graph-1"),)

    def readiness(scopes: tuple[QueryScope, ...]) -> GraphReadiness:
        calls.append("readiness")
        raise AssertionError("invalid request reached readiness")

    linker = EvidenceLinker(
        metadata_store=cast(MetadataStore, MetadataSpy(calls)),
        owner_lookup=OwnerSpy(calls),
        readiness=readiness,
        revision_reader=revisions,
    )
    request = GraphLinksRequest(cast(tuple[EvidenceKey, ...], keys), (scope,), False, cast(int, max_keys), 10)
    with pytest.raises(RetrievalContractError):
        linker.find_graph_links(request)
    assert calls == []


def test_owner_lookup_failure_propagates_instead_of_returning_empty_success(tmp_path: Path) -> None:
    store, scope, key, _ = linked_store(tmp_path)

    class FailedLookup(Lookup):
        def lookup_evidence_owners(self, **kwargs: object) -> tuple[EvidenceOwnerRecord, ...]:
            raise RuntimeError("owner lookup failed")

    linker = EvidenceLinker(
        metadata_store=store,
        owner_lookup=FailedLookup(()),
        readiness=make_readiness,
        revision_reader=lambda scopes: (EvidenceSourceRevision("graph", "graph-1"),),
    )
    with pytest.raises(RuntimeError, match="^owner lookup failed$"):
        linker.find_graph_links(GraphLinksRequest((key,), (scope,), False, 1, 10))


@pytest.mark.parametrize("path", ["docs/private.md", "../wiki/private.md", "/wiki/private.md", "wiki\\private.md"])
def test_evidence_path_is_checked_before_owner_lookup(tmp_path: Path, path: str) -> None:
    store, scope, key, _ = linked_store(tmp_path)
    evidence = store.resolve_chunk_evidence(vault_id=key[0], document_id=key[1], chunk_id=key[2])
    assert evidence is not None
    calls: list[str] = []
    linker = EvidenceLinker(
        metadata_store=cast(MetadataStore, MetadataSpy(calls, replace(evidence, path=path))),
        owner_lookup=OwnerSpy(calls),
        readiness=make_readiness,
        revision_reader=lambda scopes: (EvidenceSourceRevision("graph", "graph-1"),),
    )
    with pytest.raises(RetrievalContractError, match="outside requested scope"):
        linker.find_graph_links(GraphLinksRequest((key,), (replace(scope, content_scopes=("wiki",)),), False, 1, 10))
    assert calls == ["metadata"]


def prepared_home(tmp_path: Path, monkeypatch: MonkeyPatch, backend: str) -> tuple[Path, Path]:
    vault, home = indexed_home(tmp_path, monkeypatch)
    if backend == "document":
        switched = CliRunner().invoke(app, ["index", "--graph-home", str(home), "--graph-backend", "document"])
        assert switched.exit_code == 0, switched.output
    return vault, home


def request_for_home(home: Path) -> GraphLinksRequest:
    catalog = CatalogService(graph_home_path=home)
    scope = catalog.load_catalog().default_scope()
    metadata = SQLiteMetadataStore(catalog.metadata_path, initialize=False)
    keys = tuple((chunk.vault_id, chunk.document_id, chunk.chunk_id) for chunk in metadata.list_chunks(scope))
    return GraphLinksRequest(keys, (scope,), False, 100, 100)


@pytest.mark.parametrize("backend", ["legacy", "document"])
def test_open_linker_keeps_selected_generation_after_new_publication(
    tmp_path: Path, monkeypatch: MonkeyPatch, backend: str
) -> None:
    vault, home = prepared_home(tmp_path, monkeypatch, backend)
    manager = ProjectionGenerationManager(home)
    old_generation = manager.active_layout()
    assert old_generation is not None
    request = request_for_home(home)
    linker = ReadOnlyServiceFactory(graph_home_path=home).open_evidence_linker()
    original = linker.find_graph_links(request)
    assert original.coverage == "complete" and original.links
    old_files = fingerprints(old_generation.root_path)
    write_page(vault, "wiki/new.md", "# New\nNew evidence referencing [[target]].\n")
    published = CliRunner().invoke(app, ["index", "--graph-home", str(home)])
    assert published.exit_code == 0, published.output
    current = manager.active_layout()
    assert current is not None and current.generation_id != old_generation.generation_id
    before = fingerprints(home), fingerprints(vault)
    assert linker.find_graph_links(request) == original
    fresh = ReadOnlyServiceFactory(graph_home_path=home).open_evidence_linker().find_graph_links(request_for_home(home))
    assert fresh.coverage == "complete" and fresh.links
    assert fresh.source_revisions != original.source_revisions
    assert fingerprints(old_generation.root_path) == old_files
    assert (fingerprints(home), fingerprints(vault)) == before


@pytest.mark.parametrize("backend", ["legacy", "document"])
def test_explicit_lookup_never_constructs_models_or_chroma(
    tmp_path: Path, monkeypatch: MonkeyPatch, backend: str
) -> None:
    from vault_graph.vault_adapter.text_embeddings import FastEmbedTextEmbeddings
    from vault_graph.vault_adapter.vector_store import ChromaVectorStore

    vault, home = prepared_home(tmp_path, monkeypatch, backend)
    request = request_for_home(home)
    before = fingerprints(home), fingerprints(vault)

    def denied_constructor(*args: object, **kwargs: object) -> None:
        raise AssertionError("evidence lookup constructed model or Chroma")

    monkeypatch.setattr(FastEmbedTextEmbeddings, "__init__", denied_constructor)
    monkeypatch.setattr(ChromaVectorStore, "__init__", denied_constructor)
    result = ReadOnlyServiceFactory(graph_home_path=home).open_evidence_linker().find_graph_links(request)
    assert result.coverage == "complete" and result.links
    assert (fingerprints(home), fingerprints(vault)) == before


@pytest.mark.parametrize("backend", ["legacy", "document"])
def test_new_lookup_path_does_not_import_model_or_chroma_modules(
    tmp_path: Path, monkeypatch: MonkeyPatch, backend: str
) -> None:
    vault, home = prepared_home(tmp_path, monkeypatch, backend)
    before = fingerprints(home), fingerprints(vault)
    script = """
import importlib.abc
import sys
from pathlib import Path
class ForbiddenModelImports(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        blocked = (
            "fastembed", "chromadb", "torch", "huggingface_hub",
            "vault_graph.vault_adapter.text_embeddings", "vault_graph.vault_adapter.vector_store",
            "vault_graph.embeddings.fastembed_text_embeddings", "vault_graph.storage.local.chroma_vector_store",
        )
        if any(fullname == name or fullname.startswith(name + ".") for name in blocked):
            raise AssertionError("evidence lookup imported " + fullname)
sys.meta_path.insert(0, ForbiddenModelImports())
from vault_graph.app.read_only_service_factory import ReadOnlyServiceFactory
from vault_graph.storage.local.sqlite_metadata_store import SQLiteMetadataStore
from vault_graph.vault_adapter.evidence_linking import GraphLinksRequest
from vault_graph.vault_scope.catalog_service import CatalogService
home = Path(sys.argv[1])
catalog = CatalogService(graph_home_path=home)
scope = catalog.load_catalog().default_scope()
metadata = SQLiteMetadataStore(catalog.metadata_path, initialize=False)
keys = tuple((chunk.vault_id, chunk.document_id, chunk.chunk_id) for chunk in metadata.list_chunks(scope))
result = ReadOnlyServiceFactory(graph_home_path=home).open_evidence_linker().find_graph_links(
    GraphLinksRequest(keys, (scope,), False, 100, 100)
)
assert result.coverage == "complete" and result.links
print("lookup passed")
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(home)], capture_output=True, text=True, check=False, timeout=30
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "lookup passed"
    assert (fingerprints(home), fingerprints(vault)) == before
