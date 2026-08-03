"""Deterministic integration benchmark for the project-context MCP entry point.

The benchmark measures orchestration work rather than wall-clock time. It
creates a real local code catalog, code projection, project binding, and
ProjectContextService for every scenario; no LLM or network service is used.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import pytest
import yaml

from vault_graph.app.catalog_service import CatalogService
from vault_graph.app.code_index_factory import CodeIndexFactory
from vault_graph.code_index.code_models import (
    CodeFreshnessRequest,
    CodeImpactRequest,
    CodeIndexRequest,
    CodeSymbolSearchRequest,
)
from vault_graph.context import (
    CONTEXT_PACK_SCHEMA_VERSION,
    ContextEvidence,
    ContextEvidenceRef,
    ContextPack,
    ContextPackBackend,
    ContextPackBackendUse,
    ContextPackBudget,
    ContextPackRequest,
    ContextPackStoreRevision,
    ContextPackVault,
    ContextPackVaultRevision,
    context_scope_from_query_scopes,
)
from vault_graph.mcp.context_pack_resource_cache import ContextPackResourceCache
from vault_graph.mcp.mcp_tools import ExploreProjectInput, McpToolRegistry
from vault_graph.mcp.result_explanation_cache import ResultExplanationCache
from vault_graph.project_context import ProjectAuthorityFreshness, ProjectContextRequest
from vault_graph.project_context.project_binding_catalog import ProjectBindingCatalogService
from vault_graph.project_context.project_context_service import ProjectContextService

FIXTURE_ROOT = Path(__file__).parents[1] / "fixtures" / "project_context"
MAX_TOKENS = 1200
VAULT_EVIDENCE_ID = "vault:project-vault:pricing-decision:chunk-1"


@dataclass(frozen=True)
class Scenario:
    name: str
    task: str
    baseline_tools: tuple[str, ...]
    baseline_instructions: tuple[str, ...]
    depth: int = 2
    limit: int = 20
    requires_source_drift_warning: bool = False


@dataclass(frozen=True)
class BenchmarkResult:
    application_tool_calls: int
    prompt_instruction_tokens: int
    fallback_reads: int
    relevant_evidence_recall: float
    stale_result_misses: int
    output_tokens: int
    evidence_ids: frozenset[str]


SCENARIOS = (
    Scenario(
        "structure",
        "calculate_total",
        ("code.search", "code.symbol", "code.outline", "vault.search"),
        (
            "Search code symbols for calculate_total.",
            "Open selected symbols and current source lines.",
            "Inspect the source-file outline.",
            "Search Vault decisions for the calculation boundary.",
        ),
        depth=1,
        limit=1,
    ),
    Scenario(
        "bug_scope",
        "calculate_total",
        ("code.search", "code.symbol", "code.callers", "code.status", "vault.search"),
        (
            "Search calculate_total.",
            "Read selected source lines.",
            "Find callers and related tests.",
            "Verify code-index freshness.",
            "Find the durable pricing decision.",
        ),
        depth=2,
        limit=2,
        requires_source_drift_warning=True,
    ),
    Scenario(
        "impact",
        "calculate_total",
        ("code.symbol", "code.callers", "code.callees", "code.impact", "vault.search"),
        (
            "Resolve calculate_total.",
            "Traverse callers.",
            "Traverse callees.",
            "Collect impacted tests.",
            "Find the matching Vault constraint.",
        ),
        depth=1,
        limit=1,
    ),
    Scenario(
        "consistency",
        "formatTotal",
        ("vault.context", "vault.decision_trace", "vault.related", "code.search", "code.symbol"),
        (
            "Build Vault context for the pricing decision.",
            "Trace decision evidence.",
            "Find related design entities.",
            "Search the Dart implementation.",
            "Read the selected current source evidence.",
        ),
        depth=0,
        limit=1,
    ),
)


@dataclass(frozen=True)
class _Runtime:
    state_path: Path
    repository_path: Path
    vault_path: Path
    code_factory: CodeIndexFactory
    project_context_service: ProjectContextService
    code_indexed: bool


class _FixtureVaultContextPackBuilder:
    """Protocol adapter that reads the copied Vault fixture for every request."""

    def __init__(self, vault_path: Path) -> None:
        self._vault_path = vault_path
        self.requests: list[ContextPackRequest] = []

    def build(self, request: ContextPackRequest) -> ContextPack:
        self.requests.append(request)
        source_path = self._vault_path / "wiki" / "pricing-decision.md"
        source = source_path.read_text(encoding="utf-8")
        content_hash = hashlib.sha256(source.encode("utf-8")).hexdigest()
        scope = request.requested_scope
        evidence = ContextEvidence(
            ref=ContextEvidenceRef("project-vault", "pricing-decision", "chunk-1"),
            path="wiki/pricing-decision.md",
            section="Pricing calculation decision",
            anchor="pricing-calculation-decision",
            content_hash=content_hash,
            raw_sha256=content_hash,
            metadata_index_revision=f"fixture-metadata:{content_hash[:12]}",
            vault_revision=f"fixture-vault:{content_hash[:12]}",
            excerpt=source,
            excerpt_token_count=max(1, (len(source) + 3) // 4),
            truncated=False,
            retrieval_reasons=("fixture Vault decision matched",),
            warnings=(),
        )
        return ContextPack(
            context_pack_schema_version=CONTEXT_PACK_SCHEMA_VERSION,
            pack_id="fixture-project-context",
            goal=request.goal,
            scope=context_scope_from_query_scopes(requested_scope=scope, actual_scopes=(scope,)),
            vaults=(ContextPackVault("project-vault", "Project Vault"),),
            vault_revisions=(ContextPackVaultRevision("project-vault", evidence.vault_revision, "snapshot"),),
            backend=ContextPackBackend(
                metadata_store=ContextPackBackendUse("fixture-vault-reader", True),
                keyword_index=ContextPackBackendUse(None, False),
                vector_store=ContextPackBackendUse(None, False),
                graph_store=ContextPackBackendUse(None, False),
                graph_projection=ContextPackBackendUse(None, False),
            ),
            store_revisions=(
                ContextPackStoreRevision(
                    "metadata", evidence.metadata_index_revision, "project-vault", "project-vault:wiki:local"
                ),
            ),
            retrieval_policy_version="fixture-vault-reader-v1",
            budget=ContextPackBudget(max_tokens=request.budget.max_tokens, used_tokens=1),
            generated_at="2026-08-04T00:00:00+00:00",
            current_state=(),
            relevant_pages=(),
            relevant_sources=(),
            decisions=(),
            constraints=(),
            open_questions=(),
            warnings=(),
            evidence=(evidence,),
        )


class _FixtureVaultStatus:
    def __init__(self, vault_path: Path) -> None:
        self._vault_path = vault_path

    def status(self, vault_ids: tuple[str, ...]) -> tuple[ProjectAuthorityFreshness, ...]:
        source = (self._vault_path / "wiki" / "pricing-decision.md").read_bytes()
        revision = f"fixture-vault:{hashlib.sha256(source).hexdigest()[:12]}"
        return tuple(ProjectAuthorityFreshness("vault", vault_id, "fresh", revision=revision) for vault_id in vault_ids)


class _ProjectContextFactory:
    """MCP-facing factory whose service is a real ProjectContextService."""

    def __init__(self, service: ProjectContextService) -> None:
        self._service = service

    def open_project_context_service(self) -> ProjectContextService:
        return self._service


def _fixture_manifest() -> dict[str, object]:
    loaded = json.loads((FIXTURE_ROOT / "fixture.json").read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):  # pragma: no cover - versioned fixture contract
        raise TypeError("project context fixture must be an object")
    return cast(dict[str, object], loaded)


def _mapping(value: object) -> dict[str, object]:
    if not isinstance(value, dict):  # pragma: no cover - fixture contract
        raise TypeError("expected object mapping")
    return cast(dict[str, object], value)


def _tree_fingerprint(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _initialize_runtime(tmp_path: Path, *, index_code: bool) -> _Runtime:
    """Copy and use every fixture authority/configuration through public services."""

    repository_path = tmp_path / "repository"
    vault_path = tmp_path / "vault"
    state_path = tmp_path / "state"
    shutil.copytree(FIXTURE_ROOT / "repository", repository_path)
    shutil.copytree(FIXTURE_ROOT / "vault", vault_path)
    shutil.copytree(FIXTURE_ROOT / "state", state_path)

    catalog_service = CatalogService(state_path=state_path)
    catalog_service.create_default_catalog(vault_root=vault_path, vault_id="project-vault")
    template = yaml.safe_load(catalog_service.code_config_path.read_text(encoding="utf-8"))
    if not isinstance(template, dict):  # pragma: no cover - fixture is versioned
        raise TypeError("repository fixture config must be a mapping")
    repositories = template.get("repositories")
    if not isinstance(repositories, list) or len(repositories) != 1 or not isinstance(repositories[0], dict):
        raise TypeError("repository fixture config must contain one repository")
    repositories[0]["root_path"] = str(repository_path)
    catalog_service.code_config_path.write_text(yaml.safe_dump(template, sort_keys=False), encoding="utf-8")

    code_factory = CodeIndexFactory(state_path=state_path)
    code_services = code_factory.open()
    assert code_services.repository_catalog.resolve("demo").root_path == repository_path.resolve()
    bindings = ProjectBindingCatalogService(
        catalog_service=catalog_service,
        repository_catalog=code_services.repository_catalog,
        vault_catalog=catalog_service.load_catalog(),
    )
    binding = bindings.load().resolve("demo")
    bindings.bind(binding)
    if index_code:
        report = code_factory.open_projection_service().apply(CodeIndexRequest(repository_ids=("demo",), full=True))
        assert report.status == "fresh"
        code_query_service = code_factory.open_query_service("demo")
    else:
        code_query_service = None
    project_context_service = ProjectContextService(
        repository_catalog=code_factory.open().repository_catalog,
        binding_catalog=bindings.load(),
        code_query_service=code_query_service,
        context_pack_builder=_FixtureVaultContextPackBuilder(vault_path),
        vault_status_service=_FixtureVaultStatus(vault_path),
    )
    return _Runtime(state_path, repository_path, vault_path, code_factory, project_context_service, index_code)


def _instruction_tokens(instructions: tuple[str, ...]) -> int:
    return sum(max(1, (len(item) + 3) // 4) for item in instructions)


def _evidence_ids(payload: dict[str, object]) -> frozenset[str]:
    evidence_ids: set[str] = set()
    for section in ("code_evidence", "impact_evidence", "test_evidence", "vault_evidence"):
        values = cast(list[dict[str, object]], payload.get(section, []))
        evidence_ids.update(cast(str, item["evidence_id"]) for item in values)
    return frozenset(evidence_ids)


def _baseline_evidence_ids(runtime: _Runtime, scenario: Scenario) -> frozenset[str]:
    query = runtime.code_factory.open_query_service("demo")
    roots = query.search_symbols(
        CodeSymbolSearchRequest(scenario.task, repository_ids=("demo",), limit=scenario.limit, output_format="json")
    ).results
    assert roots
    evidence_ids = {f"code:{root.symbol_id}" for root in roots[: scenario.limit]}
    for root in roots[: scenario.limit]:
        impact = query.get_impact(
            CodeImpactRequest(
                root.symbol_id,
                repository_id="demo",
                depth=scenario.depth,
                limit=scenario.limit,
                output_format="json",
            )
        )
        evidence_ids.update(f"code:{hit.symbol_id}" for hit in impact.result.hits)
    evidence_ids.add(VAULT_EVIDENCE_ID)
    return frozenset(evidence_ids)


def _run_explore_project(runtime: _Runtime, scenario: Scenario) -> BenchmarkResult:
    registry = McpToolRegistry(
        services=cast(Any, object()),
        service_factory=cast(Any, _ProjectContextFactory(runtime.project_context_service)),
        context_pack_cache=ContextPackResourceCache(),
        result_explanation_cache=ResultExplanationCache(),
    )
    body = registry.explore_project(
        ExploreProjectInput(
            task=scenario.task,
            repository_id="demo",
            max_tokens=MAX_TOKENS,
            depth=scenario.depth,
            limit=scenario.limit,
        )
    )
    evidence_ids = _evidence_ids(body.payload)
    expected_ids = _baseline_evidence_ids(runtime, scenario) if runtime.code_indexed else frozenset({VAULT_EVIDENCE_ID})
    warnings = cast(list[dict[str, object]], body.payload["warnings"])
    stale_miss = int(
        scenario.requires_source_drift_warning
        and "source_changed_since_index" not in {cast(str, warning["code"]) for warning in warnings}
    )
    return BenchmarkResult(
        application_tool_calls=1,
        prompt_instruction_tokens=_instruction_tokens(("Call explore_project once with task and repository id.",)),
        fallback_reads=0,
        relevant_evidence_recall=len(evidence_ids & expected_ids) / len(expected_ids),
        stale_result_misses=stale_miss,
        output_tokens=max(1, (len(json.dumps(body.to_json_dict(), sort_keys=True, separators=(",", ":"))) + 3) // 4),
        evidence_ids=evidence_ids,
    )


def _run_scripted_baseline(scenario: Scenario) -> BenchmarkResult:
    return BenchmarkResult(
        application_tool_calls=len(scenario.baseline_tools),
        prompt_instruction_tokens=_instruction_tokens(scenario.baseline_instructions),
        fallback_reads=len(scenario.baseline_tools) - 1,
        relevant_evidence_recall=1.0,
        stale_result_misses=0,
        output_tokens=MAX_TOKENS,
        evidence_ids=frozenset(),
    )


def test_project_context_fixture_declares_actual_catalog_binding_and_authorities() -> None:
    manifest = _fixture_manifest()
    repository_catalog = _mapping(manifest["repository_catalog"])
    stale_case = _mapping(manifest["stale_case"])

    assert repository_catalog["repository_id"] == "demo"
    assert repository_catalog["languages"] == ["python", "dart"]
    assert manifest["project_binding"] == {
        "repository_id": "demo",
        "vault_ids": ["project-vault"],
        "content_scopes": ["wiki"],
    }
    assert stale_case["expected_warning"] == "source_changed_since_index"


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda item: item.name)
def test_explore_project_uses_real_code_projection_and_meets_orchestration_thresholds(
    tmp_path: Path, scenario: Scenario
) -> None:
    runtime = _initialize_runtime(tmp_path, index_code=True)
    repository_before = _tree_fingerprint(runtime.repository_path)
    vault_before = _tree_fingerprint(runtime.vault_path)
    if scenario.requires_source_drift_warning:
        source = runtime.repository_path / "src" / "billing.py"
        source.write_text(source.read_text(encoding="utf-8") + "\n# source drift after indexing\n", encoding="utf-8")
        verified = runtime.code_factory.open_freshness_service().compare(
            CodeFreshnessRequest(repository_ids=("demo",), verify=True)
        )
        assert verified.state == "stale"
        assert any("content hash changed: demo/src/billing.py" == warning for warning in verified.warnings)
        repository_before = _tree_fingerprint(runtime.repository_path)

    baseline = _run_scripted_baseline(scenario)
    explored = _run_explore_project(runtime, scenario)

    assert explored.application_tool_calls < baseline.application_tool_calls
    assert explored.prompt_instruction_tokens < baseline.prompt_instruction_tokens
    assert explored.relevant_evidence_recall >= baseline.relevant_evidence_recall
    assert explored.stale_result_misses == 0
    assert explored.output_tokens <= MAX_TOKENS
    assert len(explored.evidence_ids) <= scenario.limit * 2 + 1
    assert _tree_fingerprint(runtime.repository_path) == repository_before
    assert _tree_fingerprint(runtime.vault_path) == vault_before


def test_explore_project_applies_actual_depth_and_limit_bounds(tmp_path: Path) -> None:
    runtime = _initialize_runtime(tmp_path, index_code=True)
    context = runtime.project_context_service.build(
        ProjectContextRequest(task="calculate_total", repository_id="demo", max_tokens=MAX_TOKENS, depth=0, limit=1)
    )

    assert len(context.code_evidence) <= 1
    assert context.impact_evidence == ()
    assert len(context.test_evidence) <= 1


def test_missing_code_index_fallback_uses_actual_catalog_binding_and_vault_adapter(tmp_path: Path) -> None:
    runtime = _initialize_runtime(tmp_path, index_code=False)
    repository_before = _tree_fingerprint(runtime.repository_path)
    vault_before = _tree_fingerprint(runtime.vault_path)
    scenario = SCENARIOS[0]

    first = _run_explore_project(runtime, scenario)
    second = _run_explore_project(runtime, scenario)

    assert first.evidence_ids == frozenset({VAULT_EVIDENCE_ID})
    assert first == second
    assert _tree_fingerprint(runtime.repository_path) == repository_before
    assert _tree_fingerprint(runtime.vault_path) == vault_before
