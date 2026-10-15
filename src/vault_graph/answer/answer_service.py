"""Compatibility import for :mod:`vault_graph.context.answer.answer_service`."""

import sys
from collections.abc import Callable as Callable
from datetime import UTC as UTC
from datetime import datetime as datetime
from typing import Protocol as Protocol

from vault_graph.context.answer import answer_service as _implementation
from vault_graph.context.answer.answer_composer import AnswerComposer as AnswerComposer
from vault_graph.context.answer.answer_plan import AnswerPlan as AnswerPlan
from vault_graph.context.answer.answer_plan import AnswerRequest as AnswerRequest
from vault_graph.context.answer.answer_plan import PlannedEvidence as PlannedEvidence
from vault_graph.context.answer.answer_plan import answer_id_for as answer_id_for
from vault_graph.context.answer.answer_response import AnswerResponse as AnswerResponse
from vault_graph.context.answer.answer_service import AnswerEvidencePlanner as AnswerEvidencePlanner
from vault_graph.context.answer.answer_service import AnswerService as AnswerService
from vault_graph.context.answer.answer_service import _utc_isoformat as _utc_isoformat
from vault_graph.context.answer.citation_guard import CitationGuard as CitationGuard

sys.modules[__name__] = _implementation
