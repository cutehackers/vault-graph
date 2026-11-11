"""Thin Typer adapter for `vg doctor`: print each problem and the one command that fixes it. Reads only."""

from __future__ import annotations

import json
import os
import tomllib
from pathlib import Path
from typing import cast

import typer

from vault_graph.errors import VaultGraphError
from vault_graph.interface.composition.adapters.text_embeddings import (
    DEFAULT_EMBEDDING_PRESET,
    EMBEDDING_PRESETS,
    embedding_model_downloaded,
)
from vault_graph.interface.composition.query_scope_resolution import metadata_index_check
from vault_graph.operation.diagnostics.doctor_service import (
    DoctorInputs,
    EmbeddingModelState,
    McpRegistrationState,
    diagnose,
)
from vault_graph.operation.integration.mcp.mcp_config_registration import (
    SUPPORTED_MCP_AGENTS,
    McpAgent,
    McpConfigRegistrar,
)
from vault_graph.operation.scope.catalog_service import CatalogService
from vault_graph.operation.scope.embedding_selection import DEFAULT_MODELS_DIR, load_embedding_selection
from vault_graph.operation.scope.graph_home import GraphHomeResolver
from vault_graph.storage.local.sqlite_metadata_store import SQLiteMetadataStore

_SERVER_NAME = "vault-graph"

# Module-level option values keep ruff B008 satisfied without a per-file ignore.
_GRAPH_HOME_OPTION = typer.Option(Path.home() / ".vault-graph", "--graph-home", help="Vault Graph Data Home path.")
_AGENT_OPTION = typer.Option("claude", "--agent", help="Agent whose MCP config is checked: claude or codex.")
_MCP_CONFIG_PATH_OPTION = typer.Option(
    None, "--mcp-config-path", help="Agent MCP config file. Defaults to the path `vg mcp register` uses."
)


def doctor(
    state: Path = _GRAPH_HOME_OPTION,
    agent: str = _AGENT_OPTION,
    mcp_config_path: Path | None = _MCP_CONFIG_PATH_OPTION,
) -> None:
    """Find index, model and MCP problems and print one fix command for each. Changes nothing."""
    if agent not in SUPPORTED_MCP_AGENTS:
        typer.echo(f"unsupported_mcp_agent: supported agents are {', '.join(SUPPORTED_MCP_AGENTS)}")
        raise typer.Exit(1)
    try:
        findings = diagnose(_inputs(state, cast(McpAgent, agent), mcp_config_path))
    except VaultGraphError as exc:
        typer.echo(str(exc))
        raise typer.Exit(1) from exc
    if not findings:
        typer.echo("ok: no problems found")
        return
    for finding in findings:
        typer.echo(f"problem: {finding.problem}")
        typer.echo(f"fix: {finding.fix}")
    raise typer.Exit(1)


def _inputs(state: Path, agent: McpAgent, mcp_config_path: Path | None) -> DoctorInputs:
    descriptor = GraphHomeResolver().resolve(state)
    config_path = mcp_config_path or McpConfigRegistrar().default_config_path(agent)
    mcp = McpRegistrationState(agent=agent, config_path=config_path, registered=_mcp_registered(config_path))
    if not descriptor.initialized:
        return DoctorInputs(
            graph_home_path=descriptor.root_path,
            vault_ids=None,
            is_indexed=lambda _: False,
            embedding_model=lambda: EmbeddingModelState(DEFAULT_EMBEDDING_PRESET, DEFAULT_MODELS_DIR, False),
            mcp_registration=mcp,
        )
    catalog_service = CatalogService(graph_home_path=descriptor.root_path)
    catalog = catalog_service.load_catalog()
    # initialize=False opens SQLite read-only and never creates the file.
    metadata_store = SQLiteMetadataStore(catalog_service.metadata_path, initialize=False)
    return DoctorInputs(
        graph_home_path=descriptor.root_path,
        vault_ids=tuple(entry.vault_id for entry in catalog.entries() if entry.enabled),
        is_indexed=metadata_index_check(metadata_store),
        embedding_model=lambda: _embedding_model(catalog_service),
        mcp_registration=mcp,
    )


def _embedding_model(catalog_service: CatalogService) -> EmbeddingModelState:
    """The selected model and whether its files are on disk. An unreadable or unknown selection counts as missing."""
    try:
        selection = load_embedding_selection(catalog_service.embedding_config_path)
    except VaultGraphError:
        return EmbeddingModelState(DEFAULT_EMBEDDING_PRESET, _absolute(DEFAULT_MODELS_DIR), False)
    models_dir = _absolute(selection.models_dir)
    preset = EMBEDDING_PRESETS.get(selection.model or DEFAULT_EMBEDDING_PRESET)
    if preset is None:
        return EmbeddingModelState(DEFAULT_EMBEDDING_PRESET, models_dir, False)
    return EmbeddingModelState(preset.name, models_dir, embedding_model_downloaded(preset, models_dir))


def _mcp_registered(config_path: Path) -> bool:
    """Whether the agent config names the vault-graph server. A missing or unreadable file counts as not registered."""
    path = config_path.expanduser()
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    try:
        if path.suffix == ".toml":
            servers = tomllib.loads(text).get("mcp_servers")
        else:
            payload = json.loads(text)
            servers = payload.get("mcpServers") if isinstance(payload, dict) else None
    except (tomllib.TOMLDecodeError, json.JSONDecodeError):
        return False
    return isinstance(servers, dict) and _SERVER_NAME in servers


def _absolute(path: Path) -> Path:
    """Expand `~` and make the path absolute without following symlinks."""
    return Path(os.path.abspath(path.expanduser()))
