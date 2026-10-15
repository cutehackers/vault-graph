"""Compatibility import for :mod:`vault_graph.retrieval.explanation.result_explanation`."""

import sys
from dataclasses import dataclass as dataclass
from typing import Literal as Literal
from typing import Protocol as Protocol

from vault_graph.errors import ResultExplanationError as ResultExplanationError
from vault_graph.retrieval.explanation import result_explanation as _implementation
from vault_graph.retrieval.explanation.result_explanation import CachedExplanationView as CachedExplanationView
from vault_graph.retrieval.explanation.result_explanation import ExplainResultService as ExplainResultService
from vault_graph.retrieval.explanation.result_explanation import ExplanationCacheReader as ExplanationCacheReader
from vault_graph.retrieval.explanation.result_explanation import ExplanationEvidenceRef as ExplanationEvidenceRef
from vault_graph.retrieval.explanation.result_explanation import ExplanationRecord as ExplanationRecord
from vault_graph.retrieval.explanation.result_explanation import ExplanationSignal as ExplanationSignal
from vault_graph.retrieval.explanation.result_explanation import ExplanationSourceKind as ExplanationSourceKind
from vault_graph.retrieval.explanation.result_explanation import ExplanationWarning as ExplanationWarning
from vault_graph.retrieval.explanation.result_explanation import (
    ExplanationWarningSeverity as ExplanationWarningSeverity,
)
from vault_graph.retrieval.explanation.result_explanation import _evidence_ref_to_dict as _evidence_ref_to_dict
from vault_graph.retrieval.explanation.result_explanation import _require_non_empty as _require_non_empty
from vault_graph.retrieval.explanation.result_explanation import _require_tuple as _require_tuple
from vault_graph.retrieval.explanation.result_explanation import _signal_to_dict as _signal_to_dict
from vault_graph.retrieval.explanation.result_explanation import (
    _validate_json_safe_mapping as _validate_json_safe_mapping,
)
from vault_graph.retrieval.explanation.result_explanation import _validate_json_safe_value as _validate_json_safe_value
from vault_graph.retrieval.explanation.result_explanation import _validate_resource_link as _validate_resource_link
from vault_graph.retrieval.explanation.result_explanation import _warning_to_dict as _warning_to_dict
from vault_graph.retrieval.explanation.result_explanation import (
    explanation_record_to_dict as explanation_record_to_dict,
)

sys.modules[__name__] = _implementation
