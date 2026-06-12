from __future__ import annotations

import dataclasses
import hashlib
import json
import math
from dataclasses import replace
from pathlib import Path
from typing import Any

from vault_graph.context.context_pack import (
    ContextEvidence,
    ContextEvidenceRef,
    ContextPack,
    ContextPackActualScope,
    ContextPackBackend,
    ContextPackBackendUse,
    ContextPackBudget,
    ContextPackItem,
    ContextPackRequestedScope,
    ContextPackScope,
    ContextPackSignal,
    ContextPackStoreRevision,
    ContextPackVault,
    ContextPackVaultRevision,
    ContextPackWarning,
)
from vault_graph.errors import ContextPackError

_DTO_TYPES = {
    ContextPack,
    ContextPackVault,
    ContextPackVaultRevision,
    ContextPackRequestedScope,
    ContextPackActualScope,
    ContextPackScope,
    ContextPackStoreRevision,
    ContextPackBackendUse,
    ContextPackBackend,
    ContextEvidenceRef,
    ContextPackWarning,
    ContextEvidence,
    ContextPackSignal,
    ContextPackItem,
    ContextPackBudget,
}


def context_pack_to_dict(pack: ContextPack) -> dict[str, Any]:
    converted = _to_json_value(pack)
    if not isinstance(converted, dict):
        raise ContextPackError("context pack serialization produced a non-object")
    return converted


def render_context_pack_json(pack: ContextPack) -> str:
    try:
        return json.dumps(
            context_pack_to_dict(pack),
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        ) + "\n"
    except ValueError as exc:
        raise ContextPackError(f"context pack JSON serialization failed: {exc}") from exc


def context_pack_identity_dict(pack: ContextPack) -> dict[str, Any]:
    payload = context_pack_to_dict(pack)
    payload.pop("pack_id", None)
    payload.pop("generated_at", None)
    return payload


def compute_pack_id(pack: ContextPack) -> str:
    identity_json = json.dumps(
        context_pack_identity_dict(pack),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(identity_json.encode("utf-8")).hexdigest()


def with_computed_pack_id(pack: ContextPack) -> ContextPack:
    return replace(pack, pack_id=compute_pack_id(pack))


def _to_json_value(value: object) -> object:
    if dataclasses.is_dataclass(value):
        value_type = type(value)
        if value_type not in _DTO_TYPES:
            raise ContextPackError(f"unsupported dataclass in context pack serialization: {value_type.__name__}")
        return {field.name: _to_json_value(getattr(value, field.name)) for field in dataclasses.fields(value)}
    if isinstance(value, tuple):
        return [_to_json_value(item) for item in value]
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ContextPackError("non-finite float values are not supported in context pack JSON")
        return value
    if isinstance(value, str | int | bool) or value is None:
        return value
    if isinstance(value, Path | bytes | bytearray | list | dict | set):
        raise ContextPackError(f"unsupported value in context pack serialization: {type(value).__name__}")
    raise ContextPackError(f"unsupported value in context pack serialization: {type(value).__name__}")
