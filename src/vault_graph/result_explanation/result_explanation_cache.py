"""Compatibility import for :mod:`vault_graph.retrieval.explanation.result_explanation_cache`."""

import sys
from collections import OrderedDict as OrderedDict
from collections.abc import Callable as Callable
from dataclasses import dataclass as dataclass
from datetime import UTC as UTC
from datetime import datetime as datetime

from vault_graph.errors import ResultExplanationError as ResultExplanationError
from vault_graph.retrieval.explanation import result_explanation_cache as _implementation
from vault_graph.retrieval.explanation.result_explanation import CachedExplanationView as CachedExplanationView
from vault_graph.retrieval.explanation.result_explanation import ExplanationRecord as ExplanationRecord
from vault_graph.retrieval.explanation.result_explanation_cache import CachedExplanation as CachedExplanation
from vault_graph.retrieval.explanation.result_explanation_cache import ResultExplanationCache as ResultExplanationCache
from vault_graph.retrieval.explanation.result_explanation_cache import _utc_isoformat as _utc_isoformat

sys.modules[__name__] = _implementation
