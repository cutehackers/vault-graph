from __future__ import annotations

import dataclasses
import math
from pathlib import Path

from vault_graph.errors import VaultGraphError
from vault_graph.ingestion.vault_catalog import QueryScope


def domain_to_json_dict(value: object) -> dict[str, object]:
    converted = domain_to_json_value(value)
    if not isinstance(converted, dict):
        raise VaultGraphError("http serialization produced a non-object")
    return converted


def domain_to_json_value(value: object) -> object:
    if isinstance(value, QueryScope):
        return {
            "vault_ids": list(value.vault_ids),
            "content_scopes": list(value.content_scopes),
            "include_cross_vault": value.include_cross_vault,
        }
    if dataclasses.is_dataclass(value):
        return {field.name: domain_to_json_value(getattr(value, field.name)) for field in dataclasses.fields(value)}
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
