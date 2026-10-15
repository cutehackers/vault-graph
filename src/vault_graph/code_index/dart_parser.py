"""Compatibility import for :mod:`vault_graph.project.code.dart_parser`."""

import sys
from dataclasses import dataclass as dataclass
from typing import Any as Any

from vault_graph.project.code import dart_parser as _implementation
from vault_graph.project.code.code_models import CODE_PARSER_SPEC_VERSION as CODE_PARSER_SPEC_VERSION
from vault_graph.project.code.code_models import CodeFileInput as CodeFileInput
from vault_graph.project.code.code_models import CodeParseResult as CodeParseResult
from vault_graph.project.code.code_models import CodeReferenceRecord as CodeReferenceRecord
from vault_graph.project.code.code_models import CodeSymbolRecord as CodeSymbolRecord
from vault_graph.project.code.dart_parser import DartCodeParserAdapter as DartCodeParserAdapter
from vault_graph.project.code.dart_parser import DartParserAdapter as DartParserAdapter
from vault_graph.project.code.dart_parser import _callee_identifiers as _callee_identifiers
from vault_graph.project.code.dart_parser import _constructor_name as _constructor_name
from vault_graph.project.code.dart_parser import _contains_anonymous_function as _contains_anonymous_function
from vault_graph.project.code.dart_parser import _dart_call_target as _dart_call_target
from vault_graph.project.code.dart_parser import _dart_constructor_call_target as _dart_constructor_call_target
from vault_graph.project.code.dart_parser import _dart_dynamic_selector_target as _dart_dynamic_selector_target
from vault_graph.project.code.dart_parser import _dart_import_target as _dart_import_target
from vault_graph.project.code.dart_parser import _dart_inheritance_nodes as _dart_inheritance_nodes
from vault_graph.project.code.dart_parser import _dart_module_identity as _dart_module_identity
from vault_graph.project.code.dart_parser import _dart_selector_chain as _dart_selector_chain
from vault_graph.project.code.dart_parser import _dart_selector_is_call as _dart_selector_is_call
from vault_graph.project.code.dart_parser import _Declaration as _Declaration
from vault_graph.project.code.dart_parser import _declaration_name as _declaration_name
from vault_graph.project.code.dart_parser import _following_body as _following_body
from vault_graph.project.code.dart_parser import _is_test_name as _is_test_name
from vault_graph.project.code.dart_parser import _map_following_body as _map_following_body
from vault_graph.project.code.dart_parser import _property_declarations as _property_declarations
from vault_graph.project.code.dart_parser import _reference_sort_key as _reference_sort_key
from vault_graph.project.code.dart_parser import _special_method_name as _special_method_name
from vault_graph.project.code.dart_parser import _symbol_sort_key as _symbol_sort_key
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
