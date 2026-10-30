"""Status fields that memory views read.

Memory views (M10) must not import the diagnostics StatusReport (M15). Any object with these
read-only attributes, such as StatusReport, satisfies this Protocol.
"""

from __future__ import annotations

from typing import Protocol

from vault_graph.retrieval.graph.graph_readiness import GraphReadiness


class MemoryStatusView(Protocol):
    @property
    def metadata_ok(self) -> bool: ...

    @property
    def metadata_schema_compatible(self) -> bool: ...

    @property
    def metadata_message(self) -> str: ...

    @property
    def vector_ok(self) -> bool: ...

    @property
    def vector_backend(self) -> str: ...

    @property
    def vector_schema_compatible(self) -> bool: ...

    @property
    def vector_message(self) -> str: ...

    @property
    def vector_revision(self) -> str | None: ...

    @property
    def vector_last_success_at(self) -> str | None: ...

    @property
    def vector_last_error_at(self) -> str | None: ...

    @property
    def vector_stale_count(self) -> int: ...

    @property
    def vector_last_error(self) -> str | None: ...

    @property
    def vector_status_scope(self) -> str: ...

    @property
    def graph_readiness(self) -> GraphReadiness: ...

    @property
    def graph_status_scope(self) -> str: ...

    @property
    def graph_last_success_revision(self) -> str | None: ...

    @property
    def graph_last_success_at(self) -> str | None: ...

    @property
    def graph_last_error_at(self) -> str | None: ...

    @property
    def graph_last_error(self) -> str | None: ...
