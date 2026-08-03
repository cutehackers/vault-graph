from pathlib import Path

import pytest

from vault_graph.ingestion.document_authority import (
    assign_provenance_families,
    classify_document_role,
)
from vault_graph.ingestion.document_normalizer import DocumentNormalizer, NormalizedDocument
from vault_graph.ingestion.vault_frontmatter_reader import read_frontmatter
from vault_graph.ingestion.vault_loader import LoadedVaultDocument


@pytest.mark.parametrize(
    ("path", "frontmatter", "expected"),
    [
        ("raw/source.md", {}, "raw_evidence"),
        ("wiki/sources/source.md", {"type": "source"}, "source_manifest"),
        ("wiki/index.md", {"type": "index"}, "generated_view"),
        ("wiki/maps/topic-map.md", {"type": "map"}, "generated_view"),
        ("wiki/log.md", {"type": "log"}, "operation_log"),
        ("docs/usage.md", {}, "operating_contract"),
        ("scratch/reports/audit.md", {}, "audit_record"),
        ("wiki/concepts/topic.md", {"type": "concept"}, "canonical_knowledge"),
    ],
)
def test_classify_document_role(path: str, frontmatter: dict[str, object], expected: str) -> None:
    assert classify_document_role(path=path, frontmatter=frontmatter) == expected


def test_family_connects_raw_manifest_and_durable_pages(tmp_path: Path) -> None:
    items = (
        _normalized(tmp_path, path="raw/sources/a.md"),
        _normalized(
            tmp_path,
            path="wiki/sources/a.md",
            frontmatter={"type": "source", "canonical_source": "raw/sources/a.md"},
        ),
        _normalized(
            tmp_path,
            path="wiki/systems/a.md",
            frontmatter={"type": "system", "derived_from": ["wiki/sources/a"]},
        ),
        _normalized(
            tmp_path,
            path="wiki/decisions/a.md",
            frontmatter={"type": "decision", "derived_from": ["wiki/sources/a"]},
        ),
    )

    assigned = assign_provenance_families(items)

    assert len({item.document.provenance_family_id for item in assigned}) == 1
    assert {item.document.source_role for item in assigned} == {
        "raw_evidence",
        "source_manifest",
        "canonical_knowledge",
    }
    assert all(
        chunk.provenance_family_id == item.document.provenance_family_id
        and chunk.source_role == item.document.source_role
        for item in assigned
        for chunk in item.chunks
    )


def test_equal_content_does_not_merge_unrelated_families(tmp_path: Path) -> None:
    assigned = assign_provenance_families(
        (
            _normalized(tmp_path, path="wiki/concepts/first.md", body="same"),
            _normalized(tmp_path, path="wiki/concepts/second.md", body="same"),
        )
    )

    assert assigned[0].document.provenance_family_id != assigned[1].document.provenance_family_id


def test_provenance_families_never_cross_vaults(tmp_path: Path) -> None:
    assigned = assign_provenance_families(
        (
            _normalized(
                tmp_path,
                vault_id="first",
                path="wiki/sources/a.md",
                frontmatter={"canonical_source": "raw/sources/a.md"},
            ),
            _normalized(
                tmp_path,
                vault_id="second",
                path="wiki/sources/a.md",
                frontmatter={"canonical_source": "raw/sources/a.md"},
            ),
        )
    )

    assert assigned[0].document.provenance_family_id != assigned[1].document.provenance_family_id


def test_missing_relation_target_still_produces_stable_family(tmp_path: Path) -> None:
    item = _normalized(
        tmp_path,
        path="wiki/systems/a.md",
        frontmatter={"derived_from": ["wiki/sources/missing"]},
    )

    first = assign_provenance_families((item,))[0]
    second = assign_provenance_families((item,))[0]

    assert first.document.provenance_family_id == second.document.provenance_family_id


def _normalized(
    tmp_path: Path,
    *,
    path: str,
    vault_id: str = "main",
    frontmatter: dict[str, object] | None = None,
    body: str = "body",
) -> NormalizedDocument:
    metadata = frontmatter or {}
    yaml_lines = "\n".join(f"{key}: {_yaml_value(value)}" for key, value in metadata.items())
    text = f"---\n{yaml_lines}\n---\n# Title\n{body}\n" if metadata else f"# Title\n{body}\n"
    loaded = LoadedVaultDocument(
        vault_id=vault_id,
        root_path=tmp_path / vault_id,
        path=path,
        text=text,
        raw_sha256=f"raw-{vault_id}-{path}",
        content_hash=f"content-{vault_id}-{path}",
        frontmatter=read_frontmatter(text),
    )
    return DocumentNormalizer().normalize(loaded)


def _yaml_value(value: object) -> str:
    if isinstance(value, list):
        return "[" + ", ".join(str(item) for item in value) + "]"
    return str(value)
