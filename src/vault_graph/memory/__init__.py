from __future__ import annotations

from typing import Any

__all__ = [
    "CachedExplanationView",
    "ExplainResultService",
    "ExplanationCacheReader",
    "ExplanationEvidenceRef",
    "ExplanationRecord",
    "ExplanationSignal",
    "ExplanationSourceKind",
    "ExplanationWarning",
    "ExplanationWarningSeverity",
    "explanation_record_to_dict",
]


def __getattr__(name: str) -> Any:
    if name in __all__:
        from vault_graph.memory.result_explanation import (
            CachedExplanationView,
            ExplainResultService,
            ExplanationCacheReader,
            ExplanationEvidenceRef,
            ExplanationRecord,
            ExplanationSignal,
            ExplanationSourceKind,
            ExplanationWarning,
            ExplanationWarningSeverity,
            explanation_record_to_dict,
        )

        return {
            "CachedExplanationView": CachedExplanationView,
            "ExplainResultService": ExplainResultService,
            "ExplanationCacheReader": ExplanationCacheReader,
            "ExplanationEvidenceRef": ExplanationEvidenceRef,
            "ExplanationRecord": ExplanationRecord,
            "ExplanationSignal": ExplanationSignal,
            "ExplanationSourceKind": ExplanationSourceKind,
            "ExplanationWarning": ExplanationWarning,
            "ExplanationWarningSeverity": ExplanationWarningSeverity,
            "explanation_record_to_dict": explanation_record_to_dict,
        }[name]
    raise AttributeError(name)


def __dir__() -> list[str]:
    return sorted(__all__)
