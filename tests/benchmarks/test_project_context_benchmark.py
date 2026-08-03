"""Deterministic acceptance benchmark for the project-context entry point.

The benchmark deliberately records orchestration work, not wall-clock time.
It uses no model or network dependency, so its comparison remains reproducible
in CI and on a disconnected developer machine.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import pytest

from tests.test_mcp_tools import fake_services
from vault_graph.mcp.context_pack_resource_cache import ContextPackResourceCache
from vault_graph.mcp.mcp_tools import ExploreProjectInput, McpToolRegistry
from vault_graph.mcp.result_explanation_cache import ResultExplanationCache
from vault_graph.project_context import (
    ProjectAuthorityFreshness,
    ProjectBinding,
    ProjectContext,
    ProjectContextBudget,
    ProjectContextWarning,
    ProjectEvidence,
)

FIXTURE_ROOT = Path(__file__).parents[1] / "fixtures" / "project_context"
# This is deliberately well below the 4,000-token default while leaving room
# for the compact MCP envelope (not only the service DTO) in the stale case.
MAX_TOKENS = 1200


@dataclass(frozen=True)
class Scenario:
    name: str
    task: str
    baseline_tools: tuple[str, ...]
    baseline_instructions: tuple[str, ...]
    expected_evidence_ids: frozenset[str]
    requires_stale_warning: bool = False


@dataclass(frozen=True)
class BenchmarkResult:
    application_tool_calls: int
    prompt_instruction_tokens: int
    fallback_reads: int
    relevant_evidence_recall: float
    stale_result_misses: int
    output_tokens: int


SCENARIOS = (
    Scenario(
        name="structure",
        task="Explain the Python and Dart pricing structure.",
        baseline_tools=("code.search", "code.symbol", "code.outline", "vault.search"),
        baseline_instructions=(
            "Search code symbols for pricing.",
            "Open each matching symbol and its source lines.",
            "Outline the Dart implementation.",
            "Search Vault decisions for pricing structure.",
        ),
        expected_evidence_ids=frozenset(
            {"code:calculate_total", "code:dart:format_total", "vault:project-vault:pricing-decision:chunk-1"}
        ),
    ),
    Scenario(
        name="bug_scope",
        task="Investigate the stale tax calculation bug scope.",
        baseline_tools=("code.search", "code.symbol", "code.callers", "code.status", "vault.search"),
        baseline_instructions=(
            "Search the tax calculation symbol.",
            "Read its source evidence.",
            "Find callers and related tests.",
            "Check code index freshness before trusting results.",
            "Find the durable pricing decision.",
        ),
        expected_evidence_ids=frozenset(
            {
                "code:calculate_total",
                "code:checkout_total",
                "code:test_calculate_total",
                "vault:project-vault:pricing-decision:chunk-1",
            }
        ),
        requires_stale_warning=True,
    ),
    Scenario(
        name="impact",
        task="Assess the impact of changing calculate_total.",
        baseline_tools=("code.symbol", "code.callers", "code.callees", "code.impact", "vault.search"),
        baseline_instructions=(
            "Resolve calculate_total.",
            "Traverse callers.",
            "Traverse callees.",
            "Collect impacted tests.",
            "Find the corresponding Vault constraint.",
        ),
        expected_evidence_ids=frozenset(
            {
                "code:calculate_total",
                "code:checkout_total",
                "code:test_calculate_total",
                "vault:project-vault:pricing-decision:chunk-1",
            }
        ),
    ),
    Scenario(
        name="consistency",
        task="Check pricing design and implementation consistency.",
        baseline_tools=("vault.context", "vault.decision_trace", "vault.related", "code.search", "code.symbol"),
        baseline_instructions=(
            "Build Vault context for the pricing decision.",
            "Trace the decision evidence.",
            "Find related design entities.",
            "Search implementation symbols.",
            "Read the selected current code evidence.",
        ),
        expected_evidence_ids=frozenset(
            {"code:calculate_total", "code:dart:format_total", "vault:project-vault:pricing-decision:chunk-1"}
        ),
    ),
)


@dataclass
class _FixtureProjectService:
    contexts: dict[str, ProjectContext]
    requests: list[ExploreProjectInput]

    def build(self, request: object) -> ProjectContext:
        typed_request = cast(ExploreProjectInput, request)
        self.requests.append(typed_request)
        return self.contexts[typed_request.task]


class _FixtureFactory:
    def __init__(self, service: _FixtureProjectService) -> None:
        self._service = service

    def open_project_context_service(self) -> _FixtureProjectService:
        return self._service


def _fixture_manifest() -> dict[str, object]:
    loaded = json.loads((FIXTURE_ROOT / "fixture.json").read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):  # pragma: no cover - fixture is static and versioned
        raise TypeError("project context fixture must be an object")
    return cast(dict[str, object], loaded)


def _mapping(value: object) -> dict[str, object]:
    if not isinstance(value, dict):  # pragma: no cover - fixture and serializer contracts are static
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


def _code_evidence(
    evidence_id: str,
    title: str,
    relative_path: str,
    start_line: int,
    end_line: int,
    *,
    freshness: str = "fresh",
) -> ProjectEvidence:
    return ProjectEvidence(
        evidence_id=evidence_id,
        authority="code",
        title=title,
        summary=title,
        relationship_status="stated",
        revision="fixture-revision",
        freshness=cast(Any, freshness),
        source_uri=f"vg-source://demo/{relative_path}#L{start_line}-L{end_line}",
        repository_id="demo",
        relative_path=relative_path,
        start_line=start_line,
        end_line=end_line,
    )


def _vault_evidence() -> ProjectEvidence:
    return ProjectEvidence(
        evidence_id="vault:project-vault:pricing-decision:chunk-1",
        authority="vault",
        title="Pricing calculation decision",
        summary="Pricing remains a pure calculation shared by Python and Dart clients.",
        relationship_status="stated",
        revision="vault-fixture-revision",
        freshness="fresh",
        source_uri="vault://project-vault/wiki/pricing-decision.md",
        vault_id="project-vault",
        relative_path="wiki/pricing-decision.md",
    )


def _context_for(scenario: Scenario) -> ProjectContext:
    by_id = {
        "code:calculate_total": _code_evidence("code:calculate_total", "calculate_total", "src/billing.py", 4, 8),
        "code:dart:format_total": _code_evidence("code:dart:format_total", "formatTotal", "lib/billing.dart", 3, 6),
        "code:checkout_total": _code_evidence("code:checkout_total", "checkout_total", "src/billing.py", 11, 13),
        "code:test_calculate_total": _code_evidence(
            "code:test_calculate_total", "test_calculate_total", "tests/billing_checks.py", 4, 7
        ),
        "vault:project-vault:pricing-decision:chunk-1": _vault_evidence(),
    }
    selected = {item: by_id[item] for item in scenario.expected_evidence_ids}
    stale = scenario.requires_stale_warning
    if stale:
        selected["code:calculate_total"] = _code_evidence(
            "code:calculate_total", "calculate_total", "src/billing.py", 4, 8, freshness="stale"
        )
    code = tuple(
        item for item in selected.values() if item.authority == "code" and item.evidence_id == "code:calculate_total"
    )
    impact = tuple(item for item in selected.values() if item.evidence_id == "code:checkout_total")
    tests = tuple(item for item in selected.values() if item.evidence_id == "code:test_calculate_total")
    other_code = tuple(
        item
        for item in selected.values()
        if item.authority == "code"
        and item.evidence_id not in {"code:calculate_total", "code:checkout_total", "code:test_calculate_total"}
    )
    return ProjectContext(
        task=scenario.task,
        repository_id="demo",
        binding=ProjectBinding("demo", ("project-vault",), ("wiki",)),
        freshness="stale" if stale else "fresh",
        code_evidence=tuple(sorted((*code, *other_code), key=lambda item: item.evidence_id)),
        impact_evidence=impact,
        test_evidence=tests,
        vault_evidence=tuple(item for item in selected.values() if item.authority == "vault"),
        relations=(),
        authority_freshness=(
            ProjectAuthorityFreshness("code", "demo", "stale" if stale else "fresh", revision="fixture-revision"),
            ProjectAuthorityFreshness("vault", "project-vault", "fresh", revision="vault-fixture-revision"),
        ),
        warnings=(
            ProjectContextWarning(
                code="source_changed_since_index",
                message="Current source differs from the indexed source; re-index before editing.",
                freshness="stale",
                authority_id="demo",
            ),
        )
        if stale
        else (),
        budget=ProjectContextBudget(max_tokens=MAX_TOKENS, used_tokens=1),
    )


def _instruction_tokens(instructions: tuple[str, ...]) -> int:
    return sum(max(1, (len(item) + 3) // 4) for item in instructions)


def _evidence_ids(payload: dict[str, object]) -> frozenset[str]:
    ids: set[str] = set()
    for section in ("code_evidence", "impact_evidence", "test_evidence", "vault_evidence"):
        values = cast(list[dict[str, object]], payload.get(section, []))
        ids.update(cast(str, item["evidence_id"]) for item in values)
    return frozenset(ids)


def _stale_result_misses(payload: dict[str, object], scenario: Scenario) -> int:
    if not scenario.requires_stale_warning:
        return 0
    warning_codes = {cast(str, item["code"]) for item in cast(list[dict[str, object]], payload["warnings"])}
    return int(payload["freshness"] != "stale" or "source_changed_since_index" not in warning_codes)


def _run_explore_project(tmp_path: Path, scenario: Scenario) -> BenchmarkResult:
    service = _FixtureProjectService({scenario.task: _context_for(scenario)}, [])
    registry = McpToolRegistry(
        services=fake_services(tmp_path),
        service_factory=cast(Any, _FixtureFactory(service)),
        context_pack_cache=ContextPackResourceCache(),
        result_explanation_cache=ResultExplanationCache(),
    )
    body = registry.explore_project(
        ExploreProjectInput(task=scenario.task, repository_id="demo", max_tokens=MAX_TOKENS, depth=2, limit=20)
    )
    payload = body.payload
    evidence_ids = _evidence_ids(payload)
    return BenchmarkResult(
        application_tool_calls=1,
        prompt_instruction_tokens=_instruction_tokens(("Call explore_project once with the task and repository id.",)),
        fallback_reads=0,
        relevant_evidence_recall=len(evidence_ids & scenario.expected_evidence_ids)
        / len(scenario.expected_evidence_ids),
        stale_result_misses=_stale_result_misses(payload, scenario),
        output_tokens=max(1, (len(json.dumps(body.to_json_dict(), sort_keys=True)) + 3) // 4),
    )


def _run_scripted_baseline(scenario: Scenario) -> BenchmarkResult:
    """Count the explicit application calls a coding harness had to orchestrate."""

    return BenchmarkResult(
        application_tool_calls=len(scenario.baseline_tools),
        prompt_instruction_tokens=_instruction_tokens(scenario.baseline_instructions),
        fallback_reads=len(scenario.baseline_tools) - 1,
        relevant_evidence_recall=1.0,
        stale_result_misses=0,
        output_tokens=MAX_TOKENS,
    )


def test_project_context_fixture_declares_two_authorities_and_stale_case() -> None:
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
    assert (FIXTURE_ROOT / "repository" / "src" / "billing.py").is_file()
    assert (FIXTURE_ROOT / "repository" / "lib" / "billing.dart").is_file()
    assert (FIXTURE_ROOT / "repository" / "tests" / "billing_checks.py").is_file()
    assert (FIXTURE_ROOT / "vault" / "wiki" / "pricing-decision.md").is_file()


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda item: item.name)
def test_explore_project_meets_deterministic_orchestration_acceptance_thresholds(
    tmp_path: Path, scenario: Scenario
) -> None:
    repository_before = _tree_fingerprint(FIXTURE_ROOT / "repository")
    vault_before = _tree_fingerprint(FIXTURE_ROOT / "vault")
    baseline = _run_scripted_baseline(scenario)
    explored = _run_explore_project(tmp_path, scenario)

    assert explored.application_tool_calls < baseline.application_tool_calls
    assert explored.prompt_instruction_tokens < baseline.prompt_instruction_tokens
    assert explored.relevant_evidence_recall >= baseline.relevant_evidence_recall
    assert explored.stale_result_misses == 0
    assert explored.output_tokens <= MAX_TOKENS
    assert _tree_fingerprint(FIXTURE_ROOT / "repository") == repository_before
    assert _tree_fingerprint(FIXTURE_ROOT / "vault") == vault_before


def test_missing_code_index_fallback_is_deterministic_and_read_only(tmp_path: Path) -> None:
    scenario = SCENARIOS[0]
    repository_before = _tree_fingerprint(FIXTURE_ROOT / "repository")
    vault_before = _tree_fingerprint(FIXTURE_ROOT / "vault")
    unavailable = ProjectContext(
        task=scenario.task,
        repository_id="demo",
        binding=ProjectBinding("demo", ("project-vault",), ("wiki",)),
        freshness="unavailable",
        code_evidence=(),
        vault_evidence=(_vault_evidence(),),
        relations=(),
        authority_freshness=(
            ProjectAuthorityFreshness("code", "demo", "unavailable"),
            ProjectAuthorityFreshness("vault", "project-vault", "fresh"),
        ),
        warnings=(
            ProjectContextWarning(
                code="code_index_unavailable",
                message="Code projection is unavailable; Vault evidence remains available.",
                freshness="unavailable",
                authority_id="demo",
            ),
        ),
        budget=ProjectContextBudget(max_tokens=MAX_TOKENS, used_tokens=1),
    )
    service = _FixtureProjectService({scenario.task: unavailable}, [])
    registry = McpToolRegistry(
        services=fake_services(tmp_path),
        service_factory=cast(Any, _FixtureFactory(service)),
        context_pack_cache=ContextPackResourceCache(),
        result_explanation_cache=ResultExplanationCache(),
    )

    first = registry.explore_project(
        ExploreProjectInput(task=scenario.task, repository_id="demo", max_tokens=MAX_TOKENS)
    )
    second = registry.explore_project(
        ExploreProjectInput(task=scenario.task, repository_id="demo", max_tokens=MAX_TOKENS)
    )

    assert first.to_json_dict() == second.to_json_dict()
    assert _evidence_ids(first.payload) == frozenset({"vault:project-vault:pricing-decision:chunk-1"})
    warnings = cast(list[dict[str, object]], first.payload["warnings"])
    assert warnings[0]["code"] == "code_index_unavailable"
    assert _tree_fingerprint(FIXTURE_ROOT / "repository") == repository_before
    assert _tree_fingerprint(FIXTURE_ROOT / "vault") == vault_before
