from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from vault_graph.interface.composition.adapters.fact_extractor import ExtractedFact, FactExchange
    from vault_graph.operation.scope.facts_settings import FactsSettings


@pytest.fixture(autouse=True)
def _isolate_vault_map(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    # Keep tests off the machine's real $HOME/.claude/vault-builder/vault-map.json.
    missing = tmp_path_factory.mktemp("no-vault-map") / "vault-map.json"
    monkeypatch.setenv("VAULT_GRAPH_VAULT_MAP", str(missing))


class FakeFactExtractor:
    """Fact extractor for tests (spec 2026-11-16 D19, A25). Set `facts` or `error`; `calls` records each input."""

    def __init__(self) -> None:
        self.extractor = "fake"
        self.model = "fake-model"
        self.facts: list[ExtractedFact] = []
        self.error: Exception | None = None
        self.calls: list[list[FactExchange]] = []
        self.settings: list[FactsSettings] = []

    def extract(self, exchanges: Sequence[FactExchange]) -> list[ExtractedFact]:
        self.calls.append(list(exchanges))
        if self.error is not None:
            raise self.error
        return list(self.facts)


@pytest.fixture(autouse=True)
def fake_fact_extractor(monkeypatch: pytest.MonkeyPatch) -> FakeFactExtractor:
    """Make `select_fact_extractor` return a fake, and fail any test that would build a real extractor adapter."""
    from vault_graph.interface.composition.adapters import fact_extractor_selection

    fake = FakeFactExtractor()

    def construct(settings: FactsSettings) -> FakeFactExtractor:
        fake.settings.append(settings)
        return fake

    def refuse(module_name: str, class_name: str) -> type:
        pytest.fail(f"a test tried to build the real fact extractor {module_name}.{class_name}; use the fake")

    monkeypatch.setattr(fact_extractor_selection, "_construct", construct)
    monkeypatch.setattr(fact_extractor_selection, "_load_adapter_class", refuse)
    return fake


@pytest.fixture
def vault_with_page(tmp_path: Path) -> Path:
    vault_root = tmp_path / "vault"
    (vault_root / "wiki").mkdir(parents=True)
    (vault_root / "wiki" / "page.md").write_text("# Page\nBody\n", encoding="utf-8")
    return vault_root
