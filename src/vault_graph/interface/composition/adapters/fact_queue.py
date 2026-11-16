"""Job files of the session fact worker in `<graph-home>/facts/queue/` (spec 2026-11-16 D16, F10).

A job names one captured session part: the Vault that captured it and the part path. The capture hook writes one
job per `written` capture (task 18) and the fact worker removes it when the job is done or closed. A job file is
written under a name starting with `.` and renamed into place, so a reader never sees half a job.

Job file `<nanoseconds since the epoch>-<random>.json`, so names sort in the order jobs were written:

    {"schema": "vault-graph-facts-job/1", "vault": "<Vault name or null>", "vault_root": "<absolute Vault folder>",
     "part": "<part path relative to the Vault root>", "created_at": "<UTC ISO time>"}

The worker reads the exchanges from the part file itself. That file is what `sessions attach-facts` checks the
exchange ids and `source_sha256` against, and its text is already redacted by the Vault tool.
"""

from __future__ import annotations

import json
import os
import secrets
import tempfile
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from vault_graph.errors import VaultGraphError
from vault_graph.operation.scope.facts_settings import facts_queue_dir

FACT_JOB_SCHEMA = "vault-graph-facts-job/1"
_MAX_JOB_BYTES = 16_384


class FactJobInvalid(VaultGraphError):
    """A job file that cannot be read or does not match `vault-graph-facts-job/1`."""


@dataclass(frozen=True)
class FactJob:
    name: str
    """Job file name. Also the key of the job's entry in the failure log."""
    vault: str | None
    vault_root: Path
    part: str
    """Part path relative to `vault_root`, with `/` separators."""

    @property
    def part_path(self) -> Path:
        return self.vault_root / self.part


def enqueue_fact_job(
    graph_home: Path, *, vault_root: Path, vault: str | None, part: str, now: datetime | None = None
) -> Path:
    """Write one job file and return its path. `part` is relative to `vault_root`."""
    if not vault_root.is_absolute():
        raise FactJobInvalid(f"fact job Vault root must be absolute: {vault_root}")
    _check_part(part)
    created = (now or datetime.now(UTC)).astimezone(UTC)
    queue = facts_queue_dir(graph_home)
    queue.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": FACT_JOB_SCHEMA,
        "vault": vault,
        "vault_root": str(vault_root),
        "part": part,
        "created_at": created.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    # The wall clock in nanoseconds keeps jobs in the order they were written, whatever `now` says.
    name = f"{time.time_ns():020d}-{secrets.token_hex(4)}.json"
    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=queue, prefix=".job-", suffix=".tmp", delete=False
        ) as stream:
            temporary = stream.name
            json.dump(payload, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, queue / name)
        temporary = None
    finally:
        if temporary is not None and os.path.exists(temporary):
            os.unlink(temporary)
    return queue / name


def list_fact_jobs(graph_home: Path) -> list[Path]:
    """Job files in creation order. Names starting with `.` are still being written."""
    queue = facts_queue_dir(graph_home)
    if not queue.is_dir():
        return []
    return sorted(
        entry
        for entry in queue.iterdir()
        if entry.suffix == ".json" and not entry.name.startswith(".") and entry.is_file()
    )


def read_fact_job(path: Path) -> FactJob:
    """Read one job file. Raises `FactJobInvalid` for anything off the format."""
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise FactJobInvalid(f"fact job cannot be read: {path.name}: {exc.strerror}") from exc
    if len(raw) > _MAX_JOB_BYTES:
        raise FactJobInvalid(f"fact job is larger than {_MAX_JOB_BYTES} bytes: {path.name}")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FactJobInvalid(f"fact job is not JSON: {path.name}") from exc
    if not isinstance(payload, dict) or payload.get("schema") != FACT_JOB_SCHEMA:
        raise FactJobInvalid(f"fact job schema is not {FACT_JOB_SCHEMA}: {path.name}")
    vault, vault_root, part = payload.get("vault"), payload.get("vault_root"), payload.get("part")
    if not (vault is None or isinstance(vault, str)):
        raise FactJobInvalid(f"fact job vault must be a string or null: {path.name}")
    if not isinstance(vault_root, str) or not Path(vault_root).is_absolute():
        raise FactJobInvalid(f"fact job vault_root must be an absolute path: {path.name}")
    if not isinstance(part, str):
        raise FactJobInvalid(f"fact job part must be a string: {path.name}")
    _check_part(part)
    return FactJob(name=path.name, vault=vault, vault_root=Path(vault_root), part=part)


def remove_fact_job(path: Path) -> None:
    path.unlink(missing_ok=True)


def _check_part(part: str) -> None:
    pure = PurePosixPath(part)
    if not part or pure.is_absolute() or ".." in pure.parts or "\\" in part:
        raise FactJobInvalid(f"fact job part must be a path inside the Vault: {part!r}")
