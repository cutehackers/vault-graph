"""`vg doctor` checks: each problem found comes with one command that fixes it.

Spec 2026-11-11 §4.4.1 and §6. The checks only read. They never change a Vault or Graph Home, so the caller
passes in what needs another area to read (index state, model files, MCP registration).
"""

from __future__ import annotations

import shlex
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from vault_graph.indexing.vector_failure_log import read_vector_failures


@dataclass(frozen=True)
class DoctorFinding:
    problem: str
    fix: str


@dataclass(frozen=True)
class EmbeddingModelState:
    name: str
    models_dir: Path
    downloaded: bool


@dataclass(frozen=True)
class McpRegistrationState:
    agent: str
    config_path: Path
    registered: bool


@dataclass(frozen=True)
class DoctorInputs:
    """What the checks read. `vault_ids` is None when Graph Home is not initialized."""

    graph_home_path: Path
    vault_ids: tuple[str, ...] | None
    is_indexed: Callable[[str], bool]
    embedding_model: Callable[[], EmbeddingModelState]
    mcp_registration: McpRegistrationState


def diagnose(inputs: DoctorInputs) -> tuple[DoctorFinding, ...]:
    """Return the problems in a fixed order: Graph Home, failure record, index, model files, MCP."""
    graph_home = inputs.graph_home_path
    findings: list[DoctorFinding] = []
    if inputs.vault_ids is None:
        findings.append(
            DoctorFinding(
                problem="graph_home_not_initialized: no Vault is registered",
                fix=(
                    f"vg setup --vault <Vault 경로> --graph-home {_quote(graph_home)} "
                    f"--agent {inputs.mcp_registration.agent} --mcp"
                ),
            )
        )
    else:
        findings.extend(_failure_findings(graph_home))
        findings.extend(
            DoctorFinding(
                problem=f"index_missing vault_id={vault_id}: no document is indexed",
                fix=_index_command(graph_home, vault_id),
            )
            for vault_id in inputs.vault_ids
            if not inputs.is_indexed(vault_id)
        )
        model = inputs.embedding_model()
        if not model.downloaded:
            findings.append(
                DoctorFinding(
                    problem=(
                        f"embedding_model_missing model={model.name}: no model files in {model.models_dir}, "
                        "so search returns keyword results only"
                    ),
                    fix=(
                        f"vg embedding use {model.name} --models-dir {_quote(model.models_dir)} "
                        f"--graph-home {_quote(graph_home)}"
                    ),
                )
            )
    mcp = inputs.mcp_registration
    if not mcp.registered:
        findings.append(
            DoctorFinding(
                problem=f"mcp_not_registered agent={mcp.agent}: no vault-graph server in {mcp.config_path}",
                fix=(
                    f"vg mcp register --agent {mcp.agent} --graph-home {_quote(graph_home)} "
                    f"--config-path {_quote(mcp.config_path)}"
                ),
            )
        )
    return tuple(findings)


def _failure_findings(graph_home: Path) -> list[DoctorFinding]:
    failures = read_vector_failures(graph_home)
    return [
        DoctorFinding(
            problem=(
                f"index_failed vault_id={failure.vault_id} count={failure.count} "
                f"since={failure.first_failed_at.isoformat()}: {failure.error_head}"
            ),
            fix=_index_command(graph_home, failure.vault_id),
        )
        for failure in sorted(failures.values(), key=lambda item: item.vault_id)
    ]


def _index_command(graph_home: Path, vault_id: str) -> str:
    # A person running `vg index` is never held back by the retry wait, and a vector success clears the record.
    return f"vg index --vault-id {shlex.quote(vault_id)} --graph-home {_quote(graph_home)}"


def _quote(path: Path) -> str:
    return shlex.quote(str(path))


__all__ = [
    "DoctorFinding",
    "DoctorInputs",
    "EmbeddingModelState",
    "McpRegistrationState",
    "diagnose",
]
