from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tests.test_context_pack_contract import make_pack
from vault_graph.context import (
    CONTEXT_PACK_SCHEMA_VERSION,
    ContextPack,
    render_context_pack_json,
    with_computed_pack_id,
)


def test_spec_and_features_context_pack_examples_match_dto_top_level_fields() -> None:
    dto_fields = set(ContextPack.__dataclass_fields__)
    spec_payload = _first_json_object_after_heading(Path("docs/SPEC.md"), "Minimum JSON shape")
    features_payload = _first_json_object_after_heading(Path("docs/FEATURES.md"), "Minimum JSON shape")

    assert set(spec_payload) == dto_fields
    assert set(features_payload) == dto_fields
    assert spec_payload["context_pack_schema_version"] == CONTEXT_PACK_SCHEMA_VERSION
    assert features_payload["context_pack_schema_version"] == CONTEXT_PACK_SCHEMA_VERSION


def test_documented_context_pack_nested_shapes_match_dto_serialization() -> None:
    rendered_payload = json.loads(render_context_pack_json(with_computed_pack_id(make_pack())))
    spec_payload = _first_json_object_after_heading(Path("docs/SPEC.md"), "Minimum JSON shape")

    assert set(spec_payload["scope"]) == set(rendered_payload["scope"])
    assert set(spec_payload["scope"]["requested"]) == set(rendered_payload["scope"]["requested"])
    assert set(spec_payload["scope"]["actual_scopes"][0]) == set(rendered_payload["scope"]["actual_scopes"][0])
    assert set(spec_payload["backend"]) == set(rendered_payload["backend"])
    assert set(spec_payload["backend"]["metadata_store"]) == set(rendered_payload["backend"]["metadata_store"])
    assert set(spec_payload["budget"]) == set(rendered_payload["budget"])
    assert set(spec_payload["store_revisions"][0]) == set(rendered_payload["store_revisions"][0])


def _first_json_object_after_heading(path: Path, heading: str) -> dict[str, Any]:
    lines = path.read_text(encoding="utf-8").splitlines()
    start_index = next(index for index, line in enumerate(lines) if line.strip() == f"{heading}:")
    fence_start = next(
        index
        for index, line in enumerate(lines[start_index + 1 :], start=start_index + 1)
        if line.strip() == "```json"
    )
    fence_end = next(
        index for index, line in enumerate(lines[fence_start + 1 :], start=fence_start + 1) if line.strip() == "```"
    )
    payload = json.loads("\n".join(lines[fence_start + 1 : fence_end]))
    assert isinstance(payload, dict)
    return payload
