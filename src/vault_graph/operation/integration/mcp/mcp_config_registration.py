from __future__ import annotations

import json
import os
import shutil
import tempfile
import tomllib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from vault_graph.errors import McpConfigError
from vault_graph.operation.integration.hook_status import running_vg_path

McpAgent = Literal["codex", "claude"]
SUPPORTED_MCP_AGENTS: tuple[str, ...] = ("codex", "claude")


@dataclass(frozen=True)
class McpConfigRequest:
    agent: McpAgent
    graph_home_path: Path
    server_name: str = "vault-graph"


@dataclass(frozen=True)
class McpRegistrationRequest:
    agent: McpAgent
    graph_home_path: Path
    config_path: Path
    dry_run: bool = False
    server_name: str = "vault-graph"


@dataclass(frozen=True)
class McpUnregistrationRequest:
    agent: McpAgent
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
    def __init__(self, *, vg_command: Callable[[], str | None] | None = None) -> None:
        self._vg_command = vg_command or _installed_vg_command

    def render(self, request: McpConfigRequest) -> str:
        _validate_agent(request.agent)
        _validate_server_name(request.server_name)
        if request.agent == "claude":
            return self._render_claude(request)
        payload = {
            "mcpServers": {
                request.server_name: {
                    "command": "vg",
                    "args": [
                        "serve",
                        "--mcp",
                        "--graph-home",
                        str(request.graph_home_path.expanduser().resolve()),
                    ],
                }
            }
        }
        return json.dumps(payload, sort_keys=True, indent=2) + "\n"

    def _render_claude(self, request: McpConfigRequest) -> str:
        # Claude Code starts the server from its own working directory and PATH, so use the absolute vg path.
        command = self._vg_command()
        if not command:
            raise McpConfigError("vg_command_not_found: install vault-graph so `vg` is on PATH, then retry")
        args = ["serve", "--mcp"]
        graph_home = request.graph_home_path.expanduser().resolve()
        if graph_home != (Path.home() / ".vault-graph").resolve():
            args += ["--graph-home", str(graph_home)]
        payload = {"mcpServers": {request.server_name: {"type": "stdio", "command": command, "args": args}}}
        return json.dumps(payload, indent=2) + "\n"


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
                graph_home_path=request.graph_home_path,
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
            # copy2 keeps the file mode, so a private config stays private in its backup.
            shutil.copy2(config_path, backup_path)
        next_payload = dict(current_payload)
        next_servers = dict(_mcp_servers(next_payload))
        next_servers[request.server_name] = desired_entry
        next_payload["mcpServers"] = next_servers
        if request.agent == "claude":
            # Claude Code owns this file: keep its key order and text as written, and replace it in one rename.
            _replace_file(config_path, json.dumps(next_payload, indent=2, ensure_ascii=False) + "\n")
        else:
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

    def unregister(self, request: McpUnregistrationRequest) -> McpRegistrationReport:
        """Remove ``mcpServers.<server_name>`` from a Claude Code config, keeping every other key and a backup."""
        if request.agent != "claude":
            raise McpConfigError("unsupported_mcp_agent: unregister supports claude only")
        _validate_server_name(request.server_name)
        config_path = request.config_path.expanduser()
        current_payload = self._read_existing_payload(config_path)
        current_servers = _mcp_servers(current_payload)
        changed = request.server_name in current_servers
        if request.dry_run or not changed:
            return McpRegistrationReport(
                agent=request.agent,
                config_path=config_path,
                server_name=request.server_name,
                changed=changed,
                dry_run=request.dry_run,
            )

        backup_path = self._backup_path(config_path)
        # copy2 keeps the file mode, so a private config stays private in its backup.
        shutil.copy2(config_path, backup_path)
        next_payload = dict(current_payload)
        next_payload["mcpServers"] = {
            name: entry for name, entry in current_servers.items() if name != request.server_name
        }
        # Same write rule as register for Claude Code: keep key order and text, replace in one rename.
        _replace_file(config_path, json.dumps(next_payload, indent=2, ensure_ascii=False) + "\n")
        return McpRegistrationReport(
            agent=request.agent,
            config_path=config_path,
            server_name=request.server_name,
            changed=True,
            dry_run=False,
            backup_path=backup_path,
        )

    def default_config_path(self, agent: McpAgent) -> Path:
        _validate_agent(agent)
        if agent == "claude":
            # Claude Code reads join(CLAUDE_CONFIG_DIR || homedir(), ".claude.json"); an empty value means unset.
            config_dir = os.environ.get("CLAUDE_CONFIG_DIR")
            return (Path(config_dir).expanduser() if config_dir else Path.home()) / ".claude.json"
        codex_home = os.environ.get("CODEX_HOME")
        return Path(codex_home).expanduser() / "config.toml" if codex_home else Path.home() / ".codex" / "config.toml"

    def _register_codex_toml(self, *, request: McpRegistrationRequest, config_path: Path) -> McpRegistrationReport:
        if not config_path.parent.exists():
            raise McpConfigError("mcp_config_parent_missing: config parent directory does not exist")
        desired_block = _codex_toml_server_block(
            server_name=request.server_name,
            graph_home_path=request.graph_home_path.expanduser().resolve(),
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
    if agent not in SUPPORTED_MCP_AGENTS:
        raise McpConfigError(f"unsupported_mcp_agent: supported agents are {', '.join(SUPPORTED_MCP_AGENTS)}")


def _installed_vg_command() -> str | None:
    # The vg running `vg setup` comes first. The install command runs a vg it just installed by its absolute path,
    # and the hooks record that vg, so another vg earlier on PATH must not end up in the MCP entry.
    running = running_vg_path()
    if running is not None:
        return str(running)
    found = shutil.which("vg")
    return os.path.abspath(found) if found else None


def _replace_file(path: Path, text: str) -> None:
    """Write ``text`` to a temp file in the same folder, keep the old file mode, then rename over ``path``."""
    handle, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        if path.exists():
            shutil.copymode(path, temp_name)
        os.replace(temp_name, path)
    except BaseException:
        Path(temp_name).unlink(missing_ok=True)
        raise


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


def _codex_toml_server_block(*, server_name: str, graph_home_path: Path) -> str:
    _validate_server_name(server_name)
    args = ["serve", "--mcp", "--graph-home", str(graph_home_path)]
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
