from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from vault_graph.errors import McpConfigError

McpAgent = Literal["codex"]


@dataclass(frozen=True)
class McpConfigRequest:
    agent: McpAgent
    state_path: Path
    server_name: str = "vault-graph"


@dataclass(frozen=True)
class McpRegistrationRequest:
    agent: McpAgent
    state_path: Path
    config_path: Path
    dry_run: bool = False
    server_name: str = "vault-graph"


@dataclass(frozen=True)
class McpRegistrationReport:
    agent: McpAgent
    config_path: Path
    server_name: str
    changed: bool
    dry_run: bool
    backup_path: Path | None = None
    rendered_config: str | None = None


class McpConfigRenderer:
    def render(self, request: McpConfigRequest) -> str:
        _validate_agent(request.agent)
        _validate_server_name(request.server_name)
        payload = {
            "mcpServers": {
                request.server_name: {
                    "command": "vg",
                    "args": [
                        "serve",
                        "--mcp",
                        "--state",
                        str(request.state_path.expanduser().resolve()),
                    ],
                }
            }
        }
        return json.dumps(payload, sort_keys=True, indent=2) + "\n"


class McpConfigRegistrar:
    def __init__(
        self,
        *,
        renderer: McpConfigRenderer | None = None,
        backup_suffix_factory: Callable[[], str] | None = None,
    ) -> None:
        self._renderer = renderer or McpConfigRenderer()
        self._backup_suffix_factory = backup_suffix_factory or (lambda: "bak")

    def register(self, request: McpRegistrationRequest) -> McpRegistrationReport:
        rendered = self._renderer.render(
            McpConfigRequest(
                agent=request.agent,
                state_path=request.state_path,
                server_name=request.server_name,
            )
        )
        config_path = request.config_path.expanduser()
        if not config_path.parent.exists():
            raise McpConfigError("mcp_config_parent_missing: config parent directory does not exist")
        rendered_payload = _loads_object(rendered)
        current_payload = self._read_existing_payload(config_path)
        existing_servers = _mcp_servers(current_payload)
        current_entry = existing_servers.get(request.server_name)
        desired_entry = _mcp_servers(rendered_payload)[request.server_name]
        changed = current_entry != desired_entry
        if request.dry_run or not changed:
            return McpRegistrationReport(
                agent=request.agent,
                config_path=config_path,
                server_name=request.server_name,
                changed=changed,
                dry_run=request.dry_run,
                backup_path=None,
                rendered_config=rendered,
            )

        backup_path = None
        if config_path.exists():
            backup_path = self._backup_path(config_path)
            backup_path.write_text(config_path.read_text(encoding="utf-8"), encoding="utf-8")
        next_payload = dict(current_payload)
        next_servers = dict(_mcp_servers(next_payload))
        next_servers[request.server_name] = desired_entry
        next_payload["mcpServers"] = next_servers
        config_path.write_text(json.dumps(next_payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        return McpRegistrationReport(
            agent=request.agent,
            config_path=config_path,
            server_name=request.server_name,
            changed=True,
            dry_run=False,
            backup_path=backup_path,
            rendered_config=rendered,
        )

    def _read_existing_payload(self, config_path: Path) -> dict[str, object]:
        if not config_path.exists():
            return {}
        try:
            return _loads_object(config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise McpConfigError("mcp_config_invalid_json: existing config is not valid JSON") from exc

    def _backup_path(self, config_path: Path) -> Path:
        return config_path.with_name(f"{config_path.name}.{self._backup_suffix_factory()}")


def _validate_agent(agent: object) -> None:
    if agent != "codex":
        raise McpConfigError("unsupported_mcp_agent: only codex is supported")


def _validate_server_name(server_name: str) -> None:
    if not isinstance(server_name, str) or not server_name.strip():
        raise McpConfigError("invalid_mcp_server_name: server_name is required")


def _loads_object(value: str) -> dict[str, object]:
    payload = json.loads(value)
    if not isinstance(payload, dict):
        raise McpConfigError("mcp_config_invalid_json: config must be a JSON object")
    return payload


def _mcp_servers(payload: dict[str, object]) -> dict[str, object]:
    raw_servers = payload.get("mcpServers")
    if raw_servers is None:
        return {}
    if not isinstance(raw_servers, dict):
        raise McpConfigError("mcp_config_invalid_json: mcpServers must be an object")
    return raw_servers
