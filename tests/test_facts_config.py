"""Fact extraction settings, extractor port and selection, `vg facts on|off|status`.

Spec 2026-11-16 D18, D19, F13, A17 and spec 2026-11-25-facts-extractor-auto A4, A9.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tests.conftest import FakeFactExtractor, FakeLlamaHealth
from vault_graph.errors import CatalogError
from vault_graph.interface.cli.main import app
from vault_graph.interface.composition.adapters import fact_extractor_selection
from vault_graph.interface.composition.adapters.fact_extractor import FactExtractor
from vault_graph.interface.composition.adapters.fact_extractor_selection import select_fact_extractor
from vault_graph.operation.scope.facts_settings import (
    CLAUDE_FACTS_MODEL,
    LOCAL_FACTS_ENDPOINT,
    FactsSettings,
    default_facts_settings,
    facts_failures_path,
    facts_last_job_path,
    facts_queue_dir,
    facts_settings_path,
    local_facts_model,
    read_facts_settings,
    resolve_facts_settings,
    save_facts_settings,
)

runner = CliRunner()


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _init_graph_home(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    (vault / "wiki").mkdir(parents=True)
    (vault / "wiki" / "page.md").write_text("# Page\nBody\n", encoding="utf-8")
    graph_home = tmp_path / "graph-home"
    result = runner.invoke(app, ["init", "--vault", str(vault), "--graph-home", str(graph_home)])
    assert result.exit_code == 0, result.output
    return graph_home


# Settings file


def test_settings_file_lives_in_graph_home_configs(tmp_path: Path) -> None:
    assert facts_settings_path(tmp_path) == tmp_path / "configs" / "facts.json"
    assert facts_queue_dir(tmp_path) == tmp_path / "facts" / "queue"
    assert facts_failures_path(tmp_path) == tmp_path / "logs" / "facts-failures.json"
    assert facts_last_job_path(tmp_path) == tmp_path / "logs" / "facts-last-job.json"


def test_missing_file_means_on_with_auto(tmp_path: Path) -> None:
    reading = read_facts_settings(facts_settings_path(tmp_path))

    assert reading.settings == FactsSettings(
        enabled=True, extractor="auto", endpoint=LOCAL_FACTS_ENDPOINT, model=local_facts_model()
    )
    assert reading.source == "default"
    assert reading.problem is None
    assert not facts_settings_path(tmp_path).exists()


def test_local_defaults_point_at_llama_server_and_qwen_model() -> None:
    settings = default_facts_settings("llama-server")

    assert settings == FactsSettings(
        enabled=True, extractor="llama-server", endpoint=LOCAL_FACTS_ENDPOINT, model=local_facts_model()
    )
    assert local_facts_model() == str(Path.home() / "llm" / "models" / "Qwen3.5-27B-Q4_K_M.gguf")


def test_auto_defaults_hold_the_local_endpoint_and_model() -> None:
    assert default_facts_settings("auto") == FactsSettings(
        enabled=True, extractor="auto", endpoint=LOCAL_FACTS_ENDPOINT, model=local_facts_model()
    )


def test_resolve_auto_picks_llama_server_when_it_answers() -> None:
    asked: list[str] = []
    settings = FactsSettings(enabled=True, extractor="auto", endpoint="http://127.0.0.1:9000", model="/m.gguf")

    def answers(endpoint: str) -> bool:
        asked.append(endpoint)
        return True

    resolved = resolve_facts_settings(settings, local_answers=answers)

    assert resolved == FactsSettings(
        enabled=True, extractor="llama-server", endpoint="http://127.0.0.1:9000", model="/m.gguf"
    )
    assert asked == ["http://127.0.0.1:9000"]


def test_resolve_auto_picks_claude_when_llama_server_does_not_answer() -> None:
    settings = FactsSettings(enabled=True, extractor="auto", endpoint="http://127.0.0.1:9000", model="/m.gguf")

    resolved = resolve_facts_settings(settings, local_answers=lambda endpoint: False)

    assert resolved == FactsSettings(enabled=True, extractor="claude", endpoint=None, model=CLAUDE_FACTS_MODEL)


@pytest.mark.parametrize("extractor", ["claude", "llama-server"])
def test_resolve_keeps_fixed_extractors_without_checking(extractor: str) -> None:
    settings = default_facts_settings(extractor)

    def refuse(endpoint: str) -> bool:
        raise AssertionError("a fixed extractor must not check the server")

    assert resolve_facts_settings(settings, local_answers=refuse) is settings


@pytest.mark.parametrize(
    "settings",
    [
        FactsSettings(enabled=False, extractor="claude", endpoint=None, model=CLAUDE_FACTS_MODEL),
        FactsSettings(enabled=True, extractor="auto", endpoint="http://127.0.0.1:9000", model="/m/q.gguf"),
        FactsSettings(enabled=True, extractor="llama-server", endpoint="http://127.0.0.1:9000", model="/m/q.gguf"),
    ],
)
def test_save_then_read_round_trips(tmp_path: Path, settings: FactsSettings) -> None:
    path = facts_settings_path(tmp_path)
    save_facts_settings(path, settings)

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload == {
        "version": 1,
        "enabled": settings.enabled,
        "extractor": settings.extractor,
        "endpoint": settings.endpoint,
        "model": settings.model,
    }
    reading = read_facts_settings(path)
    assert reading.settings == settings
    assert reading.source == "file"
    assert reading.problem is None


def test_save_refuses_invalid_settings(tmp_path: Path) -> None:
    with pytest.raises(CatalogError):
        save_facts_settings(
            facts_settings_path(tmp_path), FactsSettings(enabled=True, extractor="gpt", endpoint=None, model="x")
        )
    assert not facts_settings_path(tmp_path).exists()


_GOOD = {"version": 1, "enabled": True, "extractor": "claude", "endpoint": None, "model": "claude-sonnet-5-5"}


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        ("{not json", "not valid JSON"),
        ("[]", "JSON object"),
        (json.dumps({**_GOOD, "extra": 1}), "unknown keys"),
        (json.dumps({k: v for k, v in _GOOD.items() if k != "model"}), "missing keys"),
        (json.dumps({**_GOOD, "version": 2}), "version"),
        (json.dumps({**_GOOD, "enabled": "yes"}), "enabled"),
        (json.dumps({**_GOOD, "extractor": "gpt"}), "extractor"),
        (json.dumps({**_GOOD, "model": ""}), "model"),
        (json.dumps({**_GOOD, "endpoint": "http://x"}), "endpoint"),
        (json.dumps({**_GOOD, "extractor": "llama-server", "endpoint": None}), "endpoint"),
        (json.dumps({**_GOOD, "extractor": "llama-server", "endpoint": "ftp://x"}), "endpoint"),
        (json.dumps({**_GOOD, "extractor": "auto", "endpoint": None}), "endpoint"),
        (json.dumps({**_GOOD, "extractor": "auto", "endpoint": "ftp://x"}), "endpoint"),
    ],
)
def test_broken_file_means_off_with_reason(tmp_path: Path, text: str, reason: str) -> None:
    path = facts_settings_path(tmp_path)
    _write(path, text)

    reading = read_facts_settings(path)

    assert reading.settings.enabled is False
    assert reading.source == "broken"
    assert reading.problem is not None
    assert reason in reading.problem
    assert str(path) in reading.problem


def test_directory_in_place_of_file_means_off(tmp_path: Path) -> None:
    path = facts_settings_path(tmp_path)
    path.mkdir(parents=True)

    reading = read_facts_settings(path)

    assert reading.settings.enabled is False
    assert reading.source == "broken"


# Port and selection


def test_selection_returns_the_fake_extractor_installed_by_conftest(fake_fact_extractor: FakeFactExtractor) -> None:
    extractor = select_fact_extractor(default_facts_settings("claude"))

    assert extractor is fake_fact_extractor
    assert isinstance(extractor, FactExtractor)


def test_selection_refuses_unresolved_auto() -> None:
    with pytest.raises(CatalogError, match="auto"):
        select_fact_extractor(default_facts_settings("auto"))


def test_selection_refuses_disabled_settings() -> None:
    with pytest.raises(CatalogError, match="off"):
        select_fact_extractor(FactsSettings(enabled=False, extractor="claude", endpoint=None, model="m"))


def test_real_adapter_construction_fails_the_test_under_conftest() -> None:
    with pytest.raises(pytest.fail.Exception, match="real fact extractor"):
        fact_extractor_selection.construct_real_fact_extractor(default_facts_settings("claude"))


@pytest.mark.parametrize(
    ("extractor", "module", "class_name"),
    [
        ("claude", "vault_graph.interface.composition.adapters.claude_fact_extractor", "ClaudeFactExtractor"),
        ("llama-server", "vault_graph.interface.composition.adapters.llama_fact_extractor", "LlamaFactExtractor"),
    ],
)
def test_real_selection_lazily_loads_the_named_adapter_with_settings(
    monkeypatch: pytest.MonkeyPatch, extractor: str, module: str, class_name: str
) -> None:
    assert fact_extractor_selection.REAL_FACT_EXTRACTORS[extractor] == (module, class_name)
    loaded: list[tuple[str, str]] = []

    class Stub:
        def __init__(self, *, endpoint: str | None, model: str) -> None:
            self.endpoint = endpoint
            self.model = model

    def load(module_name: str, attribute: str) -> type:
        loaded.append((module_name, attribute))
        return Stub

    monkeypatch.setattr(fact_extractor_selection, "_load_adapter_class", load)
    settings = default_facts_settings(extractor)

    built = fact_extractor_selection.construct_real_fact_extractor(settings)

    assert loaded == [(module, class_name)]
    assert isinstance(built, Stub)
    assert built.endpoint == settings.endpoint
    assert built.model == settings.model


def test_selection_module_does_not_import_adapters_at_load_time() -> None:
    source = Path(fact_extractor_selection.__file__).read_text(encoding="utf-8")
    head = source.split("\ndef ", 1)[0]
    assert "claude_fact_extractor import" not in head
    assert "llama_fact_extractor import" not in head


# CLI


def test_status_without_file_shows_on_auto_and_empty_queue(tmp_path: Path) -> None:
    graph_home = _init_graph_home(tmp_path)

    result = runner.invoke(app, ["facts", "status", "--graph-home", str(graph_home)])

    assert result.exit_code == 0, result.output
    assert "facts: on" in result.output
    assert "extractor: auto" in result.output
    assert "settings: default (no file)" in result.output
    assert "queue: 0" in result.output
    assert "failures: 0" in result.output


def test_off_writes_enabled_false_and_on_turns_it_back(tmp_path: Path) -> None:
    graph_home = _init_graph_home(tmp_path)
    path = facts_settings_path(graph_home)

    off = runner.invoke(app, ["facts", "off", "--graph-home", str(graph_home)])
    assert off.exit_code == 0, off.output
    assert json.loads(path.read_text(encoding="utf-8"))["enabled"] is False
    assert "facts: off" in runner.invoke(app, ["facts", "status", "--graph-home", str(graph_home)]).output

    assert read_facts_settings(path).settings.extractor == "auto"

    on = runner.invoke(app, ["facts", "on", "--graph-home", str(graph_home)])
    assert on.exit_code == 0, on.output
    assert read_facts_settings(path).settings == default_facts_settings("auto")


@pytest.mark.parametrize("extractor", ["auto", "claude", "llama-server"])
def test_on_with_extractor_saves_that_extractor(tmp_path: Path, extractor: str) -> None:
    graph_home = _init_graph_home(tmp_path)

    result = runner.invoke(app, ["facts", "on", "--extractor", extractor, "--graph-home", str(graph_home)])

    assert result.exit_code == 0, result.output
    assert f"facts: on {extractor}" in result.output
    assert read_facts_settings(facts_settings_path(graph_home)).settings == default_facts_settings(extractor)


def test_saved_claude_file_keeps_working(tmp_path: Path) -> None:
    graph_home = _init_graph_home(tmp_path)
    path = facts_settings_path(graph_home)
    _write(path, json.dumps(_GOOD))

    status = runner.invoke(app, ["facts", "status", "--graph-home", str(graph_home)]).output
    on = runner.invoke(app, ["facts", "on", "--graph-home", str(graph_home)])

    assert "extractor: claude" in status
    assert f"extractor_now: claude {CLAUDE_FACTS_MODEL}" in status
    assert on.exit_code == 0, on.output
    assert read_facts_settings(path).settings == default_facts_settings("claude")


def _status(graph_home: Path) -> str:
    result = runner.invoke(app, ["facts", "status", "--graph-home", str(graph_home)])
    assert result.exit_code == 0, result.output
    return result.output


def test_status_shows_auto_picks_claude_when_llama_server_is_down(
    tmp_path: Path, fake_llama_health: FakeLlamaHealth
) -> None:
    graph_home = _init_graph_home(tmp_path)

    output = _status(graph_home)

    assert (
        f"extractor_now: claude {CLAUDE_FACTS_MODEL} (llama-server not answering at {LOCAL_FACTS_ENDPOINT})" in output
    )
    assert fake_llama_health.calls == [(LOCAL_FACTS_ENDPOINT, 1.0)]


def test_status_shows_auto_picks_llama_server_when_it_answers(
    tmp_path: Path, fake_llama_health: FakeLlamaHealth
) -> None:
    graph_home = _init_graph_home(tmp_path)
    fake_llama_health.up = True

    output = _status(graph_home)

    assert f"extractor_now: llama-server {local_facts_model()}\n" in output


def test_status_shows_fixed_llama_server_not_answering(tmp_path: Path) -> None:
    graph_home = _init_graph_home(tmp_path)
    save_facts_settings(facts_settings_path(graph_home), default_facts_settings("llama-server"))

    output = _status(graph_home)

    assert f"extractor_now: llama-server {local_facts_model()} (not answering)" in output


def test_status_shows_no_extractor_when_off(tmp_path: Path, fake_llama_health: FakeLlamaHealth) -> None:
    graph_home = _init_graph_home(tmp_path)
    runner.invoke(app, ["facts", "off", "--graph-home", str(graph_home)])

    output = _status(graph_home)

    assert "extractor_now: none" in output
    assert fake_llama_health.calls == []


def test_status_shows_last_job_record(tmp_path: Path) -> None:
    graph_home = _init_graph_home(tmp_path)
    assert "last_job: none" in _status(graph_home)
    record = {
        "job": "j1.json",
        "status": "written",
        "extractor": "claude",
        "model": CLAUDE_FACTS_MODEL,
        "finished_at": "2026-11-25T01:02:03Z",
    }
    _write(facts_last_job_path(graph_home), json.dumps(record))

    assert f"last_job: j1.json written claude {CLAUDE_FACTS_MODEL} 2026-11-25T01:02:03Z" in _status(graph_home)

    _write(facts_last_job_path(graph_home), "{broken")
    assert "last_job: unreadable" in _status(graph_home)


def test_on_with_llama_server_selects_local_extractor(tmp_path: Path) -> None:
    graph_home = _init_graph_home(tmp_path)

    result = runner.invoke(app, ["facts", "on", "--extractor", "llama-server", "--graph-home", str(graph_home)])

    assert result.exit_code == 0, result.output
    assert read_facts_settings(facts_settings_path(graph_home)).settings == default_facts_settings("llama-server")
    status = runner.invoke(app, ["facts", "status", "--graph-home", str(graph_home)]).output
    assert "extractor: llama-server" in status
    assert f"endpoint: {LOCAL_FACTS_ENDPOINT}" in status


def test_on_without_extractor_keeps_saved_local_choice(tmp_path: Path) -> None:
    graph_home = _init_graph_home(tmp_path)
    path = facts_settings_path(graph_home)
    save_facts_settings(
        path, FactsSettings(enabled=False, extractor="llama-server", endpoint="http://127.0.0.1:9000", model="/m.gguf")
    )

    result = runner.invoke(app, ["facts", "on", "--graph-home", str(graph_home)])

    assert result.exit_code == 0, result.output
    assert read_facts_settings(path).settings == FactsSettings(
        enabled=True, extractor="llama-server", endpoint="http://127.0.0.1:9000", model="/m.gguf"
    )


def test_on_rejects_unknown_extractor(tmp_path: Path) -> None:
    graph_home = _init_graph_home(tmp_path)

    result = runner.invoke(app, ["facts", "on", "--extractor", "gpt", "--graph-home", str(graph_home)])

    assert result.exit_code != 0
    assert not facts_settings_path(graph_home).exists()


def test_status_of_broken_file_shows_off_and_reason(tmp_path: Path) -> None:
    graph_home = _init_graph_home(tmp_path)
    _write(facts_settings_path(graph_home), "{not json")

    result = runner.invoke(app, ["facts", "status", "--graph-home", str(graph_home)])

    assert result.exit_code == 0, result.output
    assert "facts: off" in result.output
    assert "settings: broken" in result.output
    assert "problem:" in result.output
    assert "not valid JSON" in result.output


def test_off_replaces_broken_file(tmp_path: Path) -> None:
    graph_home = _init_graph_home(tmp_path)
    path = facts_settings_path(graph_home)
    _write(path, "{not json")

    result = runner.invoke(app, ["facts", "off", "--graph-home", str(graph_home)])

    assert result.exit_code == 0, result.output
    reading = read_facts_settings(path)
    assert reading.source == "file"
    assert reading.settings.enabled is False


def test_status_counts_queue_files_and_failures_when_present(tmp_path: Path) -> None:
    graph_home = _init_graph_home(tmp_path)
    queue = facts_queue_dir(graph_home)
    _write(queue / "a.json", "{}")
    _write(queue / "b.json", "{}")
    _write(queue / ".tmp-c.json", "{}")
    _write(facts_failures_path(graph_home), json.dumps([{"job": "a", "error": "claude_unavailable"}]))

    result = runner.invoke(app, ["facts", "status", "--graph-home", str(graph_home)])

    assert result.exit_code == 0, result.output
    assert "queue: 2" in result.output
    assert "failures: 1" in result.output


def test_status_reports_unreadable_failures_file(tmp_path: Path) -> None:
    graph_home = _init_graph_home(tmp_path)
    _write(facts_failures_path(graph_home), "{broken")

    result = runner.invoke(app, ["facts", "status", "--graph-home", str(graph_home)])

    assert result.exit_code == 0, result.output
    assert "failures: unreadable" in result.output


def test_commands_require_initialized_graph_home(tmp_path: Path) -> None:
    for command in (["on"], ["off"], ["status"]):
        result = runner.invoke(app, ["facts", *command, "--graph-home", str(tmp_path / "missing")])
        assert result.exit_code == 1, command
        assert "graph_home_not_initialized" in result.output
