"""The setup line for an unset ``sharable`` (spec 2026-11-05 §4.4.2, §6, A-20).

Only Vaults linked to two or more projects read ``sharable``, so only they get the line.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from vault_graph.context.pack.recall import RecallUnavailable
from vault_graph.interface.cli.hook_commands import hook_app
from vault_graph.interface.composition.read_only_service_factory import ReadOnlyServiceFactory
from vault_graph.operation.integration.vault_map import load_vault_map

runner = CliRunner()


def _write_map(base: Path, vaults: dict[str, dict[str, object]], projects: dict[str, list[str]]) -> Path:
    data = {
        "version": 2,
        "vaults": {
            name: {"path": str(base / "vaults" / name), "role": "personal", **extra} for name, extra in vaults.items()
        },
        "projects": {pid: {"root": str(base / "repos" / pid), "vaults": names} for pid, names in projects.items()},
    }
    path = base / "map" / "vault-map.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_notice_names_only_unset_vaults_linked_to_two_or_more_projects(tmp_path: Path) -> None:
    path = _write_map(
        tmp_path,
        {"personal": {}, "team": {"sharable": False}, "alpha-vault": {}, "odd": {"sharable": "yes"}},
        {"alpha": ["personal", "team", "alpha-vault", "odd"], "beta": ["personal", "team", "odd"]},
    )

    vault_map = load_vault_map(path)

    (notice,) = vault_map.sharable_notices()
    assert notice.startswith("`personal`의 `sharable`이 설정되지 않아 false로 다룸. 설정 방법: ")
    assert "vaults.personal.sharable" in notice
    assert "\n" not in notice
    # The non-boolean value is a field warning, not a second line here.
    assert len(vault_map.warnings) == 1 and "odd" in vault_map.warnings[0]


def test_notice_goes_away_once_the_field_is_set(tmp_path: Path) -> None:
    path = _write_map(tmp_path, {"personal": {"sharable": True}}, {"alpha": ["personal"], "beta": ["personal"]})

    assert load_vault_map(path).sharable_notices() == ()


def test_single_project_vault_gets_no_notice(tmp_path: Path) -> None:
    path = _write_map(tmp_path, {"alpha-vault": {}}, {"alpha": ["alpha-vault"]})

    assert load_vault_map(path).sharable_notices() == ()


def test_notices_can_be_limited_to_some_vaults(tmp_path: Path) -> None:
    path = _write_map(
        tmp_path, {"personal": {}, "team": {}}, {"alpha": ["personal", "team"], "beta": ["personal", "team"]}
    )

    notices = load_vault_map(path).sharable_notices(["team"])

    assert len(notices) == 1 and notices[0].startswith("`team`")


def _repo(path: Path) -> Path:
    path.mkdir(parents=True)
    subprocess.run(["git", "-C", str(path), "init", "-q"], check=True)
    return path.resolve()


@pytest.fixture
def no_recall(monkeypatch: pytest.MonkeyPatch) -> None:
    def unavailable(self: ReadOnlyServiceFactory, *, vault_map_path: Path) -> object:
        raise RecallUnavailable("No Graph Home.")

    monkeypatch.setattr(ReadOnlyServiceFactory, "open_session_recall", unavailable)


def _session_start(base: Path, map_path: Path, repo: Path) -> tuple[int, list[str]]:
    result = runner.invoke(
        hook_app,
        ["session-start", "--graph-home", str(base / "home"), "--vault-map", str(map_path), "--refresh-budget", "0"],
        input=json.dumps({"cwd": str(repo), "source": "startup", "session_id": "s"}),
    )
    return result.exit_code, result.stderr.splitlines()


@pytest.mark.usefixtures("no_recall")
def test_session_start_prints_one_notice_line_per_unset_shared_vault_of_the_project(tmp_path: Path) -> None:
    base = tmp_path.resolve()
    alpha = _repo(base / "repos" / "alpha")
    _repo(base / "repos" / "beta")
    map_path = _write_map(
        base,
        {"personal": {}, "alpha-vault": {}, "other": {}},
        {"alpha": ["alpha-vault", "personal"], "beta": ["personal", "other"], "gamma": ["other"]},
    )

    exit_code, lines = _session_start(base, map_path, alpha)

    assert exit_code == 3
    notices = [line for line in lines if "sharable" in line]
    assert len(notices) == 1
    assert notices[0].startswith("vg hook session-start: notice: `personal`의 `sharable`이 설정되지 않아")


@pytest.mark.usefixtures("no_recall")
def test_session_start_prints_no_notice_when_the_shared_vault_is_set(tmp_path: Path) -> None:
    base = tmp_path.resolve()
    alpha = _repo(base / "repos" / "alpha")
    map_path = _write_map(
        base,
        {"personal": {"sharable": False}, "alpha-vault": {}},
        {"alpha": ["alpha-vault", "personal"], "beta": ["personal"]},
    )

    _, lines = _session_start(base, map_path, alpha)

    assert not [line for line in lines if "sharable" in line]


def _status(base: Path, map_path: Path, *extra: str) -> str:
    from vault_graph.interface.cli.main import app

    vault = base / "vaults" / "personal"
    (vault / "wiki").mkdir(parents=True, exist_ok=True)
    home = base / "home"
    init = runner.invoke(app, ["init", "--vault", str(vault), "--vault-id", "personal", "--graph-home", str(home)])
    assert init.exit_code == 0, init.output
    result = runner.invoke(app, ["status", "--graph-home", str(home), "--vault-map", str(map_path), *extra])
    assert result.exit_code == 0, result.output
    return result.stdout


def test_vg_status_shows_the_notice_until_the_field_is_set(tmp_path: Path) -> None:
    base = tmp_path.resolve()
    unset = _write_map(base, {"personal": {}}, {"alpha": ["personal"], "beta": ["personal"]})

    lines = [line for line in _status(base, unset).splitlines() if line.startswith("vault_map_sharable_notice: ")]
    payload = json.loads(_status(base, unset, "--format", "json"))

    assert len(lines) == 1 and "`personal`의 `sharable`이 설정되지 않아" in lines[0]
    assert len(payload["vault_map_sharable_notices"]) == 1

    _write_map(base, {"personal": {"sharable": True}}, {"alpha": ["personal"], "beta": ["personal"]})
    assert "vault_map_sharable_notice" not in _status(base, unset)
