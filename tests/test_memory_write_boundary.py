"""A-18: vault-graph never writes Vault files itself when it adds, updates or retires a memory.

Source: spec 2026-11-02-vault-long-term-memory A-18, V1 (VaultPageReader is read-only).
The three MCP write tools run through the real composition with a stand-in VaultWriter, and the
Vault folder's file sha256 values stay the same.
"""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
from typing import Any, cast

import pytest

from vault_graph.interface.composition.adapters.vault_page_reader import VaultPageFileReader
from vault_graph.interface.composition.adapters.vault_publish_cli import VaultPublishCli
from vault_graph.interface.mcp.context_pack_resource_cache import ContextPackResourceCache
from vault_graph.interface.mcp.mcp_service_factory import McpServiceFactory
from vault_graph.interface.mcp.mcp_tools import McpToolRegistry, RememberInput, RetireMemoryInput, UpdateMemoryInput
from vault_graph.interface.mcp.result_explanation_cache import ResultExplanationCache
from vault_graph.operation.memory.memory_ports import WriteOutcome

MEMORY_PACKAGE = Path(__file__).parents[1] / "src" / "vault_graph" / "operation" / "memory"

PAGE = """---
title: Use SQLite
type: decision
status: active
created: 2026-10-01
updated: 2026-10-01
owner: agent
summary: Use SQLite
source_count: 1
tags: []
related: []
confidence: medium
---

# Use SQLite

Body.
"""


def sha256_by_file(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    root = tmp_path / "vault"
    (root / "wiki" / "decisions").mkdir(parents=True)
    (root / "wiki" / "index.md").write_text("# Index\n", encoding="utf-8")
    (root / "wiki" / "decisions" / "use-sqlite.md").write_text(PAGE, encoding="utf-8")
    (root / "wiki" / "decisions" / "use-postgres.md").write_text(PAGE, encoding="utf-8")
    return root


def test_three_write_tools_with_a_stand_in_writer_leave_vault_files_unchanged(
    tmp_path: Path, vault: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault_map = tmp_path / "vault-map.json"
    vault_map.write_text(
        json.dumps({"version": 2, "vaults": {"main": {"path": str(vault), "role": "project"}}, "projects": {}}),
        encoding="utf-8",
    )
    calls: list[dict[str, object]] = []

    def stand_in(self: VaultPublishCli, vault_root: Path, draft_path: Path, *, timeout_s: float) -> WriteOutcome:
        calls.append(json.loads(draft_path.read_text(encoding="utf-8")))
        return WriteOutcome(status="published", written_paths=(str(calls[-1]["path"]),))

    monkeypatch.setattr(VaultPublishCli, "publish", stand_in)
    registry = McpToolRegistry(
        services=cast(Any, None),
        service_factory=McpServiceFactory(graph_home_path=tmp_path / "state", vault_map_path=vault_map),
        context_pack_cache=ContextPackResourceCache(),
        result_explanation_cache=ResultExplanationCache(),
    )
    before = sha256_by_file(vault)

    bodies = [
        registry.remember(
            RememberInput(
                title="Keep drafts outside", kind="decision", body="B", evidence=("E",), basis="stated", vault="main"
            )
        ),
        registry.update_memory(
            UpdateMemoryInput(
                path="wiki/decisions/use-sqlite.md", body="New body.", evidence=("E",), basis="stated", vault="main"
            )
        ),
        registry.retire_memory(
            RetireMemoryInput(
                path="wiki/decisions/use-sqlite.md",
                reason="Replaced.",
                basis="stated",
                vault="main",
                replaced_by="wiki/decisions/use-postgres.md",
            )
        ),
    ]

    assert [body.payload["status"] for body in bodies] == ["published"] * 3
    assert [draft["operation"] for draft in calls] == ["upsert-page", "upsert-page", "patch-page"]
    assert sha256_by_file(vault) == before


def test_three_write_tools_with_basis_inferred_propose_and_leave_vault_files_unchanged(
    tmp_path: Path, vault: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault_map = tmp_path / "vault-map.json"
    vault_map.write_text(
        json.dumps({"version": 2, "vaults": {"main": {"path": str(vault), "role": "project"}}, "projects": {}}),
        encoding="utf-8",
    )
    proposals: list[tuple[dict[str, object], str]] = []
    published: list[Path] = []

    def stand_in_propose(
        self: VaultPublishCli, vault_root: Path, draft_path: Path, *, summary: str, timeout_s: float
    ) -> WriteOutcome:
        proposals.append((json.loads(draft_path.read_text(encoding="utf-8")), summary))
        return WriteOutcome(status="proposed", review_path=f"scratch/review/2026-11-02-memory-{len(proposals):08d}.md")

    def stand_in_publish(
        self: VaultPublishCli, vault_root: Path, draft_path: Path, *, timeout_s: float
    ) -> WriteOutcome:
        published.append(draft_path)
        return WriteOutcome(status="published")

    monkeypatch.setattr(VaultPublishCli, "propose", stand_in_propose)
    monkeypatch.setattr(VaultPublishCli, "publish", stand_in_publish)
    registry = McpToolRegistry(
        services=cast(Any, None),
        service_factory=McpServiceFactory(graph_home_path=tmp_path / "state", vault_map_path=vault_map),
        context_pack_cache=ContextPackResourceCache(),
        result_explanation_cache=ResultExplanationCache(),
    )
    before = sha256_by_file(vault)

    bodies = [
        registry.remember(
            RememberInput(
                title="Keep drafts outside", kind="decision", body="B", evidence=("E",), basis="inferred", vault="main"
            )
        ),
        registry.update_memory(
            UpdateMemoryInput(
                path="wiki/decisions/use-sqlite.md", body="New body.", evidence=("E",), basis="inferred", vault="main"
            )
        ),
        registry.retire_memory(
            RetireMemoryInput(
                path="wiki/decisions/use-sqlite.md",
                reason="Replaced.",
                basis="inferred",
                vault="main",
                replaced_by="wiki/decisions/use-postgres.md",
            )
        ),
    ]

    assert [body.payload["status"] for body in bodies] == ["proposed"] * 3
    assert [body.payload["review_path"] for body in bodies] == [
        f"scratch/review/2026-11-02-memory-{index:08d}.md" for index in (1, 2, 3)
    ]
    assert all(
        any(
            f"review resolve {body.payload['review_path']} --status accepted" in line
            for line in body.payload["messages"]
        )
        for body in bodies
    )
    assert [draft["operation"] for draft, _ in proposals] == ["upsert-page", "upsert-page", "patch-page"]
    assert published == []
    assert sha256_by_file(vault) == before


def _write_calls(path: Path) -> list[int]:
    lines = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else func.id if isinstance(func, ast.Name) else ""
        if name in {"write_text", "write_bytes"}:
            lines.append(node.lineno)
        elif name == "open" and any(
            isinstance(arg, ast.Constant) and isinstance(arg.value, str) and arg.value[:1] in "wax"
            for arg in [*node.args[1:], *(keyword.value for keyword in node.keywords if keyword.arg == "mode")]
        ):
            lines.append(node.lineno)
    return lines


def test_memory_package_writes_only_the_temporary_draft() -> None:
    writes = {path.name: _write_calls(path) for path in sorted(MEMORY_PACKAGE.glob("*.py"))}

    assert {name: lines for name, lines in writes.items() if lines} == {
        "memory_write_service.py": writes["memory_write_service.py"]
    }
    assert len(writes["memory_write_service.py"]) == 1
    source = (MEMORY_PACKAGE / "memory_write_service.py").read_text(encoding="utf-8")
    assert "tempfile.TemporaryDirectory(" in source


def test_page_reader_reads_text_and_sha256_without_writing(vault: Path) -> None:
    before = sha256_by_file(vault)

    page = VaultPageFileReader().read(vault, "wiki/decisions/use-sqlite.md")

    assert page is not None
    assert page.text == PAGE
    assert page.sha256 == hashlib.sha256(PAGE.encode("utf-8")).hexdigest()
    assert VaultPageFileReader().read(vault, "wiki/decisions/missing.md") is None
    assert sha256_by_file(vault) == before


def test_page_reader_does_not_read_outside_the_vault(tmp_path: Path, vault: Path) -> None:
    outside = tmp_path / "outside.md"
    outside.write_text("secret\n", encoding="utf-8")
    (vault / "wiki" / "link.md").symlink_to(outside)

    reader = VaultPageFileReader()

    assert reader.read(vault, "wiki/link.md") is None
    assert reader.read(vault, "../outside.md") is None
    assert reader.read(vault, "wiki/decisions") is None
