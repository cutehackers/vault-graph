"""MCP resources follow the active index generation (re-audit finding 발견7).

Background indexing publishes new projection generations while the server runs, and only the
active and previous generations are kept. Resources must reopen their read services on the new
generation instead of keeping the metadata store opened at server start.
"""

from __future__ import annotations

import threading
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest
from pytest import MonkeyPatch
from typer.testing import CliRunner

from tests.fakes.deterministic_text_embeddings import DeterministicTextEmbeddings
from tests.test_mcp_tools import RecordingFactory, fake_services
from tests.test_vector_indexer import SPEC
from vault_graph.interface.cli.main import app
from vault_graph.interface.mcp.mcp_resources import McpResourceRequest
from vault_graph.interface.mcp.mcp_server import McpServerConfig, create_mcp_server
from vault_graph.interface.mcp.mcp_service_factory import CurrentMcpServices, McpServices

runner = CliRunner()


class _ConfiguredDeterministicTextEmbeddings(DeterministicTextEmbeddings):
    class Config:
        embedding_batch_size = 256
        embedding_parallelism = None
        embedding_lazy_load = True

    config = Config()


def _deterministic_text_embeddings(_: object) -> _ConfiguredDeterministicTextEmbeddings:
    return _ConfiguredDeterministicTextEmbeddings(SPEC)


def _write_page(root: Path, path: str, body: str) -> None:
    file_path = root / path
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(body, encoding="utf-8")


def _index(graph_home: Path) -> None:
    result = runner.invoke(app, ["index", "--graph-home", str(graph_home)])
    assert result.exit_code == 0, result.output


def _generations(graph_home: Path) -> set[str]:
    return {path.name for path in (graph_home / "projections" / "generations").iterdir()}


@pytest.fixture
def indexed_home(tmp_path: Path, monkeypatch: MonkeyPatch) -> tuple[Path, Path]:
    monkeypatch.setattr("vault_graph.interface.cli.main._text_embeddings", _deterministic_text_embeddings)
    vault_root = tmp_path / "vault"
    _write_page(vault_root, "wiki/page.md", "# Page\nStartup body about markdown.\n")
    graph_home = tmp_path / "state"
    result = runner.invoke(app, ["init", "--vault", str(vault_root), "--graph-home", str(graph_home)])
    assert result.exit_code == 0, result.output
    _index(graph_home)
    return vault_root, graph_home


def test_page_resource_reads_after_the_startup_generation_is_pruned(indexed_home: tuple[Path, Path]) -> None:
    vault_root, graph_home = indexed_home
    registered = create_mcp_server(McpServerConfig(graph_home_path=graph_home))
    startup_generations = _generations(graph_home)
    first = registered.resource_registry.read(McpResourceRequest(uri="vault://default/pages/wiki%2Fpage.md"))
    assert "Startup body" in first.text

    _write_page(vault_root, "wiki/decisions/new-page.md", "# New page\nNarwhalite tags are signed.\n")
    _index(graph_home)
    _write_page(vault_root, "wiki/other.md", "# Other\nAnother body.\n")
    _index(graph_home)
    assert not (startup_generations & _generations(graph_home)), "the startup generation must be pruned"

    old_page = registered.resource_registry.read(McpResourceRequest(uri="vault://default/pages/wiki%2Fpage.md"))
    new_page = registered.resource_registry.read(
        McpResourceRequest(uri="vault://default/pages/wiki%2Fdecisions%2Fnew-page.md")
    )
    document = registered.resource_registry.read(McpResourceRequest(uri="vault://default/documents/wiki%2Fother.md"))

    assert "Startup body" in old_page.text
    assert "Narwhalite tags are signed" in new_page.text
    assert document.metadata["path"] == "wiki/other.md"


def test_resources_and_tools_share_one_services_holder(indexed_home: tuple[Path, Path]) -> None:
    _, graph_home = indexed_home
    registered = create_mcp_server(McpServerConfig(graph_home_path=graph_home))

    assert registered.resource_registry.services_holder is registered.tool_registry.services_holder


# --- CurrentMcpServices: the per-call generation check shared by tools and resources ---


class _GenerationFactory(RecordingFactory):
    def __init__(self, fresh: McpServices) -> None:
        super().__init__()
        self.generation: str | None = "g1"
        self.fresh = fresh
        self.opened = 0

    def active_generation_id(self) -> str | None:
        return self.generation

    def open_read_only(self) -> McpServices:
        self.opened += 1
        return replace(self.fresh, generation_id=self.generation)


def _holder(tmp_path: Path) -> tuple[CurrentMcpServices, _GenerationFactory, McpServices]:
    (tmp_path / "fresh").mkdir()
    factory = _GenerationFactory(fake_services(tmp_path / "fresh"))
    startup = replace(fake_services(tmp_path), generation_id="g1")
    return CurrentMcpServices(services=startup, service_factory=cast(Any, factory)), factory, startup


def test_holder_keeps_services_while_the_generation_is_unchanged(tmp_path: Path) -> None:
    holder, factory, startup = _holder(tmp_path)

    assert holder.get() is startup
    assert holder.get() is startup
    assert factory.opened == 0


def test_holder_reopens_once_when_the_generation_changes(tmp_path: Path) -> None:
    holder, factory, startup = _holder(tmp_path)
    factory.generation = "g2"

    reopened = holder.get()

    assert reopened is not startup and reopened.generation_id == "g2"
    assert holder.get() is reopened
    assert factory.opened == 1


def test_holder_keeps_services_when_the_reopen_fails(tmp_path: Path) -> None:
    holder, factory, startup = _holder(tmp_path)

    def broken_open() -> McpServices:
        raise RuntimeError("generation folder vanished")

    factory.open_read_only = broken_open  # type: ignore[method-assign]
    factory.generation = "g2"

    assert holder.get() is startup


def test_holder_reopens_once_under_concurrent_calls(tmp_path: Path) -> None:
    holder, factory, _ = _holder(tmp_path)
    factory.generation = "g2"
    release = threading.Event()
    real_open = factory.open_read_only

    def slow_open() -> McpServices:
        release.wait(0.2)
        return real_open()

    factory.open_read_only = slow_open  # type: ignore[method-assign]
    threads = [threading.Thread(target=holder.get) for _ in range(4)]
    for thread in threads:
        thread.start()
    release.set()
    for thread in threads:
        thread.join(5)

    assert factory.opened == 1


def test_graph_reader_is_reopened_when_the_generation_changes(tmp_path: Path) -> None:
    from vault_graph.interface.mcp.mcp_resources import LazyGraphResourceReaderFactory

    holder, factory, _ = _holder(tmp_path)
    opened: list[object] = []

    def open_graph_resource_service() -> object:
        opened.append(object())
        return opened[-1]

    factory.open_graph_resource_service = open_graph_resource_service  # type: ignore[attr-defined]
    graph_readers = LazyGraphResourceReaderFactory(service_factory=cast(Any, factory), services_holder=holder)

    first = graph_readers.get()
    assert graph_readers.get() is first
    factory.generation = "g2"
    second = graph_readers.get()

    assert second is not first
    assert len(opened) == 2
