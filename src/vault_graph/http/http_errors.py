"""Compatibility import for :mod:`vault_graph.interface.http.http_errors`."""

import sys
from dataclasses import dataclass as dataclass
from pathlib import Path as Path

from vault_graph.errors import DataHomeManifestError as DataHomeManifestError
from vault_graph.errors import DataHomeNotInitializedError as DataHomeNotInitializedError
from vault_graph.errors import LegacyDataHomeDetectedError as LegacyDataHomeDetectedError
from vault_graph.errors import ResultExplanationError as ResultExplanationError
from vault_graph.errors import VaultGraphError as VaultGraphError
from vault_graph.interface.http import http_errors as _implementation
from vault_graph.interface.http.http_errors import HttpErrorPayload as HttpErrorPayload
from vault_graph.interface.http.http_errors import HttpRequestError as HttpRequestError
from vault_graph.interface.http.http_errors import HttpServerConfig as HttpServerConfig
from vault_graph.interface.http.http_errors import _map_result_explanation_error as _map_result_explanation_error
from vault_graph.interface.http.http_errors import _prefixed_domain_code as _prefixed_domain_code
from vault_graph.interface.http.http_errors import _snake_case_error_code as _snake_case_error_code
from vault_graph.interface.http.http_errors import map_exception_to_http_error as map_exception_to_http_error

sys.modules[__name__] = _implementation
