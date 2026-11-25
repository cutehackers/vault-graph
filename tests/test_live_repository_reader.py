from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from vault_graph.project.code.live_repository_reader import (
    GitResult,
    LiveRepositoryReader,
    extract_terms,
)


def _git(folder: Path, *arguments: str) -> str:
    return subprocess.run(
        ("git", *arguments),
        cwd=folder,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _repository(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "test@example.com")
    _git(root, "config", "user.name", "Test")
    return root


def _commit(root: Path) -> str:
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "init")
    return _git(root, "rev-parse", "HEAD")


def _write(root: Path, relative: str, text: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_find_repository_returns_root_label_and_head(tmp_path: Path) -> None:
    root = _repository(tmp_path / "demo")
    _write(root, "pkg/flow.py", "def run_request_flow():\n    return 1\n")
    head = _commit(root)

    repository = LiveRepositoryReader().find_repository(root / "pkg")

    assert repository is not None
    assert repository.root_path == root.resolve()
    assert repository.label == "git:demo"
    assert repository.head == head


def test_find_repository_is_none_outside_git_and_for_missing_paths(tmp_path: Path) -> None:
    outside = tmp_path / "plain"
    outside.mkdir()
    reader = LiveRepositoryReader()

    assert reader.find_repository(outside) is None
    assert reader.find_repository(tmp_path / "missing") is None
    assert reader.git_available() is True


def test_git_available_is_false_when_git_cannot_run(tmp_path: Path) -> None:
    def broken(folder: Path, arguments: tuple[str, ...], timeout_s: float) -> GitResult:
        del folder, arguments, timeout_s
        return GitResult(returncode=None, stdout="", timed_out=False)

    reader = LiveRepositoryReader(runner=broken)

    assert reader.find_repository(tmp_path) is None
    assert reader.git_available() is False


def test_find_repository_without_commits_has_no_head(tmp_path: Path) -> None:
    root = _repository(tmp_path / "empty")

    repository = LiveRepositoryReader().find_repository(root)

    assert repository is not None
    assert repository.head is None


def test_linked_worktree_uses_main_worktree_folder_name(tmp_path: Path) -> None:
    root = _repository(tmp_path / "mainrepo")
    _write(root, "flow.py", "def run_request_flow():\n    return 1\n")
    _commit(root)
    linked = tmp_path / "linked-checkout"
    _git(root, "worktree", "add", "-q", str(linked), "-b", "side")

    repository = LiveRepositoryReader().find_repository(linked)

    assert repository is not None
    assert repository.root_path == linked.resolve()
    assert repository.label == "git:mainrepo"


def test_search_returns_symbol_hits_before_line_hits(tmp_path: Path) -> None:
    root = _repository(tmp_path / "demo")
    _write(root, "pkg/flow.py", "import os\n\n\ndef run_request_flow():\n    return os.getcwd()\n")
    _write(root, "docs/notes.md", "# Notes\n\nThe request flow starts here.\n")
    _commit(root)
    reader = LiveRepositoryReader()
    repository = reader.find_repository(root)
    assert repository is not None

    result = reader.search(repository, "run request flow", limit=10)

    assert result.hits, result.warnings
    assert result.hits[0].kind == "symbol"
    assert result.hits[0].relative_path == "pkg/flow.py"
    assert result.hits[0].title.endswith("run_request_flow")
    assert result.hits[0].start_line == 4
    assert result.hits[0].symbol_id
    line_hits = [hit for hit in result.hits if hit.kind == "line"]
    assert [hit.relative_path for hit in line_hits] == ["docs/notes.md"]
    assert line_hits[0].start_line == 3
    kinds = [hit.kind for hit in result.hits]
    assert kinds == sorted(kinds, key=lambda kind: 0 if kind == "symbol" else 1)
    assert not result.truncated


def test_search_reads_files_from_git_and_skips_ignored_symlinks_and_large_files(tmp_path: Path) -> None:
    root = _repository(tmp_path / "demo")
    _write(root, ".gitignore", ".venv/\n")
    _write(root, "flow.py", "def flow_handler():\n    return 1\n")
    venv_bin = root / ".venv" / "bin"
    venv_bin.mkdir(parents=True)
    (venv_bin / "python").symlink_to("/usr/bin/env")
    _write(root, ".venv/lib/flow_ignored.py", "def flow_ignored():\n    return 1\n")
    outside = tmp_path / "outside.py"
    outside.write_text("def flow_outside():\n    return 1\n", encoding="utf-8")
    (root / "flow_link.py").symlink_to(outside)
    _write(root, "big_flow.py", "def flow_big():\n    return 1\n" + "# flow\n" * 80_000)
    _write(root, "broken_flow.py", "def flow_broken(:\n    flow\n")
    _commit(root)
    _write(root, "new_flow.py", "def flow_new():\n    return 1\n")
    reader = LiveRepositoryReader()
    repository = reader.find_repository(root)
    assert repository is not None

    result = reader.search(repository, "flow", limit=20)

    paths = {hit.relative_path for hit in result.hits}
    assert "flow.py" in paths
    assert "new_flow.py" in paths
    assert "broken_flow.py" in paths
    assert not any(path.startswith(".venv") for path in paths)
    assert "flow_link.py" not in paths
    assert "big_flow.py" not in paths
    assert "code_live_files_skipped" in result.warnings
    assert all(not Path(path).is_absolute() for path in paths)


def test_search_caps_parsed_files_and_reports_truncation(tmp_path: Path) -> None:
    root = _repository(tmp_path / "demo")
    for index in range(60):
        _write(root, f"mod_{index:02d}.py", f"def widget_{index:02d}():\n    return {index}\n")
    _commit(root)
    reader = LiveRepositoryReader()
    repository = reader.find_repository(root)
    assert repository is not None

    result = reader.search(repository, "widget", limit=100)

    assert result.files_parsed <= 50
    assert result.truncated
    assert "code_live_read_truncated" in result.warnings


def test_search_stops_on_git_timeout_and_returns_partial_result(tmp_path: Path) -> None:
    root = _repository(tmp_path / "demo")
    _write(root, "alpha.py", "def alpha_task():\n    return 1\n")
    _commit(root)
    real = LiveRepositoryReader()
    repository = real.find_repository(root)
    assert repository is not None

    def slow_grep(folder: Path, arguments: tuple[str, ...], timeout_s: float) -> GitResult:
        if arguments and arguments[0] == "grep":
            return GitResult(returncode=None, stdout="", timed_out=True)
        return real.run(folder, arguments, timeout_s)

    result = LiveRepositoryReader(runner=slow_grep).search(repository, "alpha task", limit=10)

    assert result.truncated
    assert "code_live_read_truncated" in result.warnings


def test_search_without_terms_or_matches_succeeds_with_warnings(tmp_path: Path) -> None:
    root = _repository(tmp_path / "demo")
    _write(root, "alpha.py", "def alpha():\n    return 1\n")
    _commit(root)
    reader = LiveRepositoryReader()
    repository = reader.find_repository(root)
    assert repository is not None

    no_terms = reader.search(repository, "??", limit=10)
    no_match = reader.search(repository, "zzqqxx", limit=10)

    assert no_terms.hits == ()
    assert "code_live_no_terms" in no_terms.warnings
    assert no_match.hits == ()
    assert "code_live_no_match" in no_match.warnings


def test_extract_terms_keeps_first_eight_and_drops_stop_words() -> None:
    terms = extract_terms("Fix the alpha beta gamma delta epsilon zeta eta theta iota kappa 요청 흐름 a1")

    assert len(terms) == 8
    assert terms[0] == "fix"
    assert "the" not in terms
    assert "iota" not in terms


def test_extract_terms_keeps_korean_chunks() -> None:
    assert extract_terms("요청 흐름 고치기") == ("요청", "흐름", "고치기")


def test_search_does_not_write_repository(tmp_path: Path) -> None:
    root = _repository(tmp_path / "demo")
    _write(root, "flow.py", "def flow_handler():\n    return 1\n")
    _commit(root)
    _write(root, "flow.py", "def flow_handler():\n    return 2\n")
    before = {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file() and not path.is_symlink()
    }
    reader = LiveRepositoryReader()
    repository = reader.find_repository(root)
    assert repository is not None

    reader.search(repository, "flow handler", limit=10)

    after = {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file() and not path.is_symlink()
    }
    assert after == before


@pytest.mark.parametrize("command", ["status", "add", "commit"])
def test_reader_never_runs_writing_git_commands(tmp_path: Path, command: str) -> None:
    root = _repository(tmp_path / "demo")
    _write(root, "flow.py", "def flow_handler():\n    return 1\n")
    _commit(root)
    seen: list[str] = []
    real = LiveRepositoryReader()

    def recording(folder: Path, arguments: tuple[str, ...], timeout_s: float) -> GitResult:
        seen.append(arguments[0])
        return real.run(folder, arguments, timeout_s)

    reader = LiveRepositoryReader(runner=recording)
    repository = reader.find_repository(root)
    assert repository is not None
    reader.search(repository, "flow handler", limit=10)

    assert command not in seen
    assert set(seen) <= {"rev-parse", "ls-files", "grep", "--version"}
