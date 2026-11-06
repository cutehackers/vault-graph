"""Graph runs that re-extract only changed documents give the same graph as a full run (spec 2026-11-05 §4.3.3, A-19).

An incremental `vg index` hands the graph the files the metadata run wrote or removed. The graph drops
and re-extracts the evidence of those documents and of the documents that link to them, keeps every
entity and relationship that still has evidence, and retires the ones left with none. Each case below
runs the same Vault change through an incremental run and through a full run on a store with the same
history, and compares entity, relationship and evidence rows. A difference fails the test, so a change
that breaks the equivalence cannot be merged (위험B7).
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from pathlib import Path

import pytest

from tests.test_metadata_indexer_paths import catalog_for
from tests.test_session_v1_v2_overlap import V2_PART3_PATH, session_vault, v2_part3_text, write
from vault_graph.indexing.extraction.entity_extractor import DeterministicEntityExtractor
from vault_graph.indexing.graph_indexer import GraphIndexApplyResult, GraphIndexPlanReport
from vault_graph.indexing.index_service import IndexRunReport, IndexService
from vault_graph.storage.local.sqlite_graph_store import SQLiteGraphStore
from vault_graph.storage.local.sqlite_metadata_store import SQLiteMetadataStore

# Columns that differ between runs by time or run id only.
ENTITY_COLUMNS = (
    "vault_id, entity_id, type, name, normalized_name, aliases_json, canonical_path, confidence, "
    "extraction_method, graph_extraction_spec_version, graph_extraction_spec_digest, status"
)
RELATIONSHIP_COLUMNS = (
    "source_vault_id, relationship_id, type, source_entity_id, target_vault_id, target_entity_id, status, "
    "confidence, extraction_method, graph_extraction_spec_version, graph_extraction_spec_digest"
)
EVIDENCE_COLUMNS = (
    "evidence_ref_id, owner_kind, owner_vault_id, owner_id, evidence_vault_id, document_id, chunk_id, "
    "content_hash, section, anchor, anchor_key, path"
)

Rows = tuple[tuple[object, ...], ...]


class GraphIndex:
    """One metadata store and one SQLite graph store, indexed together like `vg index`."""

    def __init__(self, tmp_path: Path, root: Path, name: str) -> None:
        self.catalog = catalog_for(root)
        self.graph_path = tmp_path / name / "graph.sqlite3"
        self.service = IndexService(
            catalog=self.catalog,
            metadata_store=SQLiteMetadataStore(tmp_path / name / "metadata.sqlite3", initialize=True),
            graph_store=SQLiteGraphStore.open_writable(self.graph_path),
        )

    def run(self, *, full: bool = False) -> GraphIndexApplyResult:
        report = self.service.run_apply(scope=self.catalog.default_scope(), full=full)
        return _graph_result(report)

    def rows(self, *, active_only: bool = False) -> tuple[Rows, Rows, Rows]:
        entity_filter = " WHERE status = 'active'" if active_only else ""
        relationship_filter = " WHERE status != 'deprecated'" if active_only else ""
        with sqlite3.connect(self.graph_path) as connection:
            entities = connection.execute(
                f"SELECT {ENTITY_COLUMNS} FROM graph_entities{entity_filter} ORDER BY vault_id, entity_id"
            ).fetchall()
            relationships = connection.execute(
                f"SELECT {RELATIONSHIP_COLUMNS} FROM graph_relationships{relationship_filter} "
                "ORDER BY source_vault_id, relationship_id"
            ).fetchall()
            evidence = connection.execute(
                f"SELECT {EVIDENCE_COLUMNS} FROM graph_evidence_refs ORDER BY evidence_ref_id"
            ).fetchall()
        return tuple(entities), tuple(relationships), tuple(evidence)

    def memberships(self) -> Rows:
        with sqlite3.connect(self.graph_path) as connection:
            rows = connection.execute(
                "SELECT record_kind, record_vault_id, record_id, actual_scope FROM graph_record_scopes "
                "ORDER BY record_kind, record_vault_id, record_id, actual_scope"
            ).fetchall()
        return tuple(rows)

    def latest_counts(self) -> tuple[int, int]:
        with sqlite3.connect(self.graph_path) as connection:
            row = connection.execute(
                "SELECT entity_count, relationship_count FROM graph_revisions "
                "ORDER BY updated_at DESC, graph_index_revision DESC LIMIT 1"
            ).fetchone()
        return int(row[0]), int(row[1])


def _graph_result(report: IndexRunReport) -> GraphIndexApplyResult:
    assert isinstance(report.graph, GraphIndexApplyResult)
    assert report.graph.failed is False, report.graph.error
    return report.graph


def wiki_vault(root: Path) -> Path:
    write(root, "wiki/alpha.md", "---\ntitle: Alpha\ntags: [shared]\n---\n# Alpha\nAlpha body.\n")
    write(
        root,
        "wiki/beta.md",
        "---\ntitle: Beta\ntags: [shared]\n---\n# Beta\nBeta links to [[gamma]] and [[epsilon]].\n",
    )
    write(root, "wiki/gamma.md", "---\ntitle: Gamma\n---\n# Gamma\nGamma body.\n")
    write(root, "wiki/delta.md", "---\ntitle: Delta\n---\n# Delta\nDelta points at [Beta](beta.md).\n")
    write(root, "wiki/old-plan.md", "---\ntitle: Old Plan\ntype: decision\n---\n# Old Plan\nThe old plan.\n")
    for index in range(6):
        write(
            root,
            f"wiki/other-{index}.md",
            f"---\ntitle: Other {index}\ntags: [unrelated-{index}]\n---\n# Other {index}\nOther body {index}.\n",
        )
    return root


def add_link(root: Path) -> None:
    write(root, "wiki/alpha.md", "---\ntitle: Alpha\ntags: [shared]\n---\n# Alpha\nAlpha now links to [[gamma]].\n")


def rename_link_target(root: Path) -> None:
    """beta links to gamma. Only gamma changes, so beta's evidence for gamma must be re-extracted."""
    write(root, "wiki/gamma.md", "---\ntitle: Gamma Renamed\ntype: decision\n---\n# Gamma\nGamma body.\n")


def add_unresolved_link_target(root: Path) -> None:
    """beta's link to epsilon pointed at no page. The new page turns it into a document link."""
    write(root, "wiki/epsilon.md", "---\ntitle: Epsilon\n---\n# Epsilon\nEpsilon body.\n")


def supersede(root: Path) -> None:
    write(
        root,
        "wiki/new-plan.md",
        "---\ntitle: New Plan\ntype: decision\nsupersedes: wiki/old-plan.md\n---\n# New Plan\nReplaces the old plan.\n",
    )


def delete_linking_page(root: Path) -> None:
    (root / "wiki/delta.md").unlink()


def delete_linked_page(root: Path) -> None:
    """beta and nothing else links to gamma. Deleting gamma turns beta's link into an unresolved one."""
    (root / "wiki/gamma.md").unlink()


def remove_tag(root: Path) -> None:
    write(root, "wiki/alpha.md", "---\ntitle: Alpha\n---\n# Alpha\nAlpha body.\n")


CASES: dict[str, Callable[[Path], None]] = {
    "document adds a link": add_link,
    "linked document changes": rename_link_target,
    "new document receives a link": add_unresolved_link_target,
    "supersedes changes the family": supersede,
    "linking document is deleted": delete_linking_page,
    "linked document is deleted": delete_linked_page,
    "tag loses one of its documents": remove_tag,
}


@pytest.fixture
def extracted_chunks(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Paths of the chunks the entity extractor read, in order."""
    seen: list[str] = []
    original = DeterministicEntityExtractor.extract

    def spy(self: DeterministicEntityExtractor, **kwargs: object) -> object:
        seen.append(kwargs["chunk"].path)  # type: ignore[attr-defined]
        return original(self, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(DeterministicEntityExtractor, "extract", spy)
    return seen


def assert_matches_full_run(tmp_path: Path, root: Path, incremental: GraphIndex, reference: GraphIndex) -> None:
    """Rows equal a full run with the same history, and the live rows equal a full run from nothing."""
    reference.run(full=True)
    assert incremental.rows() == reference.rows()
    assert incremental.memberships() == reference.memberships()
    assert incremental.latest_counts() == reference.latest_counts()
    fresh = GraphIndex(tmp_path, root, "fresh")
    fresh.run(full=True)
    assert incremental.rows(active_only=True)[:2] == fresh.rows(active_only=True)[:2]
    assert incremental.rows()[2] == fresh.rows()[2]


@pytest.mark.parametrize("change", CASES.values(), ids=CASES.keys())
def test_incremental_graph_matches_full_run(
    tmp_path: Path, extracted_chunks: list[str], change: Callable[[Path], None]
) -> None:
    root = wiki_vault(tmp_path / "vault")
    incremental = GraphIndex(tmp_path, root, "incremental")
    reference = GraphIndex(tmp_path, root, "reference")
    incremental.run()
    reference.run()
    change(root)
    extracted_chunks.clear()

    result = incremental.run()

    assert result.mode == "incremental"
    assert not any(path.startswith("wiki/other-") for path in extracted_chunks)
    assert result.reconcile_plan is not None
    assert not any(record.name.startswith("Other") for record in result.reconcile_plan.entity_upserts)
    assert_matches_full_run(tmp_path, root, incremental, reference)


def test_session_v2_part_addition_matches_full_run(tmp_path: Path, extracted_chunks: list[str]) -> None:
    root = session_vault(tmp_path / "vault", with_v2=False)
    incremental = GraphIndex(tmp_path, root, "incremental")
    reference = GraphIndex(tmp_path, root, "reference")
    incremental.run()
    reference.run()
    write(root, V2_PART3_PATH, v2_part3_text())
    extracted_chunks.clear()

    incremental.run()

    assert "wiki/notes/note.md" not in extracted_chunks
    assert_matches_full_run(tmp_path, root, incremental, reference)


def test_run_without_changed_files_extracts_nothing_and_writes_no_record(
    tmp_path: Path, extracted_chunks: list[str]
) -> None:
    root = wiki_vault(tmp_path / "vault")
    index = GraphIndex(tmp_path, root, "state")
    index.run()
    before = index.rows()
    extracted_chunks.clear()

    result = index.run()

    assert extracted_chunks == []
    plan = result.reconcile_plan
    assert plan is not None
    assert (plan.entity_upserts, plan.relationship_upserts, plan.evidence_ref_upserts) == ((), (), ())
    assert (plan.entity_tombstones, plan.relationship_tombstones) == ((), ())
    assert len(plan.graph_revision_rows) == 1
    assert index.rows() == before


def test_several_incremental_runs_in_a_row_match_full_run(tmp_path: Path) -> None:
    root = wiki_vault(tmp_path / "vault")
    incremental = GraphIndex(tmp_path, root, "incremental")
    reference = GraphIndex(tmp_path, root, "reference")
    incremental.run()
    reference.run()
    for change in CASES.values():
        change(root)
        incremental.run()
        reference.run()

    assert_matches_full_run(tmp_path, root, incremental, reference)


def test_dry_run_plans_only_the_changed_documents(tmp_path: Path) -> None:
    root = wiki_vault(tmp_path / "vault")
    index = GraphIndex(tmp_path, root, "state")
    index.run()
    total_entities = len(index.rows(active_only=True)[0])
    add_link(root)

    report = index.service.run_plan(scope=index.catalog.default_scope())

    assert isinstance(report.graph, GraphIndexPlanReport)
    upserts = report.graph.reconcile_plan.entity_upserts
    assert upserts
    assert len(upserts) < total_entities // 2
    assert {record.canonical_path for record in upserts if record.canonical_path} <= {
        "wiki/alpha.md",
        "wiki/gamma.md",
    }


def test_full_run_after_metadata_changed_without_graph_falls_back_to_whole_scope(tmp_path: Path) -> None:
    """Metadata written by a run that did not reach the graph is not in this run's changed list.

    The graph sees a metadata revision it never recorded and reconciles the whole scope instead.
    """
    root = wiki_vault(tmp_path / "vault")
    incremental = GraphIndex(tmp_path, root, "incremental")
    reference = GraphIndex(tmp_path, root, "reference")
    incremental.run()
    reference.run()
    add_link(root)
    incremental.service.apply(scope=incremental.catalog.default_scope())
    reference.service.apply(scope=reference.catalog.default_scope())

    incremental.run()

    assert_matches_full_run(tmp_path, root, incremental, reference)
