"""Compatibility import for :mod:`vault_graph.project.code.tree_sitter_parsing`."""

import hashlib as hashlib
import sys
from collections.abc import Iterator as Iterator
from typing import Any as Any

from vault_graph.project.code import tree_sitter_parsing as _implementation
from vault_graph.project.code.code_models import CODE_DART_GRAMMAR_PACKAGE_VERSION as CODE_DART_GRAMMAR_PACKAGE_VERSION
from vault_graph.project.code.code_models import CODE_TREE_SITTER_ABI_VERSION as CODE_TREE_SITTER_ABI_VERSION
from vault_graph.project.code.code_models import CODE_TREE_SITTER_PYTHON_VERSION as CODE_TREE_SITTER_PYTHON_VERSION
from vault_graph.project.code.code_models import CODE_TREE_SITTER_RUNTIME_VERSION as CODE_TREE_SITTER_RUNTIME_VERSION
from vault_graph.project.code.code_models import CodeFileInput as CodeFileInput
from vault_graph.project.code.code_models import CodeParseDiagnostic as CodeParseDiagnostic
from vault_graph.project.code.code_models import code_file_identity as code_file_identity
from vault_graph.project.code.tree_sitter_parsing import file_identity as file_identity
from vault_graph.project.code.tree_sitter_parsing import load_language as load_language
from vault_graph.project.code.tree_sitter_parsing import node_end as node_end
from vault_graph.project.code.tree_sitter_parsing import node_start as node_start
from vault_graph.project.code.tree_sitter_parsing import node_text as node_text
from vault_graph.project.code.tree_sitter_parsing import parse_source as parse_source
from vault_graph.project.code.tree_sitter_parsing import parser_dependency_versions as parser_dependency_versions
from vault_graph.project.code.tree_sitter_parsing import source_signature as source_signature
from vault_graph.project.code.tree_sitter_parsing import stable_identity as stable_identity
from vault_graph.project.code.tree_sitter_parsing import syntax_diagnostics as syntax_diagnostics
from vault_graph.project.code.tree_sitter_parsing import unsupported_diagnostics as unsupported_diagnostics
from vault_graph.project.code.tree_sitter_parsing import walk as walk

sys.modules[__name__] = _implementation
