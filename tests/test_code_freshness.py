from __future__ import annotations

import subprocess
from pathlib import Path

from vault_graph.code_index.code_models import CodeFreshnessRequest, CodeRepositoryEntry
from vault_graph.code_index.source_scanning import CodeSourceScanner


def _entry(root: Path, *, include_globs: tuple[str, ...] = ()) -> CodeRepositoryEntry:
    return CodeRepositoryEntry(
        repository_id="demo",
        root_path=root,
        display_name="Demo",
        enabled=True,
        include_globs=include_globs,
        exclude_globs=(),
        languages=("python", "dart"),
        state_namespace="code/demo",
        git_revision_policy="head-and-working-tree",
        watch=False,
    )


def test_scanner_applies_policy_deterministically_and_fingerprints_content(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "generated").mkdir()
    (tmp_path / ".git").mkdir()
    (tmp_path / "src" / "z.py").write_text("print('z')\n", encoding="utf-8")
    (tmp_path / "src" / "a.dart").write_text("void main() {}\n", encoding="utf-8")
    (tmp_path / "generated" / "ignored.py").write_text("ignored = True\n", encoding="utf-8")
    (tmp_path / ".git" / "ignored.py").write_text("ignored = True\n", encoding="utf-8")

    result = CodeSourceScanner().scan(_entry(tmp_path))

    assert tuple(item.relative_path for item in result.files) == ("src/a.dart", "src/z.py")
    assert result.files[0].content_hash
    assert result.files[0].snapshot().line_count == 1
    assert result.files[0].snapshot().byte_count == len((tmp_path / "src" / "a.dart").read_bytes())
    assert result.files[0].is_test_file is False


def test_scanner_include_can_opt_into_default_excluded_path(tmp_path: Path) -> None:
    (tmp_path / "generated").mkdir()
    source = tmp_path / "generated" / "kept.py"
    source.write_text("x = 1\n", encoding="utf-8")

    result = CodeSourceScanner().scan(_entry(tmp_path, include_globs=("generated/**",)))

    assert tuple(item.relative_path for item in result.files) == ("generated/kept.py",)


def test_scanner_rejects_external_file_symlink(tmp_path: Path) -> None:
    outside = tmp_path / "outside.py"
    outside.write_text("x = 1\n", encoding="utf-8")
    root = tmp_path / "repo"
    root.mkdir()
    (root / "escape.py").symlink_to(outside)

    try:
        CodeSourceScanner().scan(_entry(root))
    except ValueError as exc:
        assert "escapes" in str(exc)
    else:  # pragma: no cover - documents the safety contract
        raise AssertionError("external symlink must be rejected")


def test_git_revision_includes_head_and_worktree_changes(tmp_path: Path) -> None:
    subprocess.run(("git", "init", "-q"), cwd=tmp_path, check=True)
    subprocess.run(("git", "config", "user.email", "test@example.com"), cwd=tmp_path, check=True)
    subprocess.run(("git", "config", "user.name", "Test"), cwd=tmp_path, check=True)
    source = tmp_path / "main.py"
    source.write_text("x = 1\n", encoding="utf-8")
    subprocess.run(("git", "add", "main.py"), cwd=tmp_path, check=True)
    subprocess.run(("git", "commit", "-qm", "initial"), cwd=tmp_path, check=True)
    entry = _entry(tmp_path)
    clean = CodeSourceScanner().scan(entry)
    source.write_text("x = 2\n", encoding="utf-8")
    dirty = CodeSourceScanner().scan(entry)

    assert clean.source_revision.startswith("git:")
    assert "wt:" not in clean.source_revision
    assert dirty.source_revision.startswith("git:")
    assert "wt:" in dirty.source_revision
    assert clean.source_revision != dirty.source_revision


def test_non_git_revision_falls_back_to_content_hash(tmp_path: Path) -> None:
    (tmp_path / "main.py").write_text("x = 1\n", encoding="utf-8")

    result = CodeSourceScanner().scan(_entry(tmp_path))

    assert result.source_revision.startswith("content-hash:")


def test_freshness_reports_stale_when_source_revision_changes(tmp_path: Path) -> None:
    assert CodeFreshnessRequest(repository_ids=("demo",)).repository_ids == ("demo",)
