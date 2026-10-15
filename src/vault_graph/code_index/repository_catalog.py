"""Compatibility import for :mod:`vault_graph.project.code.repository_catalog`."""

import hashlib as hashlib
import json as json
import sys
from collections.abc import Iterable as Iterable
from pathlib import Path as Path
from typing import Any as Any
from typing import Protocol as Protocol
from typing import runtime_checkable as runtime_checkable

import yaml as yaml

from vault_graph.errors import CatalogError as CatalogError
from vault_graph.operation.scope.catalog_service import CatalogService as CatalogService
from vault_graph.operation.scope.graph_home import DEFAULT_GRAPH_HOME as DEFAULT_GRAPH_HOME
from vault_graph.operation.scope.path_guard import assert_target_outside_vaults as assert_target_outside_vaults
from vault_graph.operation.scope.vault_catalog import VaultCatalog as VaultCatalog
from vault_graph.project.code import repository_catalog as _implementation
from vault_graph.project.code.code_models import CodeRepositoryEntry as CodeRepositoryEntry
from vault_graph.project.code.repository_catalog import SUPPORTED_CODE_LANGUAGES as SUPPORTED_CODE_LANGUAGES
from vault_graph.project.code.repository_catalog import (
    SUPPORTED_GIT_REVISION_POLICIES as SUPPORTED_GIT_REVISION_POLICIES,
)
from vault_graph.project.code.repository_catalog import CodeRepositoryCatalog as CodeRepositoryCatalog
from vault_graph.project.code.repository_catalog import CodeRepositoryCatalogService as CodeRepositoryCatalogService
from vault_graph.project.code.repository_catalog import _entry_from_mapping as _entry_from_mapping
from vault_graph.project.code.repository_catalog import _normalize_entry as _normalize_entry
from vault_graph.project.code.repository_catalog import _state_namespace_key as _state_namespace_key
from vault_graph.project.code.repository_catalog import _validate_entry_policy as _validate_entry_policy
from vault_graph.project.code.repository_catalog import _validate_glob_pattern as _validate_glob_pattern
from vault_graph.project.code.repository_catalog import _validate_state_namespace as _validate_state_namespace
from vault_graph.project.code.repository_catalog import _YamlCodeRepositoryCatalog as _YamlCodeRepositoryCatalog
from vault_graph.project.code.repository_catalog import repository_policy_revision as repository_policy_revision

sys.modules[__name__] = _implementation
