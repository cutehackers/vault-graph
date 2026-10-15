"""Compatibility import for :mod:`vault_graph.project.code.reference_resolution`."""

import sys
from collections import defaultdict as defaultdict
from collections.abc import Iterable as Iterable
from dataclasses import dataclass as dataclass
from pathlib import PurePosixPath as PurePosixPath

from vault_graph.project.code import reference_resolution as _implementation
from vault_graph.project.code.code_models import CODE_PARSER_SPEC_VERSION as CODE_PARSER_SPEC_VERSION
from vault_graph.project.code.code_models import CodeEdgeRecord as CodeEdgeRecord
from vault_graph.project.code.code_models import CodeFileSnapshot as CodeFileSnapshot
from vault_graph.project.code.code_models import CodeReferenceRecord as CodeReferenceRecord
from vault_graph.project.code.code_models import CodeSymbolRecord as CodeSymbolRecord
from vault_graph.project.code.code_models import PendingCodeReference as PendingCodeReference
from vault_graph.project.code.code_models import ResolutionResult as ResolutionResult
from vault_graph.project.code.reference_resolution import CodeReferenceResolver as CodeReferenceResolver
from vault_graph.project.code.reference_resolution import _clean_target as _clean_target
from vault_graph.project.code.reference_resolution import _edge_key as _edge_key
from vault_graph.project.code.reference_resolution import _edge_sort_key as _edge_sort_key
from vault_graph.project.code.reference_resolution import _matches_import_path as _matches_import_path
from vault_graph.project.code.reference_resolution import _module_from_path as _module_from_path
from vault_graph.project.code.reference_resolution import _normal_module_name as _normal_module_name
from vault_graph.project.code.reference_resolution import _pending_key as _pending_key
from vault_graph.project.code.reference_resolution import _pending_namespace as _pending_namespace
from vault_graph.project.code.reference_resolution import _pending_sort_key as _pending_sort_key
from vault_graph.project.code.reference_resolution import _reference_sort_key as _reference_sort_key
from vault_graph.project.code.reference_resolution import _relative_module as _relative_module
from vault_graph.project.code.reference_resolution import _symbol_sort_key as _symbol_sort_key
from vault_graph.project.code.reference_resolution import _SymbolIndexes as _SymbolIndexes
from vault_graph.project.code.reference_resolution import _unique_symbols as _unique_symbols
from vault_graph.project.code.tree_sitter_parsing import stable_identity as stable_identity

sys.modules[__name__] = _implementation
