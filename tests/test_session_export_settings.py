"""Graph Home `configs/session-export.json` format (spec 2026-11-05 §4.2.4 설정)."""

from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest

from vault_graph.errors import CatalogError
from vault_graph.operation.scope.session_export_settings import (
    SessionExportSettings,
    load_session_export_settings,
    save_session_export_settings,
    session_export_settings_path,
)


def _write(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_settings_path_is_under_graph_home_configs(tmp_path: Path) -> None:
    assert session_export_settings_path(tmp_path) == tmp_path / "configs" / "session-export.json"


def test_missing_file_means_no_export(tmp_path: Path) -> None:
    path = tmp_path / "configs" / "session-export.json"

    assert load_session_export_settings(path) is None
    assert not path.exists()


def test_round_trip_keeps_values_and_writes_owner_only_file(tmp_path: Path) -> None:
    path = session_export_settings_path(tmp_path / "home")
    settings = SessionExportSettings(path=tmp_path / "export", agents=("claude-code",), raw=False)

    save_session_export_settings(path, settings)

    assert load_session_export_settings(path) == settings
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert json.loads(path.read_text(encoding="utf-8")) == {
        "path": str(tmp_path / "export"),
        "agents": ["claude-code"],
        "raw": False,
    }


def test_raw_defaults_to_true(tmp_path: Path) -> None:
    path = _write(tmp_path / "s.json", {"path": str(tmp_path / "out"), "agents": ["claude-code", "codex"]})

    assert load_session_export_settings(path) == SessionExportSettings(
        path=tmp_path / "out", agents=("claude-code", "codex"), raw=True
    )


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ([], "JSON object"),
        ({"agents": ["claude-code"]}, "missing keys"),
        ({"path": "/x", "agents": ["claude-code"], "extra": 1}, "unknown keys"),
        ({"path": "relative/out", "agents": ["claude-code"]}, "absolute"),
        ({"path": "/x", "agents": []}, "agents"),
        ({"path": "/x", "agents": ["gemini"]}, "agents"),
        ({"path": "/x", "agents": ["claude-code", "claude-code"]}, "agents"),
        ({"path": "/x", "agents": "claude-code"}, "agents"),
        ({"path": "/x", "agents": ["claude-code"], "raw": "yes"}, "raw"),
    ],
)
def test_bad_settings_name_the_problem_and_path(tmp_path: Path, payload: object, message: str) -> None:
    path = _write(tmp_path / "session-export.json", payload)

    with pytest.raises(CatalogError, match=message) as caught:
        load_session_export_settings(path)
    assert str(path) in str(caught.value)


def test_invalid_json_is_an_error(tmp_path: Path) -> None:
    path = tmp_path / "session-export.json"
    path.write_text("{not json", encoding="utf-8")

    with pytest.raises(CatalogError, match="not valid JSON"):
        load_session_export_settings(path)


def test_save_rejects_relative_path(tmp_path: Path) -> None:
    with pytest.raises(CatalogError, match="absolute"):
        save_session_export_settings(
            tmp_path / "s.json", SessionExportSettings(path=Path("out"), agents=("claude-code",), raw=True)
        )
