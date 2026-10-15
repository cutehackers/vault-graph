"""Compatibility import for :mod:`vault_graph.project.code.code_projection_service`."""

import hashlib as hashlib
import json as json
import shutil as shutil
import sqlite3 as sqlite3
import sys
import uuid as uuid
from collections.abc import Callable as Callable
from collections.abc import Iterable as Iterable
from collections.abc import Mapping as Mapping
from functools import partial as partial
from pathlib import Path as Path
from typing import Literal as Literal

from vault_graph.project.code import code_projection_service as _implementation
from vault_graph.project.code.code_freshness import CodeFreshnessService as CodeFreshnessService
from vault_graph.project.code.code_generation import CodeGenerationError as CodeGenerationError
from vault_graph.project.code.code_generation import CodeGenerationLayout as CodeGenerationLayout
from vault_graph.project.code.code_generation import CodeProjectionGenerationManager as CodeProjectionGenerationManager
from vault_graph.project.code.code_models import CODE_PROJECTION_SCHEMA_VERSION as CODE_PROJECTION_SCHEMA_VERSION
from vault_graph.project.code.code_models import CodeEdgeRecord as CodeEdgeRecord
from vault_graph.project.code.code_models import CodeFileInput as CodeFileInput
from vault_graph.project.code.code_models import CodeFileSnapshot as CodeFileSnapshot
from vault_graph.project.code.code_models import CodeFreshnessReport as CodeFreshnessReport
from vault_graph.project.code.code_models import CodeFreshnessRequest as CodeFreshnessRequest
from vault_graph.project.code.code_models import CodeFreshnessState as CodeFreshnessState
from vault_graph.project.code.code_models import CodeIndexPlan as CodeIndexPlan
from vault_graph.project.code.code_models import CodeIndexRequest as CodeIndexRequest
from vault_graph.project.code.code_models import CodeManifest as CodeManifest
from vault_graph.project.code.code_models import CodeParseDiagnostic as CodeParseDiagnostic
from vault_graph.project.code.code_models import CodeParseResult as CodeParseResult
from vault_graph.project.code.code_models import CodeReconcilePlan as CodeReconcilePlan
from vault_graph.project.code.code_models import CodeRepositoryEntry as CodeRepositoryEntry
from vault_graph.project.code.code_models import CodeRunReport as CodeRunReport
from vault_graph.project.code.code_models import PendingCodeReference as PendingCodeReference
from vault_graph.project.code.code_models import code_file_identity as code_file_identity
from vault_graph.project.code.code_projection_service import CodeProjectionService as CodeProjectionService
from vault_graph.project.code.code_projection_service import StoreFactory as StoreFactory
from vault_graph.project.code.code_projection_service import _as_snapshot as _as_snapshot
from vault_graph.project.code.code_projection_service import _entries_from_catalog as _entries_from_catalog
from vault_graph.project.code.code_projection_service import _generation_repository_ids as _generation_repository_ids
from vault_graph.project.code.code_projection_service import _policy_revision as _policy_revision
from vault_graph.project.code.code_projection_service import _rebind_parse_result as _rebind_parse_result
from vault_graph.project.code.code_projection_service import _run_report as _run_report
from vault_graph.project.code.code_projection_service import _select_entries as _select_entries
from vault_graph.project.code.dart_parser import DartCodeParserAdapter as DartCodeParserAdapter
from vault_graph.project.code.parser_adapter import CodeParserAdapter as CodeParserAdapter
from vault_graph.project.code.python_parser import PythonCodeParserAdapter as PythonCodeParserAdapter
from vault_graph.project.code.reference_resolution import CodeReferenceResolver as CodeReferenceResolver
from vault_graph.project.code.repository_catalog import CodeRepositoryCatalog as CodeRepositoryCatalog
from vault_graph.project.code.repository_catalog import repository_policy_revision as repository_policy_revision
from vault_graph.project.code.source_scanning import CodeScanResult as CodeScanResult
from vault_graph.project.code.source_scanning import CodeSourceScanner as CodeSourceScanner
from vault_graph.storage.interfaces.code_projection_store import CodeProjectionStore as CodeProjectionStore

sys.modules[__name__] = _implementation
