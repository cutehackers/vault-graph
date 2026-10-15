"""Compatibility import for :mod:`vault_graph.operation.scope.vault_catalog`."""

import sys
from collections.abc import Iterable as Iterable
from dataclasses import dataclass as dataclass
from pathlib import Path as Path
from typing import Any as Any

import yaml as yaml

from vault_graph.errors import CatalogError as CatalogError
from vault_graph.operation.scope import vault_catalog as _implementation
from vault_graph.operation.scope.vault_catalog import ALLOWED_CONTENT_ROOTS as ALLOWED_CONTENT_ROOTS
from vault_graph.operation.scope.vault_catalog import DEFAULT_CONTENT_SCOPES as DEFAULT_CONTENT_SCOPES
from vault_graph.operation.scope.vault_catalog import QueryScope as QueryScope
from vault_graph.operation.scope.vault_catalog import VaultCatalog as VaultCatalog
from vault_graph.operation.scope.vault_catalog import VaultCatalogEntry as VaultCatalogEntry
from vault_graph.operation.scope.vault_catalog import _union_content_scopes as _union_content_scopes
from vault_graph.operation.scope.vault_catalog import _validate_content_scope as _validate_content_scope
from vault_graph.operation.scope.vault_catalog import _validate_content_scope_value as _validate_content_scope_value

sys.modules[__name__] = _implementation
