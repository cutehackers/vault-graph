from __future__ import annotations

import sqlite3
from pathlib import Path

from vault_graph.code_index.code_models import CodeIndexRequest, CodeRepositoryEntry
from vault_graph.code_index.code_projection_service import CodeProjectionService
from vault_graph.storage.interfaces.code_projection_store import CodeProjectionStore


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


def _entry_for(
    repository_id: str, root: Path, *, git_revision_policy: str = "head-and-working-tree"
) -> CodeRepositoryEntry:
    return CodeRepositoryEntry(
        repository_id=repository_id,
        root_path=root,
        display_name=repository_id,
        enabled=True,
        include_globs=("**/*.py",),
        exclude_globs=(),
        languages=("python",),
        state_namespace=f"code/{repository_id}",
        git_revision_policy=git_revision_policy,
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


def test_dry_run_uses_active_snapshot_in_a_fresh_service(tmp_path: Path) -> None:
    source = tmp_path / "main.py"
    source.write_text("def main():\n    return 1\n", encoding="utf-8")
    state_path = tmp_path / "state"
    entry = _entry(tmp_path)
    first = CodeProjectionService.for_testing(state_path=state_path, entries=(entry,))
    first.apply(CodeIndexRequest(full=True))
    second = CodeProjectionService.for_testing(state_path=state_path, entries=(entry,))
    before = second.generation_manager.active_layout(())
    assert before is not None

    report = second.apply(CodeIndexRequest(dry_run=True))

    after = second.generation_manager.active_layout(())
    assert after is not None
    assert report.files_discovered == 0
    assert after.generation_id == before.generation_id


def test_sqlite_failure_returns_partial_and_marks_active_generation(tmp_path: Path) -> None:
    source = tmp_path / "main.py"
    source.write_text("def main():\n    return 1\n", encoding="utf-8")
    state_path = tmp_path / "state"
    entry = _entry(tmp_path)
    service = CodeProjectionService.for_testing(state_path=state_path, entries=(entry,))
    service.apply(CodeIndexRequest(full=True))

    def fail_store(_database_path: Path, _policy_revision: str) -> CodeProjectionStore:
        raise sqlite3.OperationalError("simulated sqlite failure")

    service._store_factory = fail_store
    report = service.apply(CodeIndexRequest())

    assert report.status == "partial"
    assert service.status(()).state == "partial"


def test_status_reads_active_projection_without_rewriting_database(tmp_path: Path) -> None:
    source = tmp_path / "main.py"
    source.write_text("def main():\n    return 1\n", encoding="utf-8")
    state_path = tmp_path / "state"
    service = CodeProjectionService.for_testing(state_path=state_path, entries=(_entry(tmp_path),))
    service.apply(CodeIndexRequest(full=True))
    layout = service.generation_manager.active_layout(("demo",))
    assert layout is not None
    database = layout.database_path
    before = database.stat().st_mtime_ns

    report = service.status(())

    assert report.state == "fresh"
    assert database.stat().st_mtime_ns == before


def test_scoped_run_preserves_untouched_repository_namespace(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    first_source = first / "first.py"
    second_source = second / "second.py"
    first_source.write_text("def first():\n    return 1\n", encoding="utf-8")
    second_source.write_text("def second():\n    return 1\n", encoding="utf-8")
    service = CodeProjectionService.for_testing(
        state_path=tmp_path / "state",
        entries=(_entry_for("first", first), _entry_for("second", second)),
    )
    service.apply(CodeIndexRequest(full=True))
    layout = service.generation_manager.active_layout(())
    assert layout is not None
    before = layout.database_path.read_bytes()
    second_before = second_source.read_bytes()
    first_source.write_text("def first():\n    return 2\n", encoding="utf-8")

    report = service.apply(CodeIndexRequest(repository_ids=("first",)))

    assert report.repository_ids == ("first",)
    layout = service.generation_manager.active_layout(())
    assert layout is not None
    assert layout.repository_ids == ("first", "second")
    assert second_source.read_bytes() == second_before
    assert before != layout.database_path.read_bytes()


def test_verify_checks_the_staged_manifest(tmp_path: Path) -> None:
    source = tmp_path / "main.py"
    source.write_text("def main():\n    return 1\n", encoding="utf-8")
    service = CodeProjectionService.for_testing(state_path=tmp_path / "state", entries=(_entry(tmp_path),))

    report = service.apply(CodeIndexRequest(full=True, verify=True))

    assert report.status == "fresh"


def test_partial_run_is_not_reported_fresh_by_status(tmp_path: Path) -> None:
    source = tmp_path / "main.py"
    source.write_text("def main(:\n", encoding="utf-8")
    service = CodeProjectionService.for_testing(state_path=tmp_path / "state", entries=(_entry(tmp_path),))

    report = service.apply(CodeIndexRequest(full=True))

    assert report.status == "partial"
    assert service.status(()).state == "partial"


def test_head_revision_policy_still_detects_content_drift(tmp_path: Path) -> None:
    source = tmp_path / "main.py"
    source.write_text("def main():\n    return 1\n", encoding="utf-8")
    entry = _entry_for("demo", tmp_path, git_revision_policy="head")
    service = CodeProjectionService.for_testing(state_path=tmp_path / "state", entries=(entry,))
    service.apply(CodeIndexRequest(full=True))
    source.write_text("def main():\n    return 2\n", encoding="utf-8")

    assert service.status(()).state == "stale"


def test_failed_staging_keeps_previous_code_generation_active(tmp_path: Path) -> None:
    source = tmp_path / "main.py"
    source.write_text("def main():\n    return 1\n", encoding="utf-8")
    service = CodeProjectionService.for_testing(state_path=tmp_path / "state", entries=(_entry(tmp_path),))
    first = service.apply(CodeIndexRequest(full=True))
    previous = service.generation_manager.active_layout(("demo",))
    assert previous is not None

    source.write_bytes(b"def main(:\n")
    service.fail_next_apply = True
    failed = service.apply(CodeIndexRequest())

    assert failed.status in {"partial", "stale"}
    current = service.generation_manager.active_layout(("demo",))
    assert current is not None
    assert current.generation_id == previous.generation_id
    assert first.run_id != failed.run_id


def test_failed_run_persists_partial_marker_for_new_service(tmp_path: Path) -> None:
    source = tmp_path / "main.py"
    source.write_text("def main():\n    return 1\n", encoding="utf-8")
    state_path = tmp_path / "state"
    entry = _entry(tmp_path)
    service = CodeProjectionService.for_testing(state_path=state_path, entries=(entry,))
    service.apply(CodeIndexRequest(full=True))
    service.fail_next_apply = True

    failed = service.apply(CodeIndexRequest())
    fresh_process = CodeProjectionService.for_testing(state_path=state_path, entries=(entry,))

    assert failed.status == "partial"
    assert service.status(()).state == "partial"
    assert fresh_process.status(()).state == "partial"
