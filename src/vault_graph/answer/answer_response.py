"""Compatibility import for :mod:`vault_graph.context.answer.answer_response`."""

import sys
from dataclasses import dataclass as dataclass
from typing import Literal as Literal

from vault_graph.context.answer import answer_response as _implementation
from vault_graph.context.answer.answer_response import AnswerClaim as AnswerClaim
from vault_graph.context.answer.answer_response import AnswerClaimStatus as AnswerClaimStatus
from vault_graph.context.answer.answer_response import AnswerDraft as AnswerDraft
from vault_graph.context.answer.answer_response import AnswerEvidence as AnswerEvidence
from vault_graph.context.answer.answer_response import AnswerEvidenceSourceKind as AnswerEvidenceSourceKind
from vault_graph.context.answer.answer_response import AnswerMode as AnswerMode
from vault_graph.context.answer.answer_response import AnswerReasoningStep as AnswerReasoningStep
from vault_graph.context.answer.answer_response import AnswerResponse as AnswerResponse
from vault_graph.context.answer.answer_response import AnswerSignal as AnswerSignal
from vault_graph.context.answer.answer_response import AnswerStatus as AnswerStatus
from vault_graph.context.answer.answer_response import AnswerStoreRevision as AnswerStoreRevision
from vault_graph.context.answer.answer_response import AnswerWarning as AnswerWarning
from vault_graph.context.answer.answer_response import AnswerWarningSeverity as AnswerWarningSeverity
from vault_graph.context.answer.answer_response import _require_non_empty as _require_non_empty
from vault_graph.context.answer.answer_response import _require_tuple as _require_tuple
from vault_graph.context.answer.answer_response import _unique_ids as _unique_ids
from vault_graph.errors import AnswerError as AnswerError
from vault_graph.operation.scope.vault_catalog import QueryScope as QueryScope

sys.modules[__name__] = _implementation
