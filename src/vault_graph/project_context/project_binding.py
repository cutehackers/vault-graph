"""Explicit repository-to-Vault authority bindings."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath

MAX_PROJECT_BINDING_ID_LENGTH = 256
MAX_PROJECT_BINDING_VAULT_IDS = 128
MAX_PROJECT_BINDING_CONTENT_SCOPES = 128
MAX_PROJECT_BINDING_EVIDENCE_MAPPINGS = 5000


@dataclass(frozen=True)
class ProjectBinding:
    """Graph-owned configuration selecting Vault authorities for a repository."""

    repository_id: str
    vault_ids: tuple[str, ...]
    content_scopes: tuple[str, ...] = ()
    evidence_mappings: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        _require_identifier(self.repository_id, "repository_id")
        if not isinstance(self.vault_ids, tuple) or not self.vault_ids:
            raise ValueError("vault_ids must be a non-empty immutable tuple")
        if len(self.vault_ids) > MAX_PROJECT_BINDING_VAULT_IDS:
            raise ValueError(f"vault_ids must contain at most {MAX_PROJECT_BINDING_VAULT_IDS} items")
        if any(not isinstance(vault_id, str) for vault_id in self.vault_ids):
            raise ValueError("vault_ids must contain strings")
        if len(set(self.vault_ids)) != len(self.vault_ids):
            raise ValueError("vault_ids must not contain duplicates")
        for vault_id in self.vault_ids:
            _require_identifier(vault_id, "vault_ids")
        if not isinstance(self.content_scopes, tuple):
            raise ValueError("content_scopes must be an immutable tuple")
        if len(self.content_scopes) > MAX_PROJECT_BINDING_CONTENT_SCOPES:
            raise ValueError(f"content_scopes must contain at most {MAX_PROJECT_BINDING_CONTENT_SCOPES} items")
        if any(not isinstance(content_scope, str) for content_scope in self.content_scopes):
            raise ValueError("content_scopes must contain strings")
        if len(set(self.content_scopes)) != len(self.content_scopes):
            raise ValueError("content_scopes must not contain duplicates")
        for content_scope in self.content_scopes:
            _validate_content_scope(content_scope)
        if not isinstance(self.evidence_mappings, tuple):
            raise ValueError("evidence_mappings must be an immutable tuple")
        if len(self.evidence_mappings) > MAX_PROJECT_BINDING_EVIDENCE_MAPPINGS:
            raise ValueError(f"evidence_mappings must contain at most {MAX_PROJECT_BINDING_EVIDENCE_MAPPINGS} items")
        code_ids: set[str] = set()
        for mapping in self.evidence_mappings:
            if not isinstance(mapping, tuple):
                raise ValueError("evidence_mappings items must be immutable tuples")
            if len(mapping) != 2:
                raise ValueError("evidence_mappings items must contain exactly two values")
            code_id, vault_evidence_id = mapping
            if not isinstance(code_id, str) or not isinstance(vault_evidence_id, str):
                raise ValueError("evidence_mappings values must be strings")
            _validate_code_evidence_id(code_id)
            _validate_vault_evidence_id(vault_evidence_id)
            if code_id in code_ids:
                raise ValueError(f"duplicate code evidence mapping: {code_id}")
            code_ids.add(code_id)


def _require_identifier(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} is required")
    if len(value) > MAX_PROJECT_BINDING_ID_LENGTH:
        raise ValueError(f"{field_name} exceeds {MAX_PROJECT_BINDING_ID_LENGTH} characters")


def _validate_code_evidence_id(value: str) -> None:
    _require_identifier(value, "code evidence id")
    if not value.startswith("code:") or len(value) == len("code:"):
        raise ValueError("code evidence id must use code:<symbol_id>")


def _validate_vault_evidence_id(value: str) -> None:
    _require_identifier(value, "Vault evidence id")
    parts = value.split(":")
    if len(parts) != 4 or parts[0] != "vault" or any(not part for part in parts[1:]):
        raise ValueError("Vault evidence id must use vault:<vault_id>:<document_id>:<chunk_id>")


def _validate_content_scope(value: str) -> None:
    _require_identifier(value, "content_scopes")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ValueError(f"unsupported content scope: {value}")


__all__ = [
    "MAX_PROJECT_BINDING_CONTENT_SCOPES",
    "MAX_PROJECT_BINDING_EVIDENCE_MAPPINGS",
    "MAX_PROJECT_BINDING_ID_LENGTH",
    "MAX_PROJECT_BINDING_VAULT_IDS",
    "ProjectBinding",
]
