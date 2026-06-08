from pathlib import Path

import pytest

from vault_graph.errors import CatalogError
from vault_graph.ingestion.vault_catalog import QueryScope, VaultCatalogEntry
from vault_graph.ingestion.vault_loader import VaultLoader


def test_loader_reads_allowed_markdown_paths(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    (vault_root / "wiki").mkdir(parents=True)
    (vault_root / "data").mkdir()
    (vault_root / "wiki" / "systems.md").write_text("---\ntitle: Systems\n---\n# Systems\nBody\n", encoding="utf-8")
    (vault_root / "data" / "derived.md").write_text("# Derived\n", encoding="utf-8")

    entry = VaultCatalogEntry.from_root(vault_id="default", root_path=vault_root)
    loader = VaultLoader()

    documents = loader.load_documents(entry=entry, scope=QueryScope(vault_ids=("default",), content_scopes=("wiki",)))

    assert tuple(document.path for document in documents) == ("wiki/systems.md",)
    assert documents[0].vault_id == "default"
    assert documents[0].frontmatter.data == {"title": "Systems"}


def test_loader_does_not_modify_vault_files(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    (vault_root / "raw").mkdir(parents=True)
    note = vault_root / "raw" / "note.md"
    note.write_text("# Note\n", encoding="utf-8")
    before = note.read_bytes()

    entry = VaultCatalogEntry.from_root(vault_id="default", root_path=vault_root)
    loader = VaultLoader()
    loader.load_documents(entry=entry, scope=QueryScope(vault_ids=("default",), content_scopes=("raw",)))

    assert note.read_bytes() == before


def test_loader_respects_entry_content_scopes_when_query_scope_is_broader(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    (vault_root / "wiki").mkdir(parents=True)
    (vault_root / "raw").mkdir()
    (vault_root / "wiki" / "page.md").write_text("# Wiki\n", encoding="utf-8")
    (vault_root / "raw" / "source.md").write_text("# Raw\n", encoding="utf-8")

    entry = VaultCatalogEntry.from_root(vault_id="default", root_path=vault_root, content_scopes=("wiki",))
    documents = VaultLoader().load_documents(
        entry=entry,
        scope=QueryScope(vault_ids=("default",), content_scopes=("wiki", "raw")),
    )

    assert tuple(document.path for document in documents) == ("wiki/page.md",)


def test_loader_allows_query_scope_narrower_than_entry_scope(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    (vault_root / "wiki" / "systems").mkdir(parents=True)
    (vault_root / "wiki" / "decisions").mkdir()
    (vault_root / "wiki" / "systems" / "page.md").write_text("# System\n", encoding="utf-8")
    (vault_root / "wiki" / "decisions" / "page.md").write_text("# Decision\n", encoding="utf-8")
    entry = VaultCatalogEntry.from_root(vault_id="default", root_path=vault_root, content_scopes=("wiki",))

    documents = VaultLoader().load_documents(
        entry=entry,
        scope=QueryScope(vault_ids=("default",), content_scopes=("wiki/systems",)),
    )

    assert tuple(document.path for document in documents) == ("wiki/systems/page.md",)


def test_loader_rejects_entry_outside_query_scope(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    entry = VaultCatalogEntry.from_root(vault_id="default", root_path=vault_root)

    with pytest.raises(CatalogError, match="entry vault_id is not included in QueryScope"):
        VaultLoader().load_documents(entry=entry, scope=QueryScope(vault_ids=("other",)))


def test_loader_skips_symlinked_markdown_that_resolves_outside_vault(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    external_root = tmp_path / "external"
    (vault_root / "wiki").mkdir(parents=True)
    external_root.mkdir()
    external_note = external_root / "outside.md"
    external_note.write_text("# Outside\n", encoding="utf-8")
    (vault_root / "wiki" / "outside.md").symlink_to(external_note)
    entry = VaultCatalogEntry.from_root(vault_id="default", root_path=vault_root)

    documents = VaultLoader().load_documents(
        entry=entry,
        scope=QueryScope(vault_ids=("default",), content_scopes=("wiki",)),
    )

    assert documents == ()
