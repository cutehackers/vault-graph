from __future__ import annotations

import pytest

from vault_graph.errors import MemoryProjectionError
from vault_graph.ingestion.vault_catalog import QueryScope
from vault_graph.memory.memory_models import (
    MemoryBackendRevision,
    MemoryEvidenceRef,
    MemoryItem,
    MemoryWarning,
    ProjectMemoryProjection,
    ProjectMemoryVault,
    stable_memory_item_id,
)


def make_evidence(
    *,
    vault_id: str = "main",
    document_id: str = "doc-1",
    chunk_id: str = "chunk-1",
    path: str = "wiki/page.md",
) -> MemoryEvidenceRef:
    return MemoryEvidenceRef(
        vault_id=vault_id,
        document_id=document_id,
        chunk_id=chunk_id,
        path=path,
        section="Decision",
        anchor="decision",
        content_hash="content-hash",
        raw_sha256="raw-sha",
        metadata_index_revision="metadata-1",
        vault_revision="vault-1",
    )


def make_item(**overrides: object) -> MemoryItem:
    values: dict[str, object] = {
        "item_id": "memory:decision:0123456789abcdef01234567",
        "kind": "decision",
        "claim_status": "stated",
        "matched_signals": ("path:wiki/decisions",),
        "document_resource_kinds": ("document", "page", "decision"),
        "title": "Use MCP",
        "summary": "Decision summary",
        "vault_id": "main",
        "path": "wiki/page.md",
        "status": "accepted",
        "rank": 1,
        "evidence": (make_evidence(),),
        "warnings": (),
    }
    values.update(overrides)
    return MemoryItem(**values)  # type: ignore[arg-type]


def test_memory_item_requires_evidence_and_positive_rank() -> None:
    with pytest.raises(MemoryProjectionError, match="evidence"):
        make_item(evidence=())

    with pytest.raises(MemoryProjectionError, match="rank"):
        make_item(rank=0)


def test_memory_warning_requires_affected_vault_ids_tuple() -> None:
    warning = MemoryWarning(
        code="candidate_decision",
        message="candidate",
        severity="warning",
        affected_vault_ids=("main",),
    )
    assert warning.affected_vault_ids == ("main",)

    with pytest.raises(MemoryProjectionError, match="affected_vault_ids"):
        MemoryWarning(
            code="candidate_decision",
            message="candidate",
            severity="warning",
            affected_vault_ids=["main"],  # type: ignore[arg-type]
        )


def test_memory_projection_requires_tuple_fields() -> None:
    vault = ProjectMemoryVault(
        vault_id="main",
        display_name="Main",
        current_state=(),
        decisions=(),
        open_questions=(),
        constraints=(),
        next_priorities=(),
        stale_areas=(),
        warnings=(),
        store_revisions=(),
        freshness="fresh",
    )

    with pytest.raises(MemoryProjectionError, match="actual_scopes"):
        ProjectMemoryProjection(
            requested_scope=QueryScope(vault_ids=("main",), content_scopes=("wiki",)),
            actual_scopes=[QueryScope(vault_ids=("main",), content_scopes=("wiki",))],  # type: ignore[arg-type]
            vaults=(vault,),
            warnings=(),
            generated_at="2026-06-18T00:00:00+00:00",
        )


def test_stable_memory_item_id_includes_vault_primary_chunk_status_and_claim_status() -> None:
    base = stable_memory_item_id(
        kind="decision",
        vault_id="main",
        document_id="doc-1",
        chunk_id="chunk-1",
        title="Use MCP",
        status="accepted",
        claim_status="stated",
    )

    assert base.startswith("memory:decision:")
    assert len(base) == len("memory:decision:") + 24
    assert base != stable_memory_item_id(
        kind="decision",
        vault_id="work",
        document_id="doc-1",
        chunk_id="chunk-1",
        title="Use MCP",
        status="accepted",
        claim_status="stated",
    )
    assert base != stable_memory_item_id(
        kind="decision",
        vault_id="main",
        document_id="doc-1",
        chunk_id="chunk-2",
        title="Use MCP",
        status="accepted",
        claim_status="stated",
    )
    assert base != stable_memory_item_id(
        kind="decision",
        vault_id="main",
        document_id="doc-1",
        chunk_id="chunk-1",
        title="Use MCP",
        status="accepted",
        claim_status="heading_candidate",
    )


def test_memory_backend_revision_allows_missing_revision_but_requires_scope_key() -> None:
    revision = MemoryBackendRevision(kind="metadata", revision=None, vault_id="main", scope_key="main:wiki")

    assert revision.revision is None

    with pytest.raises(MemoryProjectionError, match="scope_key"):
        MemoryBackendRevision(kind="metadata", revision=None, vault_id="main", scope_key="")


def test_memory_item_requires_document_resource_kind() -> None:
    with pytest.raises(MemoryProjectionError, match="document_resource_kinds"):
        make_item(document_resource_kinds=())

    with pytest.raises(MemoryProjectionError, match="document"):
        make_item(document_resource_kinds=("decision",))

    with pytest.raises(MemoryProjectionError, match="document_resource_kinds"):
        make_item(document_resource_kinds=("document", "memory"))


def test_memory_item_validates_tuple_contents() -> None:
    with pytest.raises(MemoryProjectionError, match="matched_signals"):
        make_item(matched_signals=("",))

    with pytest.raises(MemoryProjectionError, match="evidence"):
        make_item(evidence=("not-evidence",))

    with pytest.raises(MemoryProjectionError, match="warnings"):
        make_item(warnings=("not-warning",))


def test_memory_item_vault_and_path_must_match_first_evidence() -> None:
    with pytest.raises(MemoryProjectionError, match="vault_id"):
        make_item(vault_id="work")

    with pytest.raises(MemoryProjectionError, match="path"):
        make_item(path="wiki/other.md")
