"""Compatibility import for :mod:`vault_graph.project.code.source_scanning`."""

import fnmatch as fnmatch
import hashlib as hashlib
import subprocess as subprocess
import sys
from collections.abc import Iterable as Iterable
from dataclasses import dataclass as dataclass
from pathlib import Path as Path
from pathlib import PurePosixPath as PurePosixPath

from vault_graph.project.code import source_scanning as _implementation
from vault_graph.project.code.code_models import CODE_PARSER_SPEC_VERSION as CODE_PARSER_SPEC_VERSION
from vault_graph.project.code.code_models import CodeFileInput as CodeFileInput
from vault_graph.project.code.code_models import CodeRepositoryEntry as CodeRepositoryEntry
from vault_graph.project.code.repository_catalog import repository_policy_revision as repository_policy_revision
from vault_graph.project.code.source_scanning import DEFAULT_EXCLUDED_DIRECTORIES as DEFAULT_EXCLUDED_DIRECTORIES
from vault_graph.project.code.source_scanning import CodeScanResult as CodeScanResult
from vault_graph.project.code.source_scanning import CodeSourceScanError as CodeSourceScanError
from vault_graph.project.code.source_scanning import CodeSourceScanner as CodeSourceScanner
from vault_graph.project.code.source_scanning import ScanResult as ScanResult
from vault_graph.project.code.source_scanning import SourceScanner as SourceScanner
from vault_graph.project.code.source_scanning import _git as _git
from vault_graph.project.code.source_scanning import _is_selected as _is_selected
from vault_graph.project.code.source_scanning import _is_test_path as _is_test_path
from vault_graph.project.code.source_scanning import _language_for_path as _language_for_path
from vault_graph.project.code.source_scanning import _matches as _matches
from vault_graph.project.code.source_scanning import _selected_digest as _selected_digest
from vault_graph.project.code.source_scanning import _source_revision as _source_revision
from vault_graph.project.code.source_scanning import _walk_files as _walk_files
from vault_graph.project.code.source_scanning import scan_repository as scan_repository

sys.modules[__name__] = _implementation
