from __future__ import annotations

import json
import os
import tomllib
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
        config_path = request.config_path.expanduser()
        if request.agent == "codex" and config_path.suffix == ".toml":
            return self._register_codex_toml(request=request, config_path=config_path)

        rendered = self._renderer.render(
            McpConfigRequest(
                agent=request.agent,
                state_path=request.state_path,
                server_name=request.server_name,
            )
        )
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

    def default_config_path(self, agent: McpAgent) -> Path:
        _validate_agent(agent)
        codex_home = os.environ.get("CODEX_HOME")
        return Path(codex_home).expanduser() / "config.toml" if codex_home else Path.home() / ".codex" / "config.toml"

    def _register_codex_toml(self, *, request: McpRegistrationRequest, config_path: Path) -> McpRegistrationReport:
        if not config_path.parent.exists():
            raise McpConfigError("mcp_config_parent_missing: config parent directory does not exist")
        desired_block = _codex_toml_server_block(
            server_name=request.server_name,
            state_path=request.state_path.expanduser().resolve(),
        )
        current_text = config_path.read_text(encoding="utf-8") if config_path.exists() else ""
        _validate_toml_config(current_text)
        next_text = _upsert_toml_section(
            value=current_text,
            section_header=f"[mcp_servers.{request.server_name}]",
            replacement=desired_block,
        )
        changed = current_text != next_text
        if request.dry_run or not changed:
            return McpRegistrationReport(
                agent=request.agent,
                config_path=config_path,
                server_name=request.server_name,
                changed=changed,
                dry_run=request.dry_run,
                backup_path=None,
                rendered_config=desired_block,
            )

        backup_path = None
        if config_path.exists():
            backup_path = self._backup_path(config_path)
            backup_path.write_text(current_text, encoding="utf-8")
        config_path.write_text(next_text, encoding="utf-8")
        return McpRegistrationReport(
            agent=request.agent,
            config_path=config_path,
            server_name=request.server_name,
            changed=True,
            dry_run=False,
            backup_path=backup_path,
            rendered_config=desired_block,
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


def _codex_toml_server_block(*, server_name: str, state_path: Path) -> str:
    _validate_server_name(server_name)
    args = ["serve", "--mcp", "--state", str(state_path)]
    rendered_args = ", ".join(json.dumps(arg) for arg in args)
    return f'[mcp_servers.{server_name}]\ncommand = "vg"\nargs = [{rendered_args}]\n'


def _validate_toml_config(value: str) -> None:
    if not value.strip():
        return
    try:
        tomllib.loads(value)
    except tomllib.TOMLDecodeError as exc:
        raise McpConfigError("mcp_config_invalid_toml: existing config is not valid TOML") from exc


def _upsert_toml_section(*, value: str, section_header: str, replacement: str) -> str:
    lines = value.splitlines(keepends=True)
    start = None
    for index, line in enumerate(lines):
        if line.strip() == section_header:
            start = index
            break
    if start is None:
        prefix = value.rstrip()
        return f"{prefix}\n\n{replacement}" if prefix else replacement

    end = len(lines)
    for index in range(start + 1, len(lines)):
        stripped = lines[index].strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            end = index
            break
    updated = [*lines[:start], replacement, *lines[end:]]
    return "".join(updated)
