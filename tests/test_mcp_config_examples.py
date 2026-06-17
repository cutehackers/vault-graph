from __future__ import annotations

import json
from pathlib import Path

from vault_graph.mcp.mcp_config_examples import CODEX_STDIO_CONFIG_EXAMPLE, codex_stdio_config_json


def test_codex_stdio_config_example_uses_only_local_stdio() -> None:
    payload = CODEX_STDIO_CONFIG_EXAMPLE
    server = payload["mcpServers"]["vault-graph"]

    assert server["command"] == "uv"
    assert server["args"] == [
        "run",
        "--python",
        "3.12",
        "vg",
        "serve",
        "--mcp",
        "--state",
        "/path/to/.vault-graph",
    ]
    assert "url" not in server
    assert "headers" not in server


def test_codex_stdio_config_json_matches_documented_example() -> None:
    rendered = codex_stdio_config_json()
    parsed = json.loads(rendered)
    docs_example = json.loads(
        Path("docs/superpowers/specs/phase-5/codex-local-stdio-config.example.json").read_text(encoding="utf-8")
    )

    assert parsed == docs_example
    assert str(Path.home()) not in rendered
    assert str(Path.cwd()) not in rendered
    assert "/path/to/.vault-graph" in rendered
