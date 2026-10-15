"""Compatibility import for :mod:`vault_graph.answer.answer_service`."""

import sys

from vault_graph.answer import answer_service as _implementation
from vault_graph.answer.answer_service import AnswerEvidencePlanner as AnswerEvidencePlanner
from vault_graph.answer.answer_service import AnswerService as AnswerService

# Preserve historical module patch targets as well as class identities.
sys.modules[__name__] = _implementation
