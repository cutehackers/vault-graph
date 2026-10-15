"""Compatibility import for :mod:`vault_graph.project.code.parser_adapter`."""

import sys
from typing import Protocol as Protocol

from vault_graph.project.code import parser_adapter as _implementation
from vault_graph.project.code.code_models import CodeFileInput as CodeFileInput
from vault_graph.project.code.code_models import CodeParseResult as CodeParseResult
from vault_graph.project.code.parser_adapter import CodeParserAdapter as CodeParserAdapter

sys.modules[__name__] = _implementation
