"""Compatibility import for :mod:`vault_graph.context.answer.answer_plan`."""

import hashlib as hashlib
import json as json
import sys
from dataclasses import dataclass as dataclass

from vault_graph.context.answer import answer_plan as _implementation
from vault_graph.context.answer.answer_plan import AnswerPlan as AnswerPlan
from vault_graph.context.answer.answer_plan import AnswerRequest as AnswerRequest
from vault_graph.context.answer.answer_plan import EvidencePlanStep as EvidencePlanStep
from vault_graph.context.answer.answer_plan import PlannedEvidence as PlannedEvidence
from vault_graph.context.answer.answer_plan import answer_id_for as answer_id_for
from vault_graph.context.answer.answer_response import AnswerEvidence as AnswerEvidence
from vault_graph.context.answer.answer_response import AnswerMode as AnswerMode
from vault_graph.context.answer.answer_response import AnswerReasoningStep as AnswerReasoningStep
from vault_graph.context.answer.answer_response import AnswerWarning as AnswerWarning
from vault_graph.errors import AnswerError as AnswerError
from vault_graph.operation.scope.vault_catalog import QueryScope as QueryScope

sys.modules[__name__] = _implementation
