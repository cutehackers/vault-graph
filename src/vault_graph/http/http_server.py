"""Compatibility import for :mod:`vault_graph.interface.http.http_server`."""

import sys
from typing import TYPE_CHECKING as TYPE_CHECKING

from vault_graph.context.answer.answer_plan import AnswerRequest as AnswerRequest
from vault_graph.context.pack.context_pack import ContextPackBudget as ContextPackBudget
from vault_graph.context.pack.context_pack import ContextPackRequest as ContextPackRequest
from vault_graph.interface.http import http_server as _implementation
from vault_graph.interface.http.http_errors import HttpRequestError as HttpRequestError
from vault_graph.interface.http.http_errors import HttpServerConfig as HttpServerConfig
from vault_graph.interface.http.http_errors import map_exception_to_http_error as map_exception_to_http_error
from vault_graph.interface.http.http_explanation_serialization import (
    explanation_records_for_answer as explanation_records_for_answer,
)
from vault_graph.interface.http.http_explanation_serialization import (
    explanation_records_for_context_pack as explanation_records_for_context_pack,
)
from vault_graph.interface.http.http_explanation_serialization import (
    explanation_records_for_decision_trace as explanation_records_for_decision_trace,
)
from vault_graph.interface.http.http_explanation_serialization import (
    explanation_records_for_related as explanation_records_for_related,
)
from vault_graph.interface.http.http_explanation_serialization import (
    explanation_records_for_search as explanation_records_for_search,
)
from vault_graph.interface.http.http_serialization import domain_to_json_dict as domain_to_json_dict
from vault_graph.interface.http.http_server import _bool as _bool
from vault_graph.interface.http.http_server import _limit as _limit
from vault_graph.interface.http.http_server import _positive_int as _positive_int
from vault_graph.interface.http.http_server import _required_string as _required_string
from vault_graph.interface.http.http_server import _result_id as _result_id
from vault_graph.interface.http.http_server import _scope_from_payload as _scope_from_payload
from vault_graph.interface.http.http_server import _string_list as _string_list
from vault_graph.interface.http.http_server import create_http_app as create_http_app
from vault_graph.interface.http.http_server import run_http_server as run_http_server
from vault_graph.interface.http.http_service_factory import HttpServiceFactory as HttpServiceFactory
from vault_graph.operation.scope.vault_catalog import QueryScope as QueryScope
from vault_graph.operation.scope.vault_catalog import VaultCatalog as VaultCatalog
from vault_graph.retrieval.explanation.result_explanation import ExplainResultService as ExplainResultService
from vault_graph.retrieval.explanation.result_explanation import (
    explanation_record_to_dict as explanation_record_to_dict,
)
from vault_graph.retrieval.explanation.result_explanation_cache import ResultExplanationCache as ResultExplanationCache

sys.modules[__name__] = _implementation
