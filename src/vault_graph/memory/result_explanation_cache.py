"""Compatibility import for :mod:`vault_graph.retrieval.explanation.result_explanation_cache`."""

import sys

from vault_graph.retrieval.explanation import result_explanation_cache as _implementation
from vault_graph.retrieval.explanation.result_explanation_cache import CachedExplanation as CachedExplanation
from vault_graph.retrieval.explanation.result_explanation_cache import ResultExplanationCache as ResultExplanationCache

sys.modules[__name__] = _implementation
