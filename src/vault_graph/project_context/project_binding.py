"""Explicit repository-to-Vault authority bindings."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath


@dataclass(frozen=True)
class ProjectBinding:
    """Graph-owned configuration selecting Vault authorities for a repository."""

    repository_id: str
    vault_ids: tuple[str, ...]
    content_scopes: tuple[str, ...] = ()
    evidence_mappings: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        _require_non_empty(self.repository_id, "repository_id")
        if not isinstance(self.vault_ids, tuple) or not self.vault_ids:
            raise ValueError("vault_ids must be a non-empty immutable tuple")
        if len(set(self.vault_ids)) != len(self.vault_ids):
            raise ValueError("vault_ids must not contain duplicates")
        for vault_id in self.vault_ids:
            _require_non_empty(vault_id, "vault_ids")
        if not isinstance(self.content_scopes, tuple):
            raise ValueError("content_scopes must be an immutable tuple")
        if len(set(self.content_scopes)) != len(self.content_scopes):
            raise ValueError("content_scopes must not contain duplicates")
        for content_scope in self.content_scopes:
            _validate_content_scope(content_scope)
        if not isinstance(self.evidence_mappings, tuple):
            raise ValueError("evidence_mappings must be an immutable tuple")
        for code_id, vault_id in self.evidence_mappings:
            _require_non_empty(code_id, "evidence_mappings.code_id")
            _require_non_empty(vault_id, "evidence_mappings.vault_evidence_id")


def _require_non_empty(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} is required")


def _validate_content_scope(value: str) -> None:
    _require_non_empty(value, "content_scopes")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ValueError(f"unsupported content scope: {value}")


__all__ = ["ProjectBinding"]
