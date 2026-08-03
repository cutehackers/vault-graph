"""Composition root for code indexing application services."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from vault_graph.app.catalog_service import CatalogService
from vault_graph.code_index.code_freshness import CodeFreshnessService
from vault_graph.code_index.code_generation import CodeProjectionGenerationManager
from vault_graph.code_index.code_models import CODE_PARSER_SPEC_VERSION
from vault_graph.code_index.code_projection_service import CodeProjectionService
from vault_graph.code_index.dart_parser import DartCodeParserAdapter
from vault_graph.code_index.python_parser import PythonCodeParserAdapter
from vault_graph.code_index.reference_resolution import CodeReferenceResolver
from vault_graph.code_index.repository_catalog import CodeRepositoryCatalogService
from vault_graph.code_index.source_scanning import CodeSourceScanner


@dataclass(frozen=True)
class CodeIndexServices:
    """Ready-to-use services; concrete SQLite construction stays here."""

    catalog_service: CatalogService
    repository_catalog: object
    scanner: CodeSourceScanner
    resolver: CodeReferenceResolver
    generation_manager: CodeProjectionGenerationManager
    projection_service: CodeProjectionService
    freshness_service: CodeFreshnessService


class CodeIndexFactory:
    """Build the code application graph for CLI, MCP, and tests."""

    def __init__(self, *, state_path: Path) -> None:
        self.state_path = state_path.expanduser().resolve()

    def open(self) -> CodeIndexServices:
        catalog_service = CatalogService(state_path=self.state_path)
        repository_catalog = CodeRepositoryCatalogService(catalog_service=catalog_service).load()
        scanner = CodeSourceScanner(parser_spec_version=CODE_PARSER_SPEC_VERSION)
        resolver = CodeReferenceResolver(parser_spec_version=CODE_PARSER_SPEC_VERSION)
        generation_manager = CodeProjectionGenerationManager(catalog_service.state_path)
        projection_service = CodeProjectionService(
            catalog=repository_catalog,
            scanner=scanner,
            parsers={"python": PythonCodeParserAdapter(), "dart": DartCodeParserAdapter()},
            resolver=resolver,
            generation_manager=generation_manager,
        )
        freshness_service = CodeFreshnessService(
            catalog=repository_catalog,
            scanner=scanner,
            generation_manager=generation_manager,
            parser_spec_version=CODE_PARSER_SPEC_VERSION,
        )
        return CodeIndexServices(
            catalog_service=catalog_service,
            repository_catalog=repository_catalog,
            scanner=scanner,
            resolver=resolver,
            generation_manager=generation_manager,
            projection_service=projection_service,
            freshness_service=freshness_service,
        )

    def open_projection_service(self) -> CodeProjectionService:
        return self.open().projection_service

    def open_freshness_service(self) -> CodeFreshnessService:
        return self.open().freshness_service


CodeIndexServiceFactory = CodeIndexFactory


__all__ = ["CodeIndexFactory", "CodeIndexServiceFactory", "CodeIndexServices"]
