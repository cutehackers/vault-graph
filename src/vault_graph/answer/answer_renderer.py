"""Compatibility import for :mod:`vault_graph.context.answer.answer_renderer`."""

import dataclasses as dataclasses
import json as json
import math as math
import sys
from pathlib import Path as Path
from typing import Protocol as Protocol

from vault_graph.context.answer import answer_renderer as _implementation
from vault_graph.context.answer.answer_renderer import AnswerRenderer as AnswerRenderer
from vault_graph.context.answer.answer_renderer import DefaultAnswerRenderer as DefaultAnswerRenderer
from vault_graph.context.answer.answer_renderer import _to_json_value as _to_json_value
from vault_graph.context.answer.answer_renderer import answer_response_to_dict as answer_response_to_dict
from vault_graph.context.answer.answer_response import AnswerClaim as AnswerClaim
from vault_graph.context.answer.answer_response import AnswerDraft as AnswerDraft
from vault_graph.context.answer.answer_response import AnswerEvidence as AnswerEvidence
from vault_graph.context.answer.answer_response import AnswerReasoningStep as AnswerReasoningStep
from vault_graph.context.answer.answer_response import AnswerResponse as AnswerResponse
from vault_graph.context.answer.answer_response import AnswerSignal as AnswerSignal
from vault_graph.context.answer.answer_response import AnswerStoreRevision as AnswerStoreRevision
from vault_graph.context.answer.answer_response import AnswerWarning as AnswerWarning
from vault_graph.errors import AnswerError as AnswerError
from vault_graph.operation.scope.vault_catalog import QueryScope as QueryScope

sys.modules[__name__] = _implementation
