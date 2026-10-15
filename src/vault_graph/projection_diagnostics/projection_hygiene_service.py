"""Compatibility import for :mod:`vault_graph.operation.diagnostics.projection_hygiene_service`."""

import json as json
import sqlite3 as sqlite3
import sys
from dataclasses import asdict as asdict
from dataclasses import dataclass as dataclass
from pathlib import Path as Path
from typing import cast as cast

from vault_graph.indexing.ingestion.document_authority import DocumentRole as DocumentRole
from vault_graph.operation.diagnostics import projection_hygiene_service as _implementation
from vault_graph.operation.diagnostics.projection_hygiene_service import (
    ProjectionHygieneReport as ProjectionHygieneReport,
)
from vault_graph.operation.diagnostics.projection_hygiene_service import (
    ProjectionHygieneService as ProjectionHygieneService,
)
from vault_graph.operation.diagnostics.projection_hygiene_service import RoleCount as RoleCount
from vault_graph.operation.diagnostics.projection_hygiene_service import SchemaVersion as SchemaVersion
from vault_graph.operation.diagnostics.projection_hygiene_service import _bundle_manifest as _bundle_manifest
from vault_graph.operation.diagnostics.projection_hygiene_service import _BundleManifestAudit as _BundleManifestAudit
from vault_graph.operation.diagnostics.projection_hygiene_service import _connect_readonly as _connect_readonly
from vault_graph.operation.diagnostics.projection_hygiene_service import _dangling_graph_refs as _dangling_graph_refs
from vault_graph.operation.diagnostics.projection_hygiene_service import _metadata_version as _metadata_version
from vault_graph.operation.diagnostics.projection_hygiene_service import _projection_version as _projection_version
from vault_graph.operation.scope.vault_catalog import QueryScope as QueryScope
from vault_graph.storage.interfaces.graph_store import GraphStore as GraphStore
from vault_graph.storage.local.chroma_vector_store import ChromaVectorStore as ChromaVectorStore
from vault_graph.storage.local.sqlite_metadata_store import SQLiteMetadataStore as SQLiteMetadataStore

sys.modules[__name__] = _implementation
