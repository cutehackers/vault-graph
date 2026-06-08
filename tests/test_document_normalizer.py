from pathlib import Path

from vault_graph.ingestion.document_normalizer import DocumentNormalizer
from vault_graph.ingestion.vault_frontmatter_reader import read_frontmatter
from vault_graph.ingestion.vault_loader import LoadedVaultDocument


def test_document_and_chunk_ids_are_vault_scoped(tmp_path: Path) -> None:
    text = "---\ntitle: Same\n---\n# Same Title\nBody\n"
    frontmatter = read_frontmatter(text)
    first = LoadedVaultDocument(
        vault_id="first",
        root_path=tmp_path / "first",
        path="wiki/same.md",
        text=text,
        raw_sha256="raw-first",
        content_hash="content",
        frontmatter=frontmatter,
    )
    second = LoadedVaultDocument(
        vault_id="second",
        root_path=tmp_path / "second",
        path="wiki/same.md",
        text=text,
        raw_sha256="raw-second",
        content_hash="content",
        frontmatter=frontmatter,
    )

    normalizer = DocumentNormalizer()
    first_snapshot = normalizer.normalize(first)
    second_snapshot = normalizer.normalize(second)

    assert first_snapshot.document.document_id != second_snapshot.document.document_id
    assert first_snapshot.chunks[0].chunk_id != second_snapshot.chunks[0].chunk_id
    assert first_snapshot.chunks[0].anchor == "same-title"


def test_document_normalizer_preserves_vault_id_and_path(tmp_path: Path) -> None:
    text = "# Decision\nWe chose local-first indexing.\n"
    loaded = LoadedVaultDocument(
        vault_id="default",
        root_path=tmp_path,
        path="wiki/decisions/local-first.md",
        text=text,
        raw_sha256="raw",
        content_hash="content",
        frontmatter=read_frontmatter(text),
    )

    snapshot = DocumentNormalizer().normalize(loaded)

    assert snapshot.document.vault_id == "default"
    assert snapshot.document.path == "wiki/decisions/local-first.md"
    assert snapshot.chunks[0].text == "We chose local-first indexing."


def test_repeated_headings_produce_unique_chunk_ids(tmp_path: Path) -> None:
    text = "# Same\nFirst body\n# Same\nSecond body\n"
    loaded = LoadedVaultDocument(
        vault_id="default",
        root_path=tmp_path,
        path="wiki/repeated.md",
        text=text,
        raw_sha256="raw",
        content_hash="content",
        frontmatter=read_frontmatter(text),
    )

    snapshot = DocumentNormalizer().normalize(loaded)

    assert len(snapshot.chunks) == 2
    assert snapshot.chunks[0].anchor == "same"
    assert snapshot.chunks[1].anchor == "same"
    assert snapshot.chunks[0].chunk_id != snapshot.chunks[1].chunk_id
