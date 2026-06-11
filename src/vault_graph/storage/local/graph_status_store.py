from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from vault_graph.graph.graph_contracts import GraphExtractionSpec
from vault_graph.ingestion.vault_catalog import QueryScope


@dataclass(frozen=True)
class GraphRunStatus:
    scope_key: str
    graph_spec_key: str
    last_success_revision: str | None = None
    last_success_at: str | None = None
    last_error: str | None = None
    last_error_at: str | None = None


class LocalGraphStatusStore:
    def __init__(self, path: Path) -> None:
        self._path = path.expanduser().resolve()

    def read(self, *, scope_key: str, graph_spec_key: str) -> GraphRunStatus:
        loaded = self._read_payload()
        runs = loaded.get("runs", {})
        payload = runs.get(_run_key(scope_key=scope_key, graph_spec_key=graph_spec_key), {})
        return GraphRunStatus(
            scope_key=scope_key,
            graph_spec_key=graph_spec_key,
            last_success_revision=_optional_str(payload.get("last_success_revision")),
            last_success_at=_optional_str(payload.get("last_success_at")),
            last_error=_optional_str(payload.get("last_error")),
            last_error_at=_optional_str(payload.get("last_error_at")),
        )

    def record_success(self, *, scope_key: str, graph_spec_key: str, graph_index_revision: str) -> None:
        self._write_run(
            GraphRunStatus(
                scope_key=scope_key,
                graph_spec_key=graph_spec_key,
                last_success_revision=graph_index_revision,
                last_success_at=datetime.now(UTC).isoformat(),
                last_error=None,
                last_error_at=None,
            )
        )

    def record_failure(self, *, scope_key: str, graph_spec_key: str, error: str) -> None:
        current = self.read(scope_key=scope_key, graph_spec_key=graph_spec_key)
        self._write_run(
            GraphRunStatus(
                scope_key=scope_key,
                graph_spec_key=graph_spec_key,
                last_success_revision=current.last_success_revision,
                last_success_at=current.last_success_at,
                last_error=error,
                last_error_at=datetime.now(UTC).isoformat(),
            )
        )

    def _read_payload(self) -> dict[str, dict[str, dict[str, Any]]]:
        if not self._path.exists():
            return {"runs": {}}
        loaded = json.loads(self._path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            return {"runs": {}}
        runs = loaded.get("runs", {})
        if not isinstance(runs, dict):
            return {"runs": {}}
        return {"runs": cast(dict[str, dict[str, Any]], runs)}

    def _write_run(self, status: GraphRunStatus) -> None:
        loaded = self._read_payload()
        runs = loaded.setdefault("runs", {})
        if isinstance(runs, dict):
            runs[_run_key(scope_key=status.scope_key, graph_spec_key=status.graph_spec_key)] = asdict(status)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(loaded, sort_keys=True, indent=2), encoding="utf-8")


def graph_spec_key(spec: GraphExtractionSpec) -> str:
    return f"{spec.spec_version}|{spec.spec_digest}"


def graph_scope_status_key(scope: QueryScope) -> str:
    cross_vault = "cross" if scope.include_cross_vault else "local"
    return f"{','.join(scope.vault_ids)}:{','.join(scope.content_scopes)}:{cross_vault}"


def _run_key(*, scope_key: str, graph_spec_key: str) -> str:
    return f"{scope_key}|{graph_spec_key}"


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) else None
