"""Compatibility import for :mod:`vault_graph.context.memory.memory_request_context`."""

import sys
from collections.abc import Callable as Callable
from dataclasses import dataclass as dataclass
from datetime import UTC as UTC
from datetime import datetime as datetime
from typing import TYPE_CHECKING as TYPE_CHECKING
from typing import Protocol as Protocol

from vault_graph.context.memory import memory_request_context as _implementation
from vault_graph.context.memory.memory_request_context import MemoryRequestContext as MemoryRequestContext
from vault_graph.context.memory.memory_request_context import MemoryStatusService as MemoryStatusService
from vault_graph.context.memory.memory_request_context import MemoryVaultDocuments as MemoryVaultDocuments
from vault_graph.context.memory.memory_request_context import _utc_now as _utc_now
from vault_graph.context.memory.memory_request_context import (
    build_memory_request_context as build_memory_request_context,
)
from vault_graph.context.memory.memory_source_reader import MemorySourceReader as MemorySourceReader
from vault_graph.errors import MemoryProjectionError as MemoryProjectionError
from vault_graph.indexing.ingestion.document_normalizer import DocumentSnapshot as DocumentSnapshot
from vault_graph.operation.scope.catalog_query_scopes import actual_query_scopes as actual_query_scopes
from vault_graph.operation.scope.vault_catalog import QueryScope as QueryScope
from vault_graph.operation.scope.vault_catalog import VaultCatalog as VaultCatalog

sys.modules[__name__] = _implementation
