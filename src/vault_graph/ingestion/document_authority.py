from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from dataclasses import replace
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from vault_graph.ingestion.document_normalizer import NormalizedDocument

DocumentRole = Literal[
    "raw_evidence",
    "canonical_knowledge",
    "source_manifest",
    "operating_contract",
    "generated_view",
    "operation_log",
    "audit_record",
]

ALL_DOCUMENT_ROLES: tuple[DocumentRole, ...] = (
    "raw_evidence",
    "canonical_knowledge",
    "source_manifest",
    "operating_contract",
    "generated_view",
    "operation_log",
    "audit_record",
)

_PROVENANCE_FIELDS = ("canonical_source", "derived_from", "supersedes", "redirects")
_WIKI_RELATIVE_PREFIXES = (
    "concepts/",
    "decisions/",
    "entities/",
    "maps/",
    "sources/",
    "systems/",
    "timelines/",
    "workflows/",
)


def classify_document_role(*, path: str, frontmatter: Mapping[str, object]) -> DocumentRole:
    normalized_type = str(frontmatter.get("type") or frontmatter.get("kind") or "").strip().casefold()
    if path.startswith("raw/"):
        return "raw_evidence"
    if path.startswith("scratch/reports/"):
        return "audit_record"
    if path.startswith("docs/"):
        return "operating_contract"
    if path == "wiki/log.md" or normalized_type == "log":
        return "operation_log"
    if path == "wiki/index.md" or path.startswith("wiki/maps/"):
        return "generated_view"
    if path.startswith("wiki/sources/") or normalized_type == "source":
        return "source_manifest"
    return "canonical_knowledge"


def assign_provenance_families(items: tuple[NormalizedDocument, ...]) -> tuple[NormalizedDocument, ...]:
    parent: dict[tuple[str, str], tuple[str, str]] = {}

    def add(key: tuple[str, str]) -> None:
        parent.setdefault(key, key)

    def find(key: tuple[str, str]) -> tuple[str, str]:
        root = parent[key]
        if root != key:
            parent[key] = find(root)
        return parent[key]

    def union(first: tuple[str, str], second: tuple[str, str]) -> None:
        first_root = find(first)
        second_root = find(second)
        if first_root == second_root:
            return
        earlier, later = sorted((first_root, second_root))
        parent[later] = earlier

    for item in items:
        key = (item.document.vault_id, item.document.path)
        add(key)
        for target_path in _provenance_paths(item.document.frontmatter):
            target = (item.document.vault_id, target_path)
            add(target)
            union(key, target)

    family_seeds: dict[tuple[str, str], str] = {}
    for key in parent:
        root = find(key)
        current = family_seeds.get(root)
        if current is None or key[1] < current:
            family_seeds[root] = key[1]

    assigned: list[NormalizedDocument] = []
    for item in items:
        document = item.document
        root = find((document.vault_id, document.path))
        family_id = _family_id(vault_id=document.vault_id, seed=family_seeds[root])
        updated_document = replace(document, provenance_family_id=family_id)
        updated_chunks = tuple(
            replace(chunk, source_role=document.source_role, provenance_family_id=family_id) for chunk in item.chunks
        )
        assigned.append(replace(item, document=updated_document, chunks=updated_chunks))
    return tuple(assigned)


def _provenance_paths(frontmatter: Mapping[str, object]) -> tuple[str, ...]:
    paths: list[str] = []
    for field_name in _PROVENANCE_FIELDS:
        for value in _frontmatter_values(frontmatter.get(field_name)):
            normalized = _normalize_relation_path(value)
            if normalized is not None:
                paths.append(normalized)
    return tuple(dict.fromkeys(paths))


def _frontmatter_values(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,)
    if isinstance(value, list):
        return tuple(str(item) for item in value if isinstance(item, str))
    return ()


def _normalize_relation_path(value: str) -> str | None:
    normalized = value.strip()
    if normalized.startswith("[[") and normalized.endswith("]]"):
        normalized = normalized[2:-2].split("|", 1)[0].strip()
    normalized = normalized.split("#", 1)[0].strip().replace("\\", "/")
    if not normalized or re.match(r"^[a-z][a-z0-9+.-]*://", normalized, flags=re.IGNORECASE):
        return None
    path = PurePosixPath(normalized)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        return None
    normalized = path.as_posix()
    if normalized.startswith(_WIKI_RELATIVE_PREFIXES):
        normalized = f"wiki/{normalized}"
    if PurePosixPath(normalized).suffix == "" and normalized.startswith(("raw/", "wiki/", "docs/", "scratch/")):
        normalized = f"{normalized}.md"
    return normalized


def _family_id(*, vault_id: str, seed: str) -> str:
    digest = hashlib.sha256(":".join(("provenance-family", vault_id, seed)).encode()).hexdigest()
    return digest
