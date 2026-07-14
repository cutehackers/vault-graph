from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from vault_graph.app.catalog_service import CatalogService
from vault_graph.app.index_service import IndexRunReport
from vault_graph.app.local_index_service_factory import LocalIndexServiceFactory
from vault_graph.errors import CatalogError, SetupError
from vault_graph.ingestion.vault_catalog import VaultCatalog, VaultCatalogEntry
from vault_graph.mcp.mcp_config_registration import (
    McpAgent,
    McpConfigRegistrar,
    McpConfigRenderer,
    McpConfigRequest,
    McpRegistrationReport,
    McpRegistrationRequest,
)


@dataclass(frozen=True)
class SetupRequest:
    vault_path: Path
    state_path: Path
    vault_id: str = "default"
    agent: McpAgent | None = None
    register_mcp: bool = False
    mcp_config_path: Path | None = None
    print_mcp_config: bool = False
    dry_run: bool = False


@dataclass(frozen=True)
class SetupReport:
    state_path: Path
    vault_id: str
    vault_path: Path
    created_catalog: bool
    indexed: bool
    dry_run: bool
    index_report: IndexRunReport | None
    mcp_config: str | None
    mcp_registration: McpRegistrationReport | None
    warnings: tuple[str, ...]


class SetupService:
    def __init__(
        self,
        *,
        index_factory: LocalIndexServiceFactory | None = None,
        mcp_renderer: McpConfigRenderer | None = None,
        mcp_registrar: McpConfigRegistrar | None = None,
    ) -> None:
        self._index_factory = index_factory or LocalIndexServiceFactory()
        self._mcp_renderer = mcp_renderer or McpConfigRenderer()
        self._mcp_registrar = mcp_registrar or McpConfigRegistrar(renderer=self._mcp_renderer)

    def setup(self, request: SetupRequest) -> SetupReport:
        catalog_service = CatalogService(state_path=request.state_path)
        vault_entry = VaultCatalogEntry.from_root(vault_id=request.vault_id, root_path=request.vault_path)
        catalog, created_catalog = self._ensure_catalog(
            catalog_service=catalog_service,
            vault_entry=vault_entry,
            dry_run=request.dry_run,
        )
        scope = catalog.scope_for_vault_ids([request.vault_id])
        index_report = None
        if not request.dry_run:
            bundle = self._index_factory.open(state_path=request.state_path, initialize_store=True)
            try:
                index_report = bundle.index_service.run_apply(scope=scope, full=False)
            finally:
                bundle.close()
        mcp_config = None
        mcp_registration = None
        warnings: list[str] = []
        if request.agent is not None:
            config_request = McpConfigRequest(agent=request.agent, state_path=request.state_path)
            actual_mcp_config_path = request.mcp_config_path
            if request.register_mcp and actual_mcp_config_path is None:
                actual_mcp_config_path = self._mcp_registrar.default_config_path(request.agent)
            if request.print_mcp_config or (actual_mcp_config_path is None and not request.register_mcp):
                mcp_config = self._mcp_renderer.render(config_request)
            if actual_mcp_config_path is not None:
                mcp_registration = self._mcp_registrar.register(
                    McpRegistrationRequest(
                        agent=request.agent,
                        state_path=request.state_path,
                        config_path=actual_mcp_config_path,
                        dry_run=request.dry_run,
                    )
                )
            elif not request.print_mcp_config:
                warnings.append("mcp_config_not_written")
        return SetupReport(
            state_path=catalog_service.state_path,
            vault_id=request.vault_id,
            vault_path=vault_entry.root_path,
            created_catalog=created_catalog,
            indexed=index_report is not None,
            dry_run=request.dry_run,
            index_report=index_report,
            mcp_config=mcp_config,
            mcp_registration=mcp_registration,
            warnings=tuple(warnings),
        )

    def _ensure_catalog(
        self,
        *,
        catalog_service: CatalogService,
        vault_entry: VaultCatalogEntry,
        dry_run: bool,
    ) -> tuple[VaultCatalog, bool]:
        if not catalog_service.config_path.exists():
            catalog = VaultCatalog.from_entries(entries=(vault_entry,), active_vault_id=vault_entry.vault_id)
            catalog_service.assert_state_safe(catalog)
            if not dry_run:
                catalog_service.save_catalog(catalog)
            return catalog, True
        try:
            catalog = catalog_service.load_catalog()
        except CatalogError as exc:
            raise SetupError(str(exc)) from exc
        existing = tuple(entry for entry in catalog.entries() if entry.vault_id == vault_entry.vault_id)
        if not existing:
            raise SetupError("setup_vault_id_missing: existing catalog does not contain requested vault_id")
        if existing[0].root_path != vault_entry.root_path:
            raise SetupError("setup_vault_id_conflict: existing vault_id points to a different root")
        return catalog, False
