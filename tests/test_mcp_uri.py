from __future__ import annotations

from pathlib import Path

import pytest

from vault_graph.ingestion.vault_catalog import VaultCatalog, VaultCatalogEntry
from vault_graph.mcp.mcp_errors import McpProtocolError
from vault_graph.mcp.mcp_uri import (
    decode_resource_segment,
    encode_resource_segment,
    parse_mcp_resource_uri,
)


def make_catalog(tmp_path: Path) -> VaultCatalog:
    main = tmp_path / "main"
    disabled = tmp_path / "disabled"
    main.mkdir()
    disabled.mkdir()
    return VaultCatalog.from_entries(
        entries=(
            VaultCatalogEntry.from_root(
                vault_id="main",
                root_path=main,
                display_name="Main",
                content_scopes=("wiki", "docs"),
            ),
            VaultCatalogEntry.from_root(
                vault_id="disabled",
                root_path=disabled,
                display_name="Disabled",
                enabled=False,
                content_scopes=("wiki",),
            ),
        ),
        active_vault_id="main",
    )


def assert_error_code(exc_info: pytest.ExceptionInfo[McpProtocolError], code: str) -> None:
    assert exc_info.value.payload.code == code


def test_encoded_document_path_decodes_and_normalizes(tmp_path: Path) -> None:
    parsed = parse_mcp_resource_uri("vault://main/documents/wiki%2Fspec.md", catalog=make_catalog(tmp_path))

    assert parsed.kind == "document"
    assert parsed.vault_id == "main"
    assert parsed.value == "wiki/spec.md"
    assert parsed.normalized_uri == "vault://main/documents/wiki%2Fspec.md"


def test_encoded_page_path_under_wiki_is_accepted(tmp_path: Path) -> None:
    parsed = parse_mcp_resource_uri("vault://main/pages/wiki%2Fpage.md", catalog=make_catalog(tmp_path))

    assert parsed.kind == "page"
    assert parsed.value == "wiki/page.md"


def test_context_pack_uri_has_no_vault_id(tmp_path: Path) -> None:
    parsed = parse_mcp_resource_uri("vault://context/packs/pack-1", catalog=make_catalog(tmp_path))

    assert parsed.kind == "context_pack"
    assert parsed.vault_id is None
    assert parsed.value == "pack-1"
    assert parsed.normalized_uri == "vault://context/packs/pack-1"


def test_segment_helpers_round_trip_slash_values() -> None:
    encoded = encode_resource_segment("wiki/spec.md")

    assert encoded == "wiki%2Fspec.md"
    assert decode_resource_segment(encoded, allow_slash=True) == "wiki/spec.md"


@pytest.mark.parametrize(
    "uri",
    [
        "vault://main/documents/wiki/spec.md",
        "vault://main/documents/wiki%2Fspec.md?x=1",
        "vault://main/documents/wiki%2Fspec.md#fragment",
        "file://main/documents/wiki%2Fspec.md",
        "vault://main/documents/%2Ftmp%2Fspec.md",
        "vault://main/documents/wiki%2F..%2Fspec.md",
        "vault://main/documents/wiki%2F%2e%2e%2Fspec.md",
        "vault://main/documents/wiki%2Fspec.txt",
        "vault://main/pages/docs%2Fspec.md",
        "vault://main/sources/raw%2Fsource.md",
    ],
)
def test_invalid_resource_uris_fail_closed(tmp_path: Path, uri: str) -> None:
    with pytest.raises(McpProtocolError) as exc_info:
        parse_mcp_resource_uri(uri, catalog=make_catalog(tmp_path))

    assert_error_code(exc_info, "invalid_resource_uri")


def test_document_path_must_stay_in_enabled_content_scope(tmp_path: Path) -> None:
    with pytest.raises(McpProtocolError) as exc_info:
        parse_mcp_resource_uri("vault://main/documents/raw%2Fsource.md", catalog=make_catalog(tmp_path))

    assert_error_code(exc_info, "invalid_resource_uri")


def test_unknown_vault_id_uses_specific_error_code(tmp_path: Path) -> None:
    with pytest.raises(McpProtocolError) as exc_info:
        parse_mcp_resource_uri("vault://missing/documents/wiki%2Fspec.md", catalog=make_catalog(tmp_path))

    assert_error_code(exc_info, "unknown_vault_id")


def test_disabled_vault_id_uses_specific_error_code(tmp_path: Path) -> None:
    with pytest.raises(McpProtocolError) as exc_info:
        parse_mcp_resource_uri("vault://disabled/documents/wiki%2Fspec.md", catalog=make_catalog(tmp_path))

    assert_error_code(exc_info, "vault_disabled")
