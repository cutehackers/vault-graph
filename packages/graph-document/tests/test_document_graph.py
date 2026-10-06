from __future__ import annotations

from dataclasses import replace
from typing import Any, cast
from pathlib import Path

import pytest

from graph_document import (
    CapacityError,
    Document,
    DocumentFeatures,
    EntityFact,
    EntityKey,
    EvidenceLocation,
    ExtractedDocument,
    ExtractionProfile,
    GraphDocument,
    GraphLimits,
    InvalidCursorError,
    InvalidDocumentError,
    InvalidExtractionError,
    ItemQuery,
    LocatedValue,
    ReadLimits,
    ReadOnlyStoreError,
    Reference,
    RevisionConflictError,
    SourceRevisionConflictError,
    StatedRelation,
)

LIMITS = GraphLimits(10, 10_000, 100_000, 100, 100, 100, 100)
READ = ReadLimits(100, 100, 100, 10, 100_000)
PROFILE = ExtractionProfile()


def open_store(tmp_path: Path) -> GraphDocument:
    return GraphDocument.open(
        tmp_path / "graph.sqlite", mode="create", limits=LIMITS, profile=PROFILE
    )


def test_rule_extraction_and_reopen_without_source_text(tmp_path: Path) -> None:
    tag = EvidenceLocation("tag", (0, 5))
    heading = EvidenceLocation("heading", (6, 10))
    ref = EvidenceLocation("link")
    document = Document(
        "a",
        "v1",
        "A",
        "Alpha Beta",
        DocumentFeatures(
            tags=(LocatedValue("Alpha", tag),),
            headings=(LocatedValue("Beta", heading),),
            references=(Reference(target_document_id="missing", label="Missing", location=ref),),
        ),
        "source://a",
    )
    with open_store(tmp_path) as store:
        result = store.update_documents((document,), collection_id="c", expected_revision=0)
        assert result.graph_revision == 1
        snapshot = store.read(collection_id="c", selection="all", limits=READ)
        assert {(node.kind, node.key) for node in snapshot.nodes} == {
            ("document", "a"),
            ("document", "missing"),
            ("concept", "alpha"),
            ("concept", "beta"),
        }
        assert {edge.relation_type for edge in snapshot.edges} == {"mentions", "links_to"}
        assert (
            next(node for node in snapshot.nodes if node.key == "missing").source_available is False
        )
        assert all(e.excerpt is None for e in snapshot.evidence)
        assert snapshot.evidence_for(edge_ids=(snapshot.edges[0].edge_id,)).by_edge_id[0][1]
    assert "Alpha Beta" not in (tmp_path / "graph.sqlite").read_bytes().decode("utf-8", "ignore")
    with GraphDocument.open(
        tmp_path / "graph.sqlite", mode="read_only", limits=LIMITS, profile=PROFILE
    ) as store:
        assert store.read(collection_id="c", selection="all", limits=READ).digest == snapshot.digest
        with pytest.raises(ReadOnlyStoreError):
            store.remove_documents(("a",), collection_id="c", expected_revision=1)
    assert snapshot.find_items(ItemQuery("alpha")).items[0].key == "alpha"


def test_shared_edge_selection_and_contribution_removal(tmp_path: Path) -> None:
    relation = StatedRelation(
        EntityKey("concept", "x"),
        EntityKey("concept", "y"),
        "depends_on",
        EvidenceLocation("stated"),
    )
    a = Document("a", "1", "A", "", DocumentFeatures(stated_relations=(relation,)))
    b = Document("b", "1", "B", "", DocumentFeatures(stated_relations=(relation,)))
    with open_store(tmp_path) as store:
        store.update_documents((a, b), collection_id="c", expected_revision=0)
        both = store.read(collection_id="c", selection="all", limits=READ)
        assert len(both.edges) == 1
        edge = both.edges[0]
        assert len(both.evidence_for(edge_ids=(edge.edge_id,)).by_edge_id[0][1]) == 2
        one = store.read(collection_id="c", selection=("a",), limits=READ)
        assert len(one.edges) == 1
        assert len(one.evidence_for(edge_ids=(edge.edge_id,)).by_edge_id[0][1]) == 1
        store.remove_documents(("a",), collection_id="c", expected_revision=1)
        after = store.read(collection_id="c", selection="all", limits=READ)
        assert len(after.edges) == 1
        assert after.edges[0].edge_id == edge.edge_id
        assert len(after.evidence_for(edge_ids=(edge.edge_id,)).by_edge_id[0][1]) == 1
        assert len(both.evidence) > len(after.evidence)  # immutable earlier read
        store.remove_documents(("b",), collection_id="c", expected_revision=2)
        empty = store.read(collection_id="c", selection="all", limits=READ)
        assert not empty.edges and not empty.nodes and not empty.evidence


def test_cas_noop_source_revision_and_partial_batch(tmp_path: Path) -> None:
    a = Document("a", "v1", "A", "")
    b = Document("b", "v1", "B", "")
    with open_store(tmp_path) as store:
        store.update_documents((a, b), collection_id="c", expected_revision=0)
        result = store.update_documents((a,), collection_id="c", expected_revision=1)
        assert result.graph_revision == 1 and result.changed_document_ids == ()
        with pytest.raises(RevisionConflictError) as conflict:
            store.update_documents((a,), collection_id="c", expected_revision=0)
        assert conflict.value.current_revision == 1
        with pytest.raises(SourceRevisionConflictError):
            store.update_documents(
                (replace(a, title="changed"),), collection_id="c", expected_revision=1
            )
        result = store.update_documents(
            (replace(a, source_revision="v2"),), collection_id="c", expected_revision=1
        )
        assert result.graph_revision == 2
        snapshot = store.read(collection_id="c", selection="all", limits=READ)
        assert {d.document_id for d in snapshot.documents} == {"a", "b"}
        assert (
            store.remove_documents(
                ("unknown",), collection_id="c", expected_revision=2
            ).graph_revision
            == 2
        )


def test_input_canonicalization_and_cursor_binding(tmp_path: Path) -> None:
    one = LocatedValue("Same", EvidenceLocation("a"))
    two = LocatedValue("Same", EvidenceLocation("b"))
    a = Document("a", "1", "A", "", DocumentFeatures(tags=(one, two)))
    permuted = Document("a", "1", "A", "", DocumentFeatures(tags=(two, one, one)))
    assert a.input_digest == permuted.input_digest
    with open_store(tmp_path) as store:
        store.update_documents((a,), collection_id="c", expected_revision=0)
        snapshot = store.read(collection_id="c", selection="all", limits=READ)
        page = snapshot.find_items(ItemQuery("Same", limit=1))
        assert len(page.items) == 1
        assert page.next_cursor is None  # duplicate fact has one logical concept
        with pytest.raises(InvalidCursorError):
            snapshot.find_items(ItemQuery("Else", cursor="invalid"))
        assert (
            store.update_documents(
                (permuted,), collection_id="c", expected_revision=1
            ).graph_revision
            == 1
        )


def test_limits_and_bad_extractor_do_not_change_db(tmp_path: Path) -> None:
    document = Document("a", "1", "A", "")
    with GraphDocument.open(
        tmp_path / "limited.sqlite",
        mode="create",
        limits=GraphLimits(1, 10, 10, 1, 1, 1, 100),
        profile=PROFILE,
    ) as store:
        with pytest.raises(CapacityError):
            store.update_documents((document,), collection_id="c", expected_revision=0)

    class BadExtractor:
        def extract(self, document: Document, *, profile: ExtractionProfile) -> ExtractedDocument:
            return ExtractedDocument(
                document.document_id,
                document.input_digest,
                profile.profile_digest,
                (
                    EntityFact(
                        EntityKey("document", document.document_id),
                        "A",
                        (),
                        "document",
                        (EvidenceLocation("document"),),
                    ),
                ),
                (),
                (EvidenceLocation("unused"),),
            )

    with GraphDocument.open(
        tmp_path / "bad.sqlite",
        mode="create",
        limits=LIMITS,
        profile=PROFILE,
        extractor=BadExtractor(),
    ) as store:
        with pytest.raises(InvalidExtractionError):
            store.update_documents((document,), collection_id="c", expected_revision=0)
        store._extractor = type(
            "Good",
            (),
            {
                "extract": lambda self, document, profile: (
                    __import__("graph_document").RuleExtractor().extract(document, profile=profile)
                )
            },
        )()
        assert (
            store.update_documents(
                (document,), collection_id="c", expected_revision=0
            ).graph_revision
            == 1
        )


def test_invalid_span_and_bool_limit() -> None:
    with pytest.raises(InvalidDocumentError):
        EvidenceLocation("span", (True, 2))
    with pytest.raises(InvalidDocumentError):
        GraphLimits(True, 1, 1, 1, 1, 1, 1)


def test_sql_failure_rolls_back_whole_batch(tmp_path: Path) -> None:
    import sqlite3

    from graph_document import StoreWriteError, UnknownCollectionError

    path = tmp_path / "graph.sqlite"
    with GraphDocument.open(path, mode="create", limits=LIMITS, profile=PROFILE):
        pass
    with sqlite3.connect(path) as connection:
        connection.execute("""
            CREATE TRIGGER reject_b BEFORE INSERT ON contributions
            WHEN NEW.document_id = 'b' BEGIN SELECT RAISE(ABORT, 'injected failure'); END
        """)
    with GraphDocument.open(path, mode="read_write", limits=LIMITS, profile=PROFILE) as store:
        with pytest.raises(StoreWriteError):
            store.update_documents(
                (Document("a", "1", "A", ""), Document("b", "1", "B", "")),
                collection_id="c",
                expected_revision=0,
            )
        with pytest.raises(UnknownCollectionError):
            store.read(collection_id="c", selection="all", limits=READ)
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_profile_selection_and_cursor_revision(tmp_path: Path) -> None:
    from graph_document import ProfileMismatchError, RuleExtractor

    class AliasExtractor:
        def extract(self, document: Document, *, profile: ExtractionProfile) -> ExtractedDocument:
            base = RuleExtractor().extract(document, profile=profile)
            second = EntityFact(
                EntityKey("concept", document.document_id),
                "Same",
                (),
                "alias",
                (EvidenceLocation("document"),),
            )
            return replace(base, entities=(*base.entities, second))

    path = tmp_path / "graph.sqlite"
    with GraphDocument.open(
        path, mode="create", limits=LIMITS, profile=PROFILE, extractor=AliasExtractor()
    ) as store:
        store.update_documents(
            (Document("a", "1", "A", ""), Document("b", "1", "B", "")),
            collection_id="c",
            expected_revision=0,
        )
        snapshot = store.read(collection_id="c", selection="all", limits=READ)
        first = snapshot.find_items(ItemQuery("Same", limit=1))
        assert first.next_cursor is not None
        second = snapshot.find_items(ItemQuery("Same", limit=1, cursor=first.next_cursor))
        assert first.items[0].node_id != second.items[0].node_id
        selected = store.read(collection_id="c", selection=("a",), limits=READ)
        with pytest.raises(InvalidCursorError):
            selected.find_items(ItemQuery("Same", limit=1, cursor=first.next_cursor))
        store.update_documents(
            (Document("c", "1", "C", ""),), collection_id="c", expected_revision=1
        )
        newer = store.read(collection_id="c", selection="all", limits=READ)
        with pytest.raises(InvalidCursorError):
            newer.find_items(ItemQuery("Same", limit=1, cursor=first.next_cursor))
    different = ExtractionProfile(profile_id="other")
    with GraphDocument.open(path, mode="read_only", limits=LIMITS, profile=different) as store:
        with pytest.raises(ProfileMismatchError):
            store.read(collection_id="c", selection="all", limits=READ)


def test_malformed_cursor_and_extractor_text_are_domain_errors(tmp_path: Path) -> None:
    import base64

    from graph_document import RuleExtractor

    document = Document("a", "1", "A", "")

    class BadTextExtractor:
        def extract(self, document: Document, *, profile: ExtractionProfile) -> ExtractedDocument:
            base = RuleExtractor().extract(document, profile=profile)
            return replace(base, warnings=("\ud800",))

    path = tmp_path / "graph.sqlite"
    with GraphDocument.open(
        path, mode="create", limits=LIMITS, profile=PROFILE, extractor=BadTextExtractor()
    ) as store:
        with pytest.raises(InvalidExtractionError):
            store.update_documents((document,), collection_id="c", expected_revision=0)
    with GraphDocument.open(path, mode="read_write", limits=LIMITS, profile=PROFILE) as store:
        store.update_documents((document,), collection_id="c", expected_revision=0)
        snapshot = store.read(collection_id="c", selection="all", limits=READ)
        for malformed in (1, base64.urlsafe_b64encode(b"1").decode("ascii"), "###"):
            with pytest.raises(InvalidCursorError):
                snapshot.find_items(ItemQuery("A", cursor=cast(Any, malformed)))


def test_selected_read_skips_unrelated_corrupt_payload(tmp_path: Path) -> None:
    import sqlite3

    path = tmp_path / "graph.sqlite"
    with GraphDocument.open(path, mode="create", limits=LIMITS, profile=PROFILE) as store:
        store.update_documents(
            (Document("a", "1", "A", ""), Document("b", "1", "B", "")),
            collection_id="c",
            expected_revision=0,
        )
    with sqlite3.connect(path) as connection:
        connection.execute("UPDATE contributions SET payload='invalid json' WHERE document_id='b'")
    with GraphDocument.open(path, mode="read_only", limits=LIMITS, profile=PROFILE) as store:
        assert [
            d.document_id
            for d in store.read(collection_id="c", selection=("a",), limits=READ).documents
        ] == ["a"]
        from graph_document import StoreCorruptError

        with pytest.raises(StoreCorruptError):
            store.read(collection_id="c", selection="all", limits=READ)


def test_schema_table_mismatch_is_rejected(tmp_path: Path) -> None:
    import sqlite3

    from graph_document import SchemaMismatchError

    path = tmp_path / "graph.sqlite"
    with GraphDocument.open(path, mode="create", limits=LIMITS, profile=PROFILE):
        pass
    with sqlite3.connect(path) as connection:
        connection.execute("DROP TABLE contributions")
    with pytest.raises(SchemaMismatchError):
        GraphDocument.open(path, mode="read_only", limits=LIMITS, profile=PROFILE)
