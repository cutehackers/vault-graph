"""One copy of the Vault frontmatter line rules in M01, shared by indexing and memory writes (정리 발견4)."""

from __future__ import annotations

import ast
from pathlib import Path

from vault_graph.indexing.ingestion.vault_frontmatter_reader import read_frontmatter
from vault_graph.operation.memory.memory_drafts import parse_frontmatter
from vault_graph.operation.scope.vault_frontmatter import parse_vault_frontmatter, split_frontmatter

SRC = Path(__file__).resolve().parents[1] / "src" / "vault_graph"
PAGE = (
    "---\ntitle: Use uv\npin: true\nsource_count: 2\ntags: [a, b]\nquality:\n  links: unchecked\n"
    "related:\n  - x\n  - y\nsummary: 'quoted: value'\n---\n# Use uv\n"
)
EXPECTED = {
    "title": "Use uv",
    "pin": True,
    "source_count": 2,
    "tags": ["a", "b"],
    "quality": {"links": "unchecked"},
    "related": ["x", "y"],
    "summary": "quoted: value",
}


def test_split_frontmatter_returns_the_raw_block_and_body() -> None:
    assert split_frontmatter("---\na: 1\n---\nbody\n") == ("a: 1", "body\n")
    assert split_frontmatter("no frontmatter") is None
    assert split_frontmatter("---\na: 1\nnever closed\n") is None


def test_the_line_rules_read_every_vault_value_shape() -> None:
    block = split_frontmatter(PAGE)
    assert block is not None
    assert parse_vault_frontmatter(block[0]) == EXPECTED


def test_memory_drafts_and_the_yaml_fallback_use_the_same_rules() -> None:
    broken = PAGE.replace("title: Use uv", "title: Use uv: [broken")

    assert parse_frontmatter(PAGE) == EXPECTED
    fallback = read_frontmatter(broken)
    assert fallback.yaml_error is not None
    assert fallback.data == {**EXPECTED, "title": "Use uv: [broken"}


def test_no_other_module_defines_the_line_rules() -> None:
    owners = [
        path.relative_to(SRC).as_posix()
        for path in SRC.rglob("*.py")
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if isinstance(node, ast.FunctionDef) and node.name in {"_block_value", "_scalar"}
    ]
    assert owners == ["operation/scope/vault_frontmatter.py", "operation/scope/vault_frontmatter.py"]
