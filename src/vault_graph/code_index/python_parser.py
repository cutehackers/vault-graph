"""Compatibility import for :mod:`vault_graph.project.code.python_parser`."""

import sys
from dataclasses import dataclass as dataclass
from typing import Any as Any

from vault_graph.project.code import python_parser as _implementation
from vault_graph.project.code.code_models import CODE_PARSER_SPEC_VERSION as CODE_PARSER_SPEC_VERSION
from vault_graph.project.code.code_models import CodeFileInput as CodeFileInput
from vault_graph.project.code.code_models import CodeParseResult as CodeParseResult
from vault_graph.project.code.code_models import CodeReferenceRecord as CodeReferenceRecord
from vault_graph.project.code.code_models import CodeSymbolRecord as CodeSymbolRecord
from vault_graph.project.code.python_parser import PythonCodeParserAdapter as PythonCodeParserAdapter
from vault_graph.project.code.python_parser import PythonParserAdapter as PythonParserAdapter
from vault_graph.project.code.python_parser import _Declaration as _Declaration
from vault_graph.project.code.python_parser import _is_test_name as _is_test_name
from vault_graph.project.code.python_parser import _module_name as _module_name
from vault_graph.project.code.python_parser import _python_base_nodes as _python_base_nodes
from vault_graph.project.code.python_parser import _python_call_target as _python_call_target
from vault_graph.project.code.python_parser import _python_import_targets as _python_import_targets
from vault_graph.project.code.python_parser import _reference_sort_key as _reference_sort_key
from vault_graph.project.code.python_parser import _symbol_sort_key as _symbol_sort_key
from vault_graph.project.code.tree_sitter_parsing import file_identity as file_identity
from vault_graph.project.code.tree_sitter_parsing import node_end as node_end
from vault_graph.project.code.tree_sitter_parsing import node_start as node_start
from vault_graph.project.code.tree_sitter_parsing import node_text as node_text
from vault_graph.project.code.tree_sitter_parsing import parse_source as parse_source
from vault_graph.project.code.tree_sitter_parsing import source_signature as source_signature
from vault_graph.project.code.tree_sitter_parsing import stable_identity as stable_identity
from vault_graph.project.code.tree_sitter_parsing import syntax_diagnostics as syntax_diagnostics
from vault_graph.project.code.tree_sitter_parsing import unsupported_diagnostics as unsupported_diagnostics
from vault_graph.project.code.tree_sitter_parsing import walk as walk

sys.modules[__name__] = _implementation
