from __future__ import annotations

import dataclasses
import math
from collections.abc import Mapping
from pathlib import Path

from vault_graph.errors import VaultGraphError
from vault_graph.interface.composition.query_scope_resolution import project_scope_warning_json
from vault_graph.interface.composition.vault_labels import VaultLabel, label_fields
from vault_graph.operation.scope.vault_catalog import QueryScope
from vault_graph.retrieval.search.retrieval_result import RetrievalResult
from vault_graph.retrieval.search.search_response import SearchResponse


def domain_to_json_dict(value: object) -> dict[str, object]:
    converted = domain_to_json_value(value)
    if not isinstance(converted, dict):
        raise VaultGraphError("http serialization produced a non-object")
    return converted


def search_response_json(
    response: SearchResponse, *, labels: Mapping[str, VaultLabel], warnings: tuple[str, ...] = ()
) -> dict[str, object]:
    """Search JSON with ``vault_name`` and ``vault_role`` on each result and project scope warnings first."""
    payload = domain_to_json_dict(response)
    payload["results"] = [
        {**item, **label_fields(labels, result.vault_id)}
        for item, result in zip(_dict_list(payload["results"]), response.results, strict=True)
    ]
    if warnings:
        payload["warnings"] = [
            *(project_scope_warning_json(message) for message in warnings),
            *_dict_list(payload["warnings"]),
        ]
    return payload


def _dict_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise VaultGraphError("http serialization expected a list of objects")
    return value


def domain_to_json_value(value: object) -> object:
    if isinstance(value, QueryScope):
        return {
            "vault_ids": list(value.vault_ids),
            "content_scopes": list(value.content_scopes),
            "include_cross_vault": value.include_cross_vault,
        }
    if dataclasses.is_dataclass(value):
        return {
            field.name: domain_to_json_value(getattr(value, field.name))
            for field in dataclasses.fields(value)
            if not _omitted_field(value, field.name)
        }
    if isinstance(value, tuple | list):
        return [domain_to_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): domain_to_json_value(item) for key, item in value.items()}
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise VaultGraphError("http serialization does not support non-finite floats")
        return value
    if isinstance(value, str | int | bool) or value is None:
        return value
    if isinstance(value, set | bytes | bytearray):
        raise VaultGraphError(f"http serialization does not support {type(value).__name__}")
    return _public_attrs(value)


def _omitted_field(value: object, name: str) -> bool:
    # Spec 2026-11-05 A-32: `lifecycle` exists only for `include_retired` searches, so existing bytes stay.
    return isinstance(value, RetrievalResult) and name == "lifecycle" and value.lifecycle is None


def _public_attrs(value: object) -> dict[str, object]:
    attrs: dict[str, object] = {}
    for name in dir(value):
        if name.startswith("_"):
            continue
        try:
            item = getattr(value, name)
        except Exception:
            continue
        if callable(item):
            continue
        attrs[name] = domain_to_json_value(item)
    if not attrs:
        raise VaultGraphError(f"http serialization does not support {type(value).__name__}")
    return attrs
