"""IndexService.status returns a typed status report Protocol, not Any (task 11, carried over from task 6)."""

import dataclasses
import typing

from vault_graph.indexing.index_service import IndexService, IndexStatusReading, IndexStatusReport
from vault_graph.operation.diagnostics.index_status_reader import IndexStatusReader, StatusReport


def _protocol_fields(protocol: type) -> set[str]:
    return {name for name, value in vars(protocol).items() if isinstance(value, property)}


def test_status_report_protocol_lists_every_status_report_field() -> None:
    assert _protocol_fields(IndexStatusReport) == {field.name for field in dataclasses.fields(StatusReport)}


def test_status_read_port_and_service_return_the_protocol() -> None:
    assert typing.get_type_hints(IndexStatusReading.read)["return"] is IndexStatusReport
    assert typing.get_type_hints(IndexService.status)["return"] is IndexStatusReport
    assert typing.get_type_hints(IndexStatusReader.read)["return"] is StatusReport


def test_local_status_stores_reexport_the_port_types() -> None:
    from vault_graph.storage.interfaces import graph_status_store as graph_port
    from vault_graph.storage.interfaces import vector_status_store as vector_port
    from vault_graph.storage.local import graph_status_store as graph_local
    from vault_graph.storage.local import vector_status_store as vector_local

    assert graph_local.GraphRunStatus is graph_port.GraphRunStatus
    assert graph_local.graph_spec_key is graph_port.graph_spec_key
    assert graph_local.graph_scope_status_key is graph_port.graph_scope_status_key
    assert vector_local.VectorRunStatus is vector_port.VectorRunStatus
    assert vector_local.embedding_spec_key is vector_port.embedding_spec_key
    assert vector_local.scope_key_for_status is vector_port.scope_key_for_status
