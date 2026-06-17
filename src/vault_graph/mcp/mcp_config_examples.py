from __future__ import annotations

import json
from typing import TypedDict


class CodexMcpServerConfig(TypedDict):
    command: str
    args: list[str]


class CodexMcpConfig(TypedDict):
    mcpServers: dict[str, CodexMcpServerConfig]


CODEX_STDIO_CONFIG_EXAMPLE: CodexMcpConfig = {
    "mcpServers": {
        "vault-graph": {
            "command": "uv",
            "args": [
                "run",
                "--python",
                "3.12",
                "vg",
                "serve",
                "--mcp",
                "--state",
                "/path/to/.vault-graph",
            ],
        }
    }
}


def codex_stdio_config_json() -> str:
    return json.dumps(CODEX_STDIO_CONFIG_EXAMPLE, sort_keys=True, indent=2) + "\n"
