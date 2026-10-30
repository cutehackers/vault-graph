"""MCP page resource reads append one ``fetched`` usage event (spec 4.2.3, S11, A-10d, A-10i)."""

from __future__ import annotations

import json
import stat
from collections.abc import Iterator
from pathlib import Path

import pytest

from tests.test_mcp_resource_read_only_boundary import initialized_state
from tests.test_read_only_boundary import file_bytes
from tests.test_sqlite_metadata_store import make_chunk, make_document
from vault_graph.context.pack.recall import memory_item_id
from vault_graph.interface.mcp.mcp_errors import McpProtocolError
from vault_graph.interface.mcp.mcp_resources import McpResourceRequest
from vault_graph.interface.mcp.mcp_server import McpServerConfig, create_mcp_server
from vault_graph.storage.local.sqlite_metadata_store import SQLiteMetadataStore

PAGE_URI = "vault://default/pages/wiki%2Fpage.md"


@pytest.fixture
def graph_home(tmp_path: Path) -> Path:
    vault_root = tmp_path / "vault"
    (vault_root / "wiki").mkdir(parents=True)
    (vault_root / "wiki" / "page.md").write_text("# Page\nVault body\n", encoding="utf-8")
    home = initialized_state(tmp_path, vault_root)
    document = make_document("default", "wiki/page.md", "hash")
    chunk = make_chunk("default", document.document_id, document.path, chunk_id="chunk-1", text="Indexed body")
    store = SQLiteMetadataStore(home / "metadata" / "metadata.sqlite3", initialize=True)
    store.apply_metadata_revision(index_revision="metadata-1", documents=[document], chunks=[chunk], tombstones=[])
    return home


def events(home: Path) -> list[dict[str, object]]:
    usage = home / "usage"
    if not usage.exists():
        return []
    return [json.loads(line) for path in sorted(usage.glob("*.jsonl")) for line in path.read_text().splitlines()]


def outside_usage(home: Path) -> dict[str, bytes]:
    return {path: data for path, data in file_bytes(home).items() if not path.startswith("usage/")}


def test_successful_page_read_appends_one_fetched_event_and_changes_nothing_else(
    tmp_path: Path, graph_home: Path
) -> None:
    vault_before = file_bytes(tmp_path / "vault")
    registered = create_mcp_server(McpServerConfig(graph_home_path=graph_home))
    home_before = outside_usage(graph_home)

    body = registered.resource_registry.read(McpResourceRequest(uri=PAGE_URI))

    assert body.text == "Indexed body"
    recorded = events(graph_home)
    assert len(recorded) == 1
    assert recorded[0]["event"] == "fetched"
    assert recorded[0]["item_id"] == memory_item_id("default", "wiki/page.md")
    assert recorded[0]["session_id"] is None
    assert file_bytes(tmp_path / "vault") == vault_before
    assert outside_usage(graph_home) == home_before


def test_failed_page_read_and_other_resources_record_nothing(graph_home: Path) -> None:
    registered = create_mcp_server(McpServerConfig(graph_home_path=graph_home))

    with pytest.raises(McpProtocolError):
        registered.resource_registry.read(McpResourceRequest(uri="vault://default/pages/wiki%2Fmissing.md"))
    registered.resource_registry.read(McpResourceRequest(uri="vault://default/documents/wiki%2Fpage.md"))

    assert events(graph_home) == []


@pytest.fixture
def read_only_usage(graph_home: Path) -> Iterator[Path]:
    usage = graph_home / "usage"
    usage.mkdir()
    usage.chmod(stat.S_IRUSR | stat.S_IXUSR)
    yield usage
    usage.chmod(stat.S_IRWXU)


def test_page_read_succeeds_and_warns_once_when_usage_is_read_only(
    graph_home: Path, read_only_usage: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    registered = create_mcp_server(McpServerConfig(graph_home_path=graph_home))
    capsys.readouterr()

    body = registered.resource_registry.read(McpResourceRequest(uri=PAGE_URI))

    captured = capsys.readouterr()
    assert body.text == "Indexed body"
    assert captured.out == ""
    assert len(captured.err.splitlines()) == 1
    assert "warning" in captured.err
    assert list(read_only_usage.iterdir()) == []
