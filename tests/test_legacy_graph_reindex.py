"""Real SQLite and publication regressions for replaced or removed evidence."""

import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest
from pytest import MonkeyPatch
from typer.testing import CliRunner

from tests.test_cli_graph_indexing import write_page
from tests.test_graph_module_public_integration import fingerprints, indexed_home
from tests.test_graph_store_contract import make_entity, make_plan
from vault_graph.cli.main import app
from vault_graph.errors import GraphStoreUnavailable
from vault_graph.graph.graph_contracts import GraphTombstone, current_graph_extraction_spec
from vault_graph.graph.graph_identity import graph_scope_key
from vault_graph.graph.graph_query import GraphEntityQuery
from vault_graph.ingestion.vault_catalog import QueryScope
from vault_graph.storage.local.sqlite_graph_store import SQLiteGraphStore
from vault_graph.vault_scope.catalog_service import CatalogService


@pytest.mark.parametrize("full", [False, True])
@pytest.mark.parametrize("mutation", ["replace", "delete"])
def test_cli_reindexes_changed_evidence_without_dangling_refs(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    full: bool,
    mutation: str,
) -> None:
    vault, home = indexed_home(tmp_path, monkeypatch)
    original = CatalogService(graph_home_path=home)
    old_generation = original.metadata_path.parent.parent
    old_files = fingerprints(old_generation)
    if mutation == "replace":
        write_page(vault, "wiki/source.md", "---\ntitle: Source\n---\n# Revised\nChanged text and [[target]].\n")
    else:
        (vault / "wiki/source.md").unlink()
    source_before = fingerprints(vault)
    args = ["index", "--graph-home", str(home)] + (["--full"] if full else [])
    for _ in range(2):
        indexed = CliRunner().invoke(app, args)
        assert indexed.exit_code == 0, f"{indexed.output}\n{indexed.exception!r}"
        current = CatalogService(graph_home_path=home)
        with sqlite3.connect(current.metadata_path) as metadata:
            keys = set(metadata.execute("SELECT vault_id, chunk_id FROM chunks"))
        with sqlite3.connect(current.graph_path) as graph:
            refs = graph.execute("SELECT evidence_vault_id, chunk_id FROM graph_evidence_refs").fetchall()
        assert all(key in keys for key in refs)
        assert fingerprints(vault) == source_before
        assert fingerprints(old_generation) == old_files


def test_scoped_reconcile_preserves_other_scope_and_vault_evidence(tmp_path: Path) -> None:
    store = SQLiteGraphStore.open_writable(tmp_path / "graph.sqlite3")
    wiki = QueryScope(vault_ids=("default",), content_scopes=("wiki",))
    docs = QueryScope(vault_ids=("default",), content_scopes=("docs",))
    source = make_entity("default")
    old_ref = source.evidence_refs[0]
    other_ref = replace(
        old_ref, evidence_ref_id="docs-ref", document_id="docs-doc", chunk_id="docs-chunk", path="docs/page.md"
    )
    shared = replace(source, canonical_path=None, evidence_refs=(old_ref, other_ref))
    store.apply_reconcile_plan(make_plan(entities=(shared,), relationships=(), scope=wiki))
    store.apply_reconcile_plan(make_plan(entities=(shared,), relationships=(), scope=docs))
    other_vault = make_entity("other")
    store.apply_reconcile_plan(make_plan(entities=(other_vault,), relationships=()))
    new_ref = replace(old_ref, evidence_ref_id="new-ref", chunk_id="new-chunk")
    updated = replace(shared, evidence_refs=(new_ref,))
    store.apply_reconcile_plan(make_plan(entities=(updated,), relationships=(), scope=wiki))
    current = store.get_entity(vault_id="default", entity_id=source.entity_id)
    assert current is not None
    assert set(current.evidence_refs) == {new_ref, other_ref}
    assert store.get_entity(vault_id="other", entity_id=other_vault.entity_id) == other_vault


def test_scoped_tombstone_preserves_shared_owner_in_other_scope(tmp_path: Path) -> None:
    store = SQLiteGraphStore.open_writable(tmp_path / "graph.sqlite3")
    wiki = QueryScope(vault_ids=("default",), content_scopes=("wiki",))
    docs = QueryScope(vault_ids=("default",), content_scopes=("docs",))
    source = make_entity("default")
    ref = replace(source.evidence_refs[0], evidence_ref_id="docs-ref", path="docs/page.md", chunk_id="docs-chunk")
    shared = replace(source, canonical_path=None, evidence_refs=(*source.evidence_refs, ref))
    cross_wiki = replace(wiki, include_cross_vault=True)
    for scope in (wiki, cross_wiki, docs):
        store.apply_reconcile_plan(make_plan(entities=(shared,), relationships=(), scope=scope))
    spec = current_graph_extraction_spec()
    tombstone = GraphTombstone(
        "tombstone",
        "entity",
        "default",
        shared.entity_id,
        graph_scope_key(wiki),
        "removed",
        "run-2",
        "graph-2",
        spec.spec_version,
        spec.spec_digest,
        "2026-10-15T00:00:00Z",
    )
    plan = replace(make_plan(entities=(), relationships=(), scope=wiki), entity_tombstones=(tombstone,))
    store.apply_reconcile_plan(plan)
    matches = store.find_entities(GraphEntityQuery(text=shared.name, actual_scopes=(docs,), limit=10)).matches
    assert len(matches) == 1
    assert matches[0].entity.evidence_refs == (ref,)
    assert store.find_entities(GraphEntityQuery(text=shared.name, actual_scopes=(wiki,), limit=10)).matches == ()
    assert store.find_entities(GraphEntityQuery(text=shared.name, actual_scopes=(cross_wiki,), limit=10)).matches == ()
    assert store.current_manifest((wiki,)).tombstone_rows == (tombstone,)


def test_reconcile_failure_rolls_back_reference_cleanup_and_owner_changes(tmp_path: Path) -> None:
    store = SQLiteGraphStore.open_writable(tmp_path / "graph.sqlite3")
    source = make_entity("default")
    store.apply_reconcile_plan(make_plan(entities=(source,), relationships=()))
    scope = QueryScope(vault_ids=("default",), content_scopes=("wiki",))
    before = store.current_manifest((scope,))
    with store._connect() as connection:
        connection.execute("""CREATE TRIGGER reject_revision BEFORE INSERT ON graph_revisions
                              BEGIN SELECT RAISE(ABORT, 'injected failure'); END""")
    changed = replace(
        source,
        evidence_refs=(
            replace(
                source.evidence_refs[0],
                evidence_ref_id="new-ref",
                chunk_id="new-chunk",
            ),
        ),
    )
    with pytest.raises(GraphStoreUnavailable, match="injected failure"):
        store.apply_reconcile_plan(make_plan(entities=(changed,), relationships=()))
    assert store.current_manifest((scope,)) == before
    assert store.get_entity(vault_id="default", entity_id=source.entity_id) == source


def test_cleanup_repairs_historical_refs_but_retains_unattributed_and_unmentioned_refs(tmp_path: Path) -> None:
    store = SQLiteGraphStore.open_writable(tmp_path / "graph.sqlite3")
    source = make_entity("default")
    historical = make_entity("default", name="Retired")
    other = make_entity("default", name="Unmentioned")
    unknown = replace(source.evidence_refs[0], evidence_ref_id="unknown-ref", path=None, anchor="unknown")
    source = replace(source, evidence_refs=(*source.evidence_refs, unknown))
    store.apply_reconcile_plan(make_plan(entities=(source, historical, other), relationships=()))
    with store._connect() as connection:
        connection.execute(
            "UPDATE graph_entities SET status = 'tombstoned' WHERE entity_id = ?", (historical.entity_id,)
        )
    updated = replace(
        source,
        evidence_refs=(
            replace(
                source.evidence_refs[0],
                evidence_ref_id="new-ref",
                chunk_id="new-chunk",
            ),
        ),
    )
    store.apply_reconcile_plan(make_plan(entities=(updated,), relationships=()))
    result = store.get_entity(vault_id="default", entity_id=source.entity_id)
    assert result is not None
    assert set(result.evidence_refs) == {updated.evidence_refs[0], unknown}
    assert store.get_entity(vault_id="default", entity_id=historical.entity_id) is None
    assert store.get_entity(vault_id="default", entity_id=other.entity_id) == other


def test_cleanup_preserves_desired_refs_without_owner_upserts(tmp_path: Path) -> None:
    store = SQLiteGraphStore.open_writable(tmp_path / "graph.sqlite3")
    source = make_entity("default")
    initial = make_plan(entities=(source,), relationships=())
    store.apply_reconcile_plan(initial)
    store.apply_reconcile_plan(replace(initial, entity_upserts=()))
    assert store.get_entity(vault_id="default", entity_id=source.entity_id) == source


def test_cleanup_treats_prefix_wildcards_as_literal_path_components(tmp_path: Path) -> None:
    store = SQLiteGraphStore.open_writable(tmp_path / "graph.sqlite3")
    scope = QueryScope(vault_ids=("default",), content_scopes=("wiki/special%_",))
    source = make_entity("default", path="wiki/special%_/old.md")
    retained = replace(
        source.evidence_refs[0],
        evidence_ref_id="retained",
        path="wiki/specialAA/keep.md",
        document_id="other-doc",
        chunk_id="other-chunk",
    )
    source = replace(source, evidence_refs=(*source.evidence_refs, retained))
    store.apply_reconcile_plan(make_plan(entities=(source,), relationships=(), scope=scope))
    updated_ref = replace(source.evidence_refs[0], evidence_ref_id="new-ref", chunk_id="new-chunk")
    store.apply_reconcile_plan(
        make_plan(entities=(replace(source, evidence_refs=(updated_ref,)),), relationships=(), scope=scope)
    )
    result = store.get_entity(vault_id="default", entity_id=source.entity_id)
    assert result is not None
    assert set(result.evidence_refs) == {updated_ref, retained}
