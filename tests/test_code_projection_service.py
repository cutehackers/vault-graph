from __future__ import annotations

from pathlib import Path

from vault_graph.code_index.code_models import CodeIndexRequest, CodeRepositoryEntry
from vault_graph.code_index.code_projection_service import CodeProjectionService


def _entry(root: Path) -> CodeRepositoryEntry:
    return CodeRepositoryEntry(
        repository_id="demo",
        root_path=root,
        display_name="Demo",
        enabled=True,
        include_globs=("**/*.py",),
        exclude_globs=(),
        languages=("python",),
        state_namespace="code/demo",
        git_revision_policy="head-and-working-tree",
        watch=False,
    )


def test_full_then_incremental_build_and_delete(tmp_path: Path) -> None:
    source = tmp_path / "main.py"
    source.write_text("def main():\n    return 1\n", encoding="utf-8")
    service = CodeProjectionService.for_testing(state_path=tmp_path / "state", entries=(_entry(tmp_path),))

    first = service.apply(CodeIndexRequest(full=True))
    source.write_text("def main():\n    return 2\n", encoding="utf-8")
    second = service.apply(CodeIndexRequest())
    source.unlink()
    third = service.apply(CodeIndexRequest())

    assert first.mode == "full"
    assert first.files_parsed == 1
    assert second.mode == "incremental"
    assert second.files_parsed == 1
    assert third.files_deleted == 1
    assert service.status(()).state in {"fresh", "partial"}


def test_dry_run_does_not_create_or_activate_code_state(tmp_path: Path) -> None:
    source = tmp_path / "main.py"
    source.write_text("def main():\n    return 1\n", encoding="utf-8")
    state_path = tmp_path / "state"
    service = CodeProjectionService.for_testing(state_path=state_path, entries=(_entry(tmp_path),))

    report = service.apply(CodeIndexRequest(dry_run=True))

    assert report.status == "stale"
    assert not (state_path / "projections" / "code" / "active.json").exists()
    assert not (state_path / "projections" / "code" / "generations").exists()


def test_status_reads_active_projection_without_rewriting_database(tmp_path: Path) -> None:
    source = tmp_path / "main.py"
    source.write_text("def main():\n    return 1\n", encoding="utf-8")
    state_path = tmp_path / "state"
    service = CodeProjectionService.for_testing(state_path=state_path, entries=(_entry(tmp_path),))
    service.apply(CodeIndexRequest(full=True))
    database = service.generation_manager.active_layout(("demo",)).database_path
    before = database.stat().st_mtime_ns

    report = service.status(())

    assert report.state == "fresh"
    assert database.stat().st_mtime_ns == before


def test_failed_staging_keeps_previous_code_generation_active(tmp_path: Path) -> None:
    source = tmp_path / "main.py"
    source.write_text("def main():\n    return 1\n", encoding="utf-8")
    service = CodeProjectionService.for_testing(state_path=tmp_path / "state", entries=(_entry(tmp_path),))
    first = service.apply(CodeIndexRequest(full=True))
    previous = service.generation_manager.active_layout(("demo",))

    source.write_bytes(b"def main(:\n")
    service.fail_next_apply = True
    failed = service.apply(CodeIndexRequest())

    assert failed.status in {"partial", "stale"}
    assert service.generation_manager.active_layout(("demo",)).generation_id == previous.generation_id
    assert first.run_id != failed.run_id
