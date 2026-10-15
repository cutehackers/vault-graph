"""Compatibility import for :mod:`vault_graph.context.answer.answer_composer`."""

import sys
from typing import Protocol as Protocol

from vault_graph.context.answer import answer_composer as _implementation
from vault_graph.context.answer.answer_composer import AnswerComposer as AnswerComposer
from vault_graph.context.answer.answer_composer import ExtractiveAnswerComposer as ExtractiveAnswerComposer
from vault_graph.context.answer.answer_composer import _claim_status_for_evidence as _claim_status_for_evidence
from vault_graph.context.answer.answer_plan import AnswerRequest as AnswerRequest
from vault_graph.context.answer.answer_plan import PlannedEvidence as PlannedEvidence
from vault_graph.context.answer.answer_response import AnswerClaim as AnswerClaim
from vault_graph.context.answer.answer_response import AnswerClaimStatus as AnswerClaimStatus
from vault_graph.context.answer.answer_response import AnswerDraft as AnswerDraft
from vault_graph.context.answer.answer_response import AnswerStatus as AnswerStatus

sys.modules[__name__] = _implementation
