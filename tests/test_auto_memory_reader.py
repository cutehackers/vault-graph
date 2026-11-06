"""L1 auto-memory folder lookup and read-only note reading (spec 2026-11-05 §4.4.5, A-24 adapter part)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from vault_graph.interface.composition.adapters.auto_memory_reader import (
    imported_raw_hashes,
    locate_memory_folder,
    memory_folder_key,
    read_memory_notes,
)

ROOT = "/Users/someone/workspace/my.repo"


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_folder_key_replaces_every_non_alphanumeric_character() -> None:
    assert memory_folder_key(ROOT) == "-Users-someone-workspace-my-repo"


def test_claude_config_dir_sets_the_projects_base(tmp_path: Path) -> None:
    config = tmp_path / "config"
    environ = {"CLAUDE_CONFIG_DIR": str(config), "HOME": str(tmp_path / "home")}

    folder = locate_memory_folder(ROOT, environ=environ, managed_settings_path=None)

    assert folder.path == config / "projects" / "-Users-someone-workspace-my-repo" / "memory"
    assert folder.source == "default"


def test_without_claude_config_dir_the_base_is_home_dot_claude(tmp_path: Path) -> None:
    home = tmp_path / "home"

    folder = locate_memory_folder(ROOT, environ={"HOME": str(home)}, managed_settings_path=None)

    assert folder.path == home / ".claude" / "projects" / "-Users-someone-workspace-my-repo" / "memory"


def test_auto_memory_directory_in_user_settings_is_the_folder_itself(tmp_path: Path) -> None:
    config = tmp_path / "config"
    home = tmp_path / "home"
    _write(config / "settings.json", json.dumps({"autoMemoryDirectory": "~/notes/memory/"}))

    folder = locate_memory_folder(
        ROOT, environ={"CLAUDE_CONFIG_DIR": str(config), "HOME": str(home)}, managed_settings_path=None
    )

    assert folder.path == home / "notes" / "memory"
    assert folder.source == "autoMemoryDirectory"
    assert folder.settings_file == config / "settings.json"


def test_local_settings_win_over_user_settings_and_policy_wins_over_both(tmp_path: Path) -> None:
    config = tmp_path / "config"
    project = tmp_path / "project"
    _write(config / "settings.json", json.dumps({"autoMemoryDirectory": str(tmp_path / "user")}))
    _write(project / ".claude" / "settings.local.json", json.dumps({"autoMemoryDirectory": str(tmp_path / "local")}))
    environ = {"CLAUDE_CONFIG_DIR": str(config), "HOME": str(tmp_path)}

    local = locate_memory_folder(str(project), environ=environ, managed_settings_path=tmp_path / "missing.json")
    assert local.path == tmp_path / "local"

    policy_file = _write(tmp_path / "managed.json", json.dumps({"autoMemoryDirectory": str(tmp_path / "policy")}))
    policy = locate_memory_folder(str(project), environ=environ, managed_settings_path=policy_file)
    assert policy.path == tmp_path / "policy"


def test_checked_in_project_settings_are_ignored(tmp_path: Path) -> None:
    config = tmp_path / "config"
    project = tmp_path / "project"
    _write(project / ".claude" / "settings.json", json.dumps({"autoMemoryDirectory": str(tmp_path / "shared")}))

    folder = locate_memory_folder(
        str(project), environ={"CLAUDE_CONFIG_DIR": str(config), "HOME": str(tmp_path)}, managed_settings_path=None
    )

    assert folder.source == "default"


def test_unusable_auto_memory_directory_falls_back_to_the_default_folder(tmp_path: Path) -> None:
    config = tmp_path / "config"
    _write(config / "settings.json", json.dumps({"autoMemoryDirectory": "relative/memory"}))

    folder = locate_memory_folder(
        ROOT, environ={"CLAUDE_CONFIG_DIR": str(config), "HOME": str(tmp_path)}, managed_settings_path=None
    )

    assert folder.source == "default"
    assert folder.path == config / "projects" / memory_folder_key(ROOT) / "memory"


def test_long_project_root_uses_the_single_matching_hashed_folder(tmp_path: Path) -> None:
    config = tmp_path / "config"
    long_root = "/" + "a" * 250
    prefix = memory_folder_key(long_root)[:200]
    (config / "projects" / f"{prefix}-abc123" / "memory").mkdir(parents=True)

    folder = locate_memory_folder(
        long_root, environ={"CLAUDE_CONFIG_DIR": str(config), "HOME": str(tmp_path)}, managed_settings_path=None
    )

    assert folder.path == config / "projects" / f"{prefix}-abc123" / "memory"


def test_notes_skip_the_memory_index_and_carry_sha256(tmp_path: Path) -> None:
    folder = tmp_path / "memory"
    _write(folder / "MEMORY.md", "- [a](a.md)\n")
    _write(folder / "b.md", "---\nname: b\n---\nBody b\n")
    _write(folder / "a.md", "Body a\n")
    _write(folder / "notes.txt", "not a note\n")

    notes = read_memory_notes(folder)

    assert [note.name for note in notes] == ["a.md", "b.md"]
    assert notes[0].sha256 == hashlib.sha256(b"Body a\n").hexdigest()
    assert notes[0].text == "Body a\n"
    assert notes[0].path == folder / "a.md"


def test_missing_folder_has_no_notes(tmp_path: Path) -> None:
    assert read_memory_notes(tmp_path / "absent") == ()


def test_imported_hashes_come_from_source_page_raw_sha256(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    _write(vault / "wiki" / "sources" / "one.md", "---\ntype: source\nraw_sha256: abc\n---\nBody\n")
    _write(vault / "wiki" / "sources" / "two.md", "---\ntype: source\n---\nBody\n")
    _write(vault / "wiki" / "topics" / "three.md", "---\nraw_sha256: zzz\n---\nBody\n")

    assert imported_raw_hashes(vault) == {"abc": ("wiki/sources/one.md",)}
