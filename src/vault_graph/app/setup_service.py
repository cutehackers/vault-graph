from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from vault_graph.app.catalog_service import CatalogService
from vault_graph.app.graph_home import GraphHomeResolver
from vault_graph.app.index_service import IndexRunReport
from vault_graph.app.local_index_service_factory import LocalIndexServiceFactory
from vault_graph.errors import CatalogError, SetupError
from vault_graph.harness.harness_guidance import HarnessGuidanceReport, HarnessGuidanceRequest, HarnessGuidanceService
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
    graph_home_path: Path
    vault_id: str = "default"
    agent: McpAgent | None = None
    register_mcp: bool = False
    mcp_config_path: Path | None = None
    print_mcp_config: bool = False
    dry_run: bool = False


@dataclass(frozen=True)
class SetupReport:
    graph_home_path: Path
    vault_id: str
    vault_path: Path
    created_catalog: bool
    indexed: bool
    dry_run: bool
    index_report: IndexRunReport | None
    mcp_config: str | None
    mcp_registration: McpRegistrationReport | None
    warnings: tuple[str, ...]
    ready: bool = False
    recovery_hint: str | None = None


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

    def manage_harness_guidance(
        self,
        *,
        action: str,
        request: HarnessGuidanceRequest,
        vault_roots: tuple[Path, ...],
    ) -> HarnessGuidanceReport:
        """Run an explicit instruction-file change without changing setup defaults."""

        service = HarnessGuidanceService(vault_roots=vault_roots)
        if action == "install":
            return service.install(request)
        if action == "remove":
            return service.remove(request)
        if action == "preview":
            return service.preview(request)
        raise SetupError("unsupported_harness_guidance_action")

    def setup(self, request: SetupRequest) -> SetupReport:
        resolver = GraphHomeResolver()
        descriptor = resolver.resolve(request.graph_home_path)
        if descriptor.legacy:
            # A pre-release Data Home is derived state, not a compatibility
            # contract. Refuse to interpret it even during dry-run so preview
            # and execution cannot disagree about the onboarding path.
            resolver.require_initialized(request.graph_home_path)
        if not request.dry_run:
            descriptor = resolver.initialize(request.graph_home_path, vault_roots=(request.vault_path,))
        catalog_service = CatalogService(graph_home_path=descriptor.root_path)
        vault_entry = VaultCatalogEntry.from_root(vault_id=request.vault_id, root_path=request.vault_path)
        catalog, created_catalog = self._ensure_catalog(
            catalog_service=catalog_service,
            vault_entry=vault_entry,
            dry_run=request.dry_run,
        )
        scope = catalog.scope_for_vault_ids([request.vault_id])
        index_report = None
        if not request.dry_run:
            bundle = self._index_factory.open(
                graph_home_path=request.graph_home_path,
                initialize_store=True,
                transactional=True,
                full=False,
            )
            try:
                index_report = bundle.index_service.run_apply(scope=scope, full=False)
                if index_report.exit_code == 0:
                    commit_projection = getattr(bundle, "commit_projection", None)
                    if commit_projection is not None:
                        commit_projection(index_report)
            finally:
                bundle.close()
        mcp_config = None
        mcp_registration = None
        warnings: list[str] = []
        if request.agent is not None:
            config_request = McpConfigRequest(agent=request.agent, graph_home_path=request.graph_home_path)
            actual_mcp_config_path = request.mcp_config_path
            if request.register_mcp and actual_mcp_config_path is None:
                actual_mcp_config_path = self._mcp_registrar.default_config_path(request.agent)
            if request.print_mcp_config or (actual_mcp_config_path is None and not request.register_mcp):
                mcp_config = self._mcp_renderer.render(config_request)
            index_ready = request.dry_run or index_report is None or index_report.exit_code == 0
            if actual_mcp_config_path is not None and index_ready:
                mcp_registration = self._mcp_registrar.register(
                    McpRegistrationRequest(
                        agent=request.agent,
                        graph_home_path=request.graph_home_path,
                        config_path=actual_mcp_config_path,
                        dry_run=request.dry_run,
                    )
                )
            elif actual_mcp_config_path is not None:
                warnings.append("mcp_registration_skipped_index_failed")
            elif not request.print_mcp_config:
                warnings.append("mcp_config_not_written")
        return SetupReport(
            graph_home_path=catalog_service.graph_home_path,
            vault_id=request.vault_id,
            vault_path=vault_entry.root_path,
            created_catalog=created_catalog,
            indexed=index_report is not None,
            dry_run=request.dry_run,
            index_report=index_report,
            mcp_config=mcp_config,
            mcp_registration=mcp_registration,
            warnings=tuple(warnings),
            ready=not request.dry_run and index_report is not None and index_report.exit_code == 0,
            recovery_hint=_setup_recovery_hint(
                request=request,
                index_report=index_report,
                mcp_registration=mcp_registration,
            ),
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
            catalog_service.assert_graph_home_safe(catalog)
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


def _setup_recovery_hint(
    *,
    request: SetupRequest,
    index_report: IndexRunReport | None,
    mcp_registration: McpRegistrationReport | None,
) -> str | None:
    if request.dry_run:
        return "run setup without --dry-run to initialize the Data Home and publish the baseline projection"
    if index_report is not None and index_report.exit_code != 0:
        return f"run `vg status --graph-home {request.graph_home_path}` and retry `vg index --full`"
    if request.register_mcp and mcp_registration is None:
        return "provide --mcp-config-path or use --print-mcp-config to complete MCP registration"
    return None
