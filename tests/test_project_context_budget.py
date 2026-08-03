from __future__ import annotations

from pathlib import Path

from tests.test_project_context_service import _Code, _service
from vault_graph.code_index.code_models import CodeSymbolResponse
from vault_graph.project_context import ProjectContextRequest, estimate_project_context_tokens


def test_project_context_serialized_output_stays_within_budget_for_long_evidence_fields(tmp_path: Path) -> None:
    context = _service(tmp_path, code=_Code()).build(ProjectContextRequest(task="x" * 500, max_tokens=512, limit=20))

    assert estimate_project_context_tokens(context) <= context.budget.max_tokens
    assert context.budget.used_tokens == estimate_project_context_tokens(context)


def test_project_context_budget_accounts_for_long_source_uris_and_warnings(tmp_path: Path) -> None:
    class LongEvidenceCode(_Code):
        def get_symbol(self, request: object) -> CodeSymbolResponse:
            return CodeSymbolResponse(
                symbol=None,
                freshness="fresh",
                source_uri="vg-source://demo/" + ("nested/" * 300) + "source.py#L1-L2",
                warnings=("source_changed_since_index:" + ("reason-" * 300),),
            )

    context = _service(tmp_path, code=LongEvidenceCode()).build(
        ProjectContextRequest(task="Bound long evidence", max_tokens=512, limit=20)
    )

    assert estimate_project_context_tokens(context) <= 512
    assert context.budget.omitted_evidence > 0
