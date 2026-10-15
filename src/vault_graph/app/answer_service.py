"""Compatibility import for :mod:`vault_graph.context.answer.answer_service`."""

import sys

from vault_graph.context.answer import answer_service as _implementation
from vault_graph.context.answer.answer_service import AnswerEvidencePlanner as AnswerEvidencePlanner
from vault_graph.context.answer.answer_service import AnswerService as AnswerService

sys.modules[__name__] = _implementation
