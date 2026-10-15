"""Compatibility import for :mod:`vault_graph.context.answer.citation_guard`."""

import sys
from dataclasses import replace as replace

from vault_graph.context.answer import citation_guard as _implementation
from vault_graph.context.answer.answer_response import AnswerResponse as AnswerResponse
from vault_graph.context.answer.citation_guard import CitationGuard as CitationGuard
from vault_graph.context.answer.citation_guard import _unique as _unique
from vault_graph.errors import AnswerError as AnswerError

sys.modules[__name__] = _implementation
