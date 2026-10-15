"""Compatibility import for :mod:`vault_graph.project.code.code_freshness`."""

import hashlib as hashlib
import json as json
import sys
from collections.abc import Callable as Callable
from collections.abc import Iterable as Iterable
from pathlib import Path as Path
from typing import cast as cast

from vault_graph.project.code import code_freshness as _implementation
from vault_graph.project.code.code_freshness import CodeFreshness as CodeFreshness
from vault_graph.project.code.code_freshness import CodeFreshnessService as CodeFreshnessService
from vault_graph.project.code.code_freshness import StoreFactory as StoreFactory
from vault_graph.project.code.code_freshness import _entries_from_catalog as _entries_from_catalog
from vault_graph.project.code.code_freshness import _last_freshness as _last_freshness
from vault_graph.project.code.code_freshness import _pending_paths as _pending_paths
from vault_graph.project.code.code_freshness import _policy_revision as _policy_revision
from vault_graph.project.code.code_freshness import _select_entries as _select_entries
from vault_graph.project.code.code_generation import CodeGenerationLayout as CodeGenerationLayout
from vault_graph.project.code.code_generation import CodeProjectionGenerationManager as CodeProjectionGenerationManager
from vault_graph.project.code.code_models import CODE_PARSER_SPEC_VERSION as CODE_PARSER_SPEC_VERSION
from vault_graph.project.code.code_models import CODE_PROJECTION_SCHEMA_VERSION as CODE_PROJECTION_SCHEMA_VERSION
from vault_graph.project.code.code_models import CodeFreshnessReport as CodeFreshnessReport
from vault_graph.project.code.code_models import CodeFreshnessRequest as CodeFreshnessRequest
from vault_graph.project.code.code_models import CodeFreshnessState as CodeFreshnessState
from vault_graph.project.code.code_models import CodeRepositoryEntry as CodeRepositoryEntry
from vault_graph.project.code.repository_catalog import CodeRepositoryCatalog as CodeRepositoryCatalog
from vault_graph.project.code.repository_catalog import repository_policy_revision as repository_policy_revision
from vault_graph.project.code.source_scanning import CodeScanResult as CodeScanResult
from vault_graph.project.code.source_scanning import CodeSourceScanner as CodeSourceScanner
from vault_graph.storage.interfaces.code_projection_store import CodeProjectionStore as CodeProjectionStore

sys.modules[__name__] = _implementation
