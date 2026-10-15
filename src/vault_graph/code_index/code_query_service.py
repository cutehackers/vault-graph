"""Compatibility import for :mod:`vault_graph.project.code.code_query_service`."""

import sys
from collections.abc import Iterable as Iterable
from typing import Protocol as Protocol
from typing import cast as cast

from vault_graph.project.code import code_query_service as _implementation
from vault_graph.project.code.code_models import CodeFileOutlineRequest as CodeFileOutlineRequest
from vault_graph.project.code.code_models import CodeFileOutlineResponse as CodeFileOutlineResponse
from vault_graph.project.code.code_models import CodeFreshnessReport as CodeFreshnessReport
from vault_graph.project.code.code_models import CodeImpactRequest as CodeImpactRequest
from vault_graph.project.code.code_models import CodeRepositoryEntry as CodeRepositoryEntry
from vault_graph.project.code.code_models import CodeSearchResponse as CodeSearchResponse
from vault_graph.project.code.code_models import CodeSymbolQuery as CodeSymbolQuery
from vault_graph.project.code.code_models import CodeSymbolRecord as CodeSymbolRecord
from vault_graph.project.code.code_models import CodeSymbolRequest as CodeSymbolRequest
from vault_graph.project.code.code_models import CodeSymbolResponse as CodeSymbolResponse
from vault_graph.project.code.code_models import CodeSymbolSearchRequest as CodeSymbolSearchRequest
from vault_graph.project.code.code_models import CodeTraversalDirection as CodeTraversalDirection
from vault_graph.project.code.code_models import CodeTraversalQuery as CodeTraversalQuery
from vault_graph.project.code.code_models import CodeTraversalRequest as CodeTraversalRequest
from vault_graph.project.code.code_models import CodeTraversalResponse as CodeTraversalResponse
from vault_graph.project.code.code_models import code_file_identity as code_file_identity
from vault_graph.project.code.code_query_service import MAX_QUERY_LIMIT as MAX_QUERY_LIMIT
from vault_graph.project.code.code_query_service import MAX_TRAVERSAL_DEPTH as MAX_TRAVERSAL_DEPTH
from vault_graph.project.code.code_query_service import CodeFreshnessReader as CodeFreshnessReader
from vault_graph.project.code.code_query_service import CodeProjectionStatusReader as CodeProjectionStatusReader
from vault_graph.project.code.code_query_service import CodeQueryService as CodeQueryService
from vault_graph.project.code.repository_catalog import CodeRepositoryCatalog as CodeRepositoryCatalog
from vault_graph.project.code.source_evidence_reader import SourceEvidenceReader as SourceEvidenceReader
from vault_graph.storage.interfaces.code_projection_store import CodeProjectionStore as CodeProjectionStore

sys.modules[__name__] = _implementation
