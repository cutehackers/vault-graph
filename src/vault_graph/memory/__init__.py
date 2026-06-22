from __future__ import annotations

from typing import Any

__all__ = [
    "CachedExplanationView",
    "DecisionMemoryService",
    "DecisionMemoryProjection",
    "DecisionMemoryVault",
    "DecisionTraceProvider",
    "ExplainResultService",
    "ExplanationCacheReader",
    "ExplanationEvidenceRef",
    "ExplanationRecord",
    "ExplanationSignal",
    "ExplanationSourceKind",
    "ExplanationWarning",
    "ExplanationWarningSeverity",
    "MemoryBackendRevision",
    "MemoryClaimStatus",
    "MemoryDocumentResourceKind",
    "MemoryEvidenceRef",
    "MemoryFreshness",
    "MemoryRequestContext",
    "MemorySourceReader",
    "MemoryVaultDocuments",
    "MemoryDocumentRead",
    "MemoryHeadingRef",
    "MemoryItem",
    "MemoryItemKind",
    "MemoryWarning",
    "MemoryWarningSeverity",
    "OpenQuestionsProjection",
    "OpenQuestionsVault",
    "IssueMemoryService",
    "ProjectMemoryProjection",
    "ProjectMemoryService",
    "ProjectMemoryVault",
    "build_memory_request_context",
    "document_resource_kinds_for_document",
    "explanation_record_to_dict",
    "stable_memory_item_id",
]


def __getattr__(name: str) -> Any:
    if name in {
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
    }:
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
    if name in {"MemorySourceReader", "MemoryDocumentRead", "MemoryHeadingRef", "document_resource_kinds_for_document"}:
        from vault_graph.memory.memory_source_reader import (
            MemoryDocumentRead,
            MemoryHeadingRef,
            MemorySourceReader,
            document_resource_kinds_for_document,
        )

        return {
            "MemorySourceReader": MemorySourceReader,
            "MemoryDocumentRead": MemoryDocumentRead,
            "MemoryHeadingRef": MemoryHeadingRef,
            "document_resource_kinds_for_document": document_resource_kinds_for_document,
        }[name]
    if name in {"MemoryRequestContext", "MemoryVaultDocuments", "build_memory_request_context"}:
        from vault_graph.memory.memory_request_context import (
            MemoryRequestContext,
            MemoryVaultDocuments,
            build_memory_request_context,
        )

        return {
            "MemoryRequestContext": MemoryRequestContext,
            "MemoryVaultDocuments": MemoryVaultDocuments,
            "build_memory_request_context": build_memory_request_context,
        }[name]
    if name in {"DecisionMemoryService", "DecisionTraceProvider"}:
        from vault_graph.memory.decision_memory import DecisionMemoryService, DecisionTraceProvider

        return {"DecisionMemoryService": DecisionMemoryService, "DecisionTraceProvider": DecisionTraceProvider}[name]
    if name == "IssueMemoryService":
        from vault_graph.memory.issue_memory import IssueMemoryService

        return IssueMemoryService
    if name == "ProjectMemoryService":
        from vault_graph.memory.project_memory import ProjectMemoryService

        return ProjectMemoryService
    if name in {
        "DecisionMemoryProjection",
        "DecisionMemoryVault",
        "MemoryBackendRevision",
        "MemoryClaimStatus",
        "MemoryDocumentResourceKind",
        "MemoryEvidenceRef",
        "MemoryFreshness",
        "MemoryItem",
        "MemoryItemKind",
        "MemoryWarning",
        "MemoryWarningSeverity",
        "OpenQuestionsProjection",
        "OpenQuestionsVault",
        "ProjectMemoryProjection",
        "ProjectMemoryVault",
        "stable_memory_item_id",
    }:
        from vault_graph.memory.memory_models import (
            DecisionMemoryProjection,
            DecisionMemoryVault,
            MemoryBackendRevision,
            MemoryClaimStatus,
            MemoryDocumentResourceKind,
            MemoryEvidenceRef,
            MemoryFreshness,
            MemoryItem,
            MemoryItemKind,
            MemoryWarning,
            MemoryWarningSeverity,
            OpenQuestionsProjection,
            OpenQuestionsVault,
            ProjectMemoryProjection,
            ProjectMemoryVault,
            stable_memory_item_id,
        )

        return {
            "DecisionMemoryProjection": DecisionMemoryProjection,
            "DecisionMemoryVault": DecisionMemoryVault,
            "MemoryBackendRevision": MemoryBackendRevision,
            "MemoryClaimStatus": MemoryClaimStatus,
            "MemoryDocumentResourceKind": MemoryDocumentResourceKind,
            "MemoryEvidenceRef": MemoryEvidenceRef,
            "MemoryFreshness": MemoryFreshness,
            "MemoryItem": MemoryItem,
            "MemoryItemKind": MemoryItemKind,
            "MemoryWarning": MemoryWarning,
            "MemoryWarningSeverity": MemoryWarningSeverity,
            "OpenQuestionsProjection": OpenQuestionsProjection,
            "OpenQuestionsVault": OpenQuestionsVault,
            "ProjectMemoryProjection": ProjectMemoryProjection,
            "ProjectMemoryVault": ProjectMemoryVault,
            "stable_memory_item_id": stable_memory_item_id,
        }[name]
    raise AttributeError(name)


def __dir__() -> list[str]:
    return sorted(__all__)
