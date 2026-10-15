"""Compatibility import for :mod:`vault_graph.interface.composition.graph_store_factory`."""

import json as json
import os as os
import stat as stat
import sys
import tempfile as tempfile
from pathlib import Path as Path
from typing import Literal as Literal
from typing import cast as cast

from vault_graph.errors import GraphStoreUnavailable as GraphStoreUnavailable
from vault_graph.interface.composition import graph_store_factory as _implementation
from vault_graph.interface.composition.graph_store_factory import document_store_path as document_store_path
from vault_graph.interface.composition.graph_store_factory import open_graph_store as open_graph_store
from vault_graph.interface.composition.graph_store_factory import selected_graph_backend as selected_graph_backend
from vault_graph.interface.composition.graph_store_factory import (
    write_graph_backend_selection as write_graph_backend_selection,
)
from vault_graph.operation.scope.catalog_service import CatalogService as CatalogService
from vault_graph.storage.interfaces.graph_store import GraphStore as GraphStore
from vault_graph.storage.interfaces.metadata_store import MetadataStore as MetadataStore
from vault_graph.storage.local.sqlite_graph_store import SQLiteGraphStore as SQLiteGraphStore

sys.modules[__name__] = _implementation
