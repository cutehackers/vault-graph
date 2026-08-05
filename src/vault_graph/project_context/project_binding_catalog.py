"""Versioned, Graph-owned persistence for explicit project bindings."""

from __future__ import annotations

import json
import os
from collections.abc import Iterable
from typing import Any, Protocol

from vault_graph.app.catalog_service import CatalogService
from vault_graph.ingestion.vault_catalog import VaultCatalog
from vault_graph.project_context.project_binding import ProjectBinding

PROJECT_BINDING_SCHEMA_VERSION = "project-bindings-v1"


class RepositoryCatalog(Protocol):
    def entries(self) -> tuple[object, ...]: ...

    def resolve(self, repository_id: str) -> object: ...


class ProjectBindingCatalog(Protocol):
    def entries(self) -> tuple[ProjectBinding, ...]: ...

    def resolve(self, repository_id: str) -> ProjectBinding: ...


class ProjectBindingCatalogService:
    """Validate and atomically persist only Graph configuration state."""

    def __init__(
        self,
        *,
        catalog_service: CatalogService,
        repository_catalog: RepositoryCatalog,
        vault_catalog: VaultCatalog,
    ) -> None:
        self._catalog_service = catalog_service
        self._repository_catalog = repository_catalog
        self._vault_catalog = vault_catalog
        self.graph_home_path = catalog_service.graph_home_path
        self.config_path = self.graph_home_path / "configs" / "project-bindings.json"

    def load(self) -> ProjectBindingCatalog:
        self._catalog_service.assert_graph_home_write_target_safe(
            target_path=self.config_path, catalog=self._vault_catalog
        )
        bindings = self._read()
        self._validate(bindings)
        return _ProjectBindingCatalog(bindings)

    def bind(self, binding: ProjectBinding) -> ProjectBindingCatalog:
        if not isinstance(binding, ProjectBinding):
            raise ValueError("binding must be a ProjectBinding")
        current = self.load().entries()
        updated = tuple(item for item in current if item.repository_id != binding.repository_id) + (binding,)
        self._validate(updated)
        self._write(updated)
        return self.load()

    def _read(self) -> tuple[ProjectBinding, ...]:
        if not self.config_path.exists():
            return ()
        try:
            payload = json.loads(self.config_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("cannot read project binding catalog") from exc
        if not isinstance(payload, dict) or payload.get("schema_version") != PROJECT_BINDING_SCHEMA_VERSION:
            raise ValueError("unsupported project binding catalog schema")
        raw_bindings = payload.get("bindings")
        if not isinstance(raw_bindings, list):
            raise ValueError("project binding catalog bindings must be a list")
        if any(not isinstance(item, dict) for item in raw_bindings):
            raise ValueError("invalid project binding catalog entry")
        try:
            return tuple(
                ProjectBinding(
                    repository_id=item["repository_id"],
                    vault_ids=tuple(item["vault_ids"]),
                    content_scopes=tuple(item.get("content_scopes", ())),
                    evidence_mappings=tuple(tuple(mapping) for mapping in item.get("evidence_mappings", ())),
                )
                for item in raw_bindings
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("invalid project binding catalog entry") from exc

    def _write(self, bindings: tuple[ProjectBinding, ...]) -> None:
        self._catalog_service.assert_graph_home_write_target_safe(
            target_path=self.config_path, catalog=self._vault_catalog
        )
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        payload: dict[str, Any] = {
            "schema_version": PROJECT_BINDING_SCHEMA_VERSION,
            "bindings": [
                {
                    "repository_id": item.repository_id,
                    "vault_ids": list(item.vault_ids),
                    "content_scopes": list(item.content_scopes),
                    "evidence_mappings": [list(mapping) for mapping in item.evidence_mappings],
                }
                for item in sorted(bindings, key=lambda item: item.repository_id)
            ],
        }
        temporary = self.config_path.with_name(f".{self.config_path.name}.tmp")
        self._catalog_service.assert_graph_home_write_target_safe(target_path=temporary, catalog=self._vault_catalog)
        try:
            with temporary.open("w", encoding="utf-8") as handle:
                json.dump(payload, handle, sort_keys=True, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.config_path)
        finally:
            if temporary.exists():
                temporary.unlink()

    def _validate(self, bindings: Iterable[ProjectBinding]) -> None:
        seen: set[str] = set()
        for binding in bindings:
            if binding.repository_id in seen:
                raise ValueError(f"duplicate repository_id: {binding.repository_id}")
            seen.add(binding.repository_id)
            try:
                self._repository_catalog.resolve(binding.repository_id)
            except Exception as exc:
                raise ValueError(f"unknown repository_id: {binding.repository_id}") from exc
            for vault_id in binding.vault_ids:
                try:
                    vault = self._vault_catalog.resolve(vault_id)
                except Exception as exc:
                    raise ValueError(f"unknown vault_id: {vault_id}") from exc
                if not vault.enabled:
                    raise ValueError(f"disabled vault_id: {vault_id}")
                unsupported = set(binding.content_scopes) - set(vault.content_scopes)
                if unsupported:
                    raise ValueError(f"content scope is not enabled for vault_id: {vault_id}")


class _ProjectBindingCatalog:
    def __init__(self, bindings: tuple[ProjectBinding, ...]) -> None:
        self._bindings = tuple(sorted(bindings, key=lambda item: item.repository_id))

    def entries(self) -> tuple[ProjectBinding, ...]:
        return self._bindings

    def resolve(self, repository_id: str) -> ProjectBinding:
        for binding in self._bindings:
            if binding.repository_id == repository_id:
                return binding
        raise ValueError(f"missing project binding for repository_id: {repository_id}")


__all__ = [
    "PROJECT_BINDING_SCHEMA_VERSION",
    "ProjectBindingCatalog",
    "ProjectBindingCatalogService",
    "RepositoryCatalog",
]
