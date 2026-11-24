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


class FakeDreamSchedule:
    """The launchd schedule in every test (spec 2026-11-24 I6). Set `fail` or `platform` to test errors."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str | None]] = []
        self.installed_at: str | None = None
        self.fail: str | None = None
        self.platform = "darwin"
        self.plist_path = Path("/fake/LaunchAgents/io.vault-graph.dream.fake.plist")

    def install(self, run_at: str) -> object:
        from vault_graph.interface.composition.adapters.dream_schedule import ScheduleResult

        self.calls.append(("install", run_at))
        if self.platform != "darwin":
            return ScheduleResult(
                ok=True, status="unsupported", plist_path=None, reason=f"unsupported on {self.platform}"
            )
        if self.fail is not None:
            return ScheduleResult(ok=False, status="not_installed", plist_path=None, reason=self.fail)
        self.installed_at = run_at
        return ScheduleResult(ok=True, status="installed", plist_path=self.plist_path, reason="")

    def remove(self) -> object:
        from vault_graph.interface.composition.adapters.dream_schedule import ScheduleResult

        self.calls.append(("remove", None))
        if self.platform != "darwin":
            return ScheduleResult(
                ok=True, status="unsupported", plist_path=None, reason=f"unsupported on {self.platform}"
            )
        if self.fail is not None:
            return ScheduleResult(ok=False, status="installed", plist_path=self.plist_path, reason=self.fail)
        self.installed_at = None
        return ScheduleResult(ok=True, status="not_installed", plist_path=None, reason="")

    def state(self, run_at: str | None = None) -> object:
        from vault_graph.interface.composition.adapters.dream_schedule import ScheduleState

        if self.platform != "darwin":
            return ScheduleState(status="unsupported", plist_path=None, reason=f"unsupported on {self.platform}")
        if self.installed_at is None:
            return ScheduleState(status="not_installed", plist_path=None, reason="")
        if run_at is not None and run_at != self.installed_at:
            reason = f"plist runs at {self.installed_at}, run_at is {run_at}"
            return ScheduleState(status="stale", plist_path=self.plist_path, reason=reason)
        return ScheduleState(status="installed", plist_path=self.plist_path, reason="")


@pytest.fixture(autouse=True)
def fake_dream_schedule(monkeypatch: pytest.MonkeyPatch) -> FakeDreamSchedule:
    """Keep every test off the real $HOME/Library/LaunchAgents and launchctl."""
    from vault_graph.interface.cli import dream_commands

    fake = FakeDreamSchedule()
    monkeypatch.setattr(dream_commands, "_schedule_for", lambda graph_home: fake)
    return fake


@pytest.fixture
def vault_with_page(tmp_path: Path) -> Path:
    vault_root = tmp_path / "vault"
    (vault_root / "wiki").mkdir(parents=True)
    (vault_root / "wiki" / "page.md").write_text("# Page\nBody\n", encoding="utf-8")
    return vault_root
