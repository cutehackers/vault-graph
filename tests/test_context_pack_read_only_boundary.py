from __future__ import annotations

from pathlib import Path
from typing import cast

from tests.test_context_pack_builder import StaticResolver, make_resolved, make_search_response
from tests.test_read_only_boundary import file_bytes
from vault_graph.context import ContextEvidenceRef, ContextPackRequest
from vault_graph.context.context_pack_builder import ContextRetrievalService, SearchContextPackBuilder
from vault_graph.ingestion.vault_catalog import VaultCatalog, VaultCatalogEntry


class _StaticRetrievalService:
    def search(self, **_: object) -> object:
        return make_search_response()


def test_context_pack_builder_does_not_modify_vault_files(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    for relative_path in (
        "wiki/page.md",
        "docs/spec.md",
        "raw/source.md",
        "scratch/reports/report.md",
        "wiki/nested/decision.md",
    ):
        path = vault_root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# {relative_path}\nBody\n", encoding="utf-8")
    before = file_bytes(vault_root)
    catalog = VaultCatalog.from_entries(
        entries=(VaultCatalogEntry.from_root(vault_id="main", root_path=vault_root, display_name="Main Vault"),),
        active_vault_id="main",
    )
    ref = ContextEvidenceRef("main", "doc-1", "chunk-1")
    builder = SearchContextPackBuilder(
        catalog=catalog,
        retrieval_service=cast(ContextRetrievalService, _StaticRetrievalService()),
        evidence_resolver=StaticResolver({ref: make_resolved(ref)}),
    )

    builder.build(ContextPackRequest(goal="Body", requested_scope=catalog.default_scope()))

    assert file_bytes(vault_root) == before
