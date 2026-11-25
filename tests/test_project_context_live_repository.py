from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.test_project_context_service import (
    _Bindings,
    _ContextPacks,
    _Repositories,
    _VaultStatus,
)
from vault_graph.project.code.live_repository_reader import GitResult, LiveRepositoryReader
from vault_graph.project.context.project_binding import ProjectBinding
from vault_graph.project.context.project_context_models import ProjectContextRequest
from vault_graph.project.context.project_context_service import ProjectContextService


def _git(folder: Path, *arguments: str) -> str:
    return subprocess.run(("git", *arguments), cwd=folder, check=True, capture_output=True, text=True).stdout.strip()


def _repository(root: Path) -> tuple[Path, str]:
    (root / "pkg").mkdir(parents=True)
    (root / "pkg" / "flow.py").write_text("def run_request_flow():\n    return 1\n", encoding="utf-8")
    (root / "README.md").write_text("# Demo\n\nThe request flow lives in pkg.\n", encoding="utf-8")
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "test@example.com")
    _git(root, "config", "user.name", "Test")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "init")
    return root, _git(root, "rev-parse", "HEAD")


class _NoRepositories:
    def entries(self) -> tuple[()]:
        return ()

    def resolve(self, repository_id: str) -> object:
        raise ValueError(f"unknown repository_id: {repository_id}")


class _NoBindings:
    def entries(self) -> tuple[ProjectBinding, ...]:
        return ()

    def resolve(self, repository_id: str) -> ProjectBinding:
        raise ValueError(f"missing project binding for repository_id: {repository_id}")


class _VaultResolver:
    def __init__(self, vault_ids: tuple[str, ...]) -> None:
        self.vault_ids = vault_ids
        self.paths: list[Path] = []

    def resolve(self, path: Path) -> tuple[str, ...]:
        self.paths.append(path)
        return self.vault_ids


class _CountingStatus(_VaultStatus):
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    def status(self, vault_ids: tuple[str, ...]):  # type: ignore[no-untyped-def]
        self.calls.append(vault_ids)
        return super().status(vault_ids)


class _CountingPacks(_ContextPacks):
    def __init__(self) -> None:
        self.calls = 0

    def build(self, request: object):  # type: ignore[no-untyped-def]
        self.calls += 1
        return super().build(request)


class _RecordingReader(LiveRepositoryReader):
    def __init__(self) -> None:
        super().__init__()
        self.found: list[Path] = []

    def find_repository(self, path: Path):  # type: ignore[no-untyped-def]
        self.found.append(path)
        return super().find_repository(path)


def _service(
    *,
    working_folder: Path,
    vault_ids: tuple[str, ...] = (),
    repositories: object | None = None,
    bindings: object | None = None,
    reader: LiveRepositoryReader | None = None,
    status: _VaultStatus | None = None,
    packs: _ContextPacks | None = None,
) -> ProjectContextService:
    return ProjectContextService(
        repository_catalog=repositories or _NoRepositories(),  # type: ignore[arg-type]
        binding_catalog=bindings or _NoBindings(),  # type: ignore[arg-type]
        code_query_service=None,
        context_pack_builder=packs or _ContextPacks(),
        vault_status_service=status or _VaultStatus(),
        live_code_reader=reader or LiveRepositoryReader(),
        vault_resolver=_VaultResolver(vault_ids),
        working_folder=lambda: working_folder,
    )


def _files(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file() and not path.is_symlink()
    }


def test_zero_registered_repositories_return_live_code_evidence(tmp_path: Path) -> None:
    root, head = _repository(tmp_path / "demo")
    service = _service(working_folder=tmp_path, vault_ids=("vault",))

    context = service.build(ProjectContextRequest(task="run request flow", cwd=str(root / "pkg")))

    assert context.repository_id == "git:demo"
    assert context.code_evidence
    first = context.code_evidence[0]
    assert first.relative_path == "pkg/flow.py"
    assert first.title.endswith("run_request_flow")
    assert first.start_line == 1
    assert first.revision == f"git:{head}"
    assert first.repository_id == "git:demo"
    assert first.evidence_id.startswith("code:")
    assert set(first.reasons) == {"live_symbol_match", "working_tree"}
    line = [item for item in context.code_evidence if "live_line_match" in item.reasons]
    assert [item.evidence_id for item in line] == ["code:line:README.md:3"]
    assert context.impact_evidence == ()
    assert context.test_evidence == ()
    assert "code_live_read" in {warning.code for warning in context.warnings}
    assert context.binding is not None
    assert context.binding.repository_id == "git:demo"
    assert context.binding.vault_ids == ("vault",)
    assert context.vault_evidence


def test_live_evidence_paths_stay_relative(tmp_path: Path) -> None:
    root, _ = _repository(tmp_path / "demo")
    service = _service(working_folder=tmp_path)

    context = service.build(ProjectContextRequest(task="run request flow", cwd=str(root)))

    text = repr(context)
    assert str(tmp_path) not in text


def test_project_path_wins_over_cwd(tmp_path: Path) -> None:
    first, _ = _repository(tmp_path / "first")
    second, _ = _repository(tmp_path / "second")
    service = _service(working_folder=tmp_path)

    context = service.build(ProjectContextRequest(task="run request flow", project_path=str(first), cwd=str(second)))

    assert context.repository_id == "git:first"


@pytest.mark.parametrize("kind", ["outside", "missing"])
def test_outside_git_raises_not_a_git_repository_without_registration_hint(tmp_path: Path, kind: str) -> None:
    folder = tmp_path / "plain"
    if kind == "outside":
        folder.mkdir()
    service = _service(working_folder=tmp_path)

    with pytest.raises(ValueError) as caught:
        service.build(ProjectContextRequest(task="run request flow", cwd=str(folder)))

    message = str(caught.value)
    assert message.startswith("not_a_git_repository")
    for word in ("register", "bind", "repository_id", str(tmp_path)):
        assert word not in message


def test_git_that_cannot_run_raises_not_a_git_repository(tmp_path: Path) -> None:
    def broken(folder: Path, arguments: tuple[str, ...], timeout_s: float) -> GitResult:
        del folder, arguments, timeout_s
        return GitResult(returncode=None, stdout="")

    service = _service(working_folder=tmp_path, reader=LiveRepositoryReader(runner=broken))

    with pytest.raises(ValueError, match="^not_a_git_repository; git could not be run"):
        service.build(ProjectContextRequest(task="run request flow", cwd=str(tmp_path)))


def test_no_vault_leaves_binding_null_and_reads_no_vault(tmp_path: Path) -> None:
    root, _ = _repository(tmp_path / "demo")
    status = _CountingStatus()
    packs = _CountingPacks()
    service = _service(working_folder=tmp_path, status=status, packs=packs)

    context = service.build(ProjectContextRequest(task="run request flow", cwd=str(root)))

    assert context.binding is None
    assert context.vault_evidence == ()
    assert "project_vault_scope_unresolved" in {warning.code for warning in context.warnings}
    assert status.calls == []
    assert packs.calls == 0
    assert context.code_evidence


def test_repository_id_skips_live_reading(tmp_path: Path) -> None:
    root, _ = _repository(tmp_path / "demo")
    reader = _RecordingReader()
    registered = tmp_path / "registered"
    service = _service(
        working_folder=root,
        repositories=_Repositories(registered),
        bindings=_Bindings(),
        reader=reader,
    )
    registered.mkdir()

    context = service.build(ProjectContextRequest(task="run", repository_id="demo", cwd=str(root)))

    assert context.repository_id == "demo"
    assert reader.found == []


def test_path_inside_registered_repository_keeps_registered_path(tmp_path: Path) -> None:
    root, _ = _repository(tmp_path / "demo")
    reader = _RecordingReader()
    service = _service(
        working_folder=tmp_path,
        repositories=_Repositories(root),
        bindings=_Bindings(),
        reader=reader,
    )

    context = service.build(ProjectContextRequest(task="run", cwd=str(root / "pkg")))

    assert context.repository_id == "demo"
    assert "code_index_unavailable" in {warning.code for warning in context.warnings}
    assert reader.found == []


def test_path_inside_registered_repository_without_binding_keeps_scope_error(tmp_path: Path) -> None:
    root, _ = _repository(tmp_path / "demo")
    service = _service(working_folder=tmp_path, repositories=_Repositories(root), bindings=_NoBindings())

    with pytest.raises(ValueError, match="missing project binding"):
        service.build(ProjectContextRequest(task="run", cwd=str(root)))


def test_no_arguments_prefer_the_single_bound_registered_repository(tmp_path: Path) -> None:
    root, _ = _repository(tmp_path / "demo")
    registered = tmp_path / "registered"
    registered.mkdir()
    service = _service(working_folder=root, repositories=_Repositories(registered), bindings=_Bindings())

    context = service.build(ProjectContextRequest(task="run"))

    assert context.repository_id == "demo"


def test_no_arguments_without_registered_repository_read_the_working_folder(tmp_path: Path) -> None:
    root, _ = _repository(tmp_path / "demo")
    service = _service(working_folder=root / "pkg")

    context = service.build(ProjectContextRequest(task="run request flow"))

    assert context.repository_id == "git:demo"
    assert context.code_evidence


def test_no_arguments_outside_git_raise_not_a_git_repository(tmp_path: Path) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    service = _service(working_folder=plain)

    with pytest.raises(ValueError, match="^not_a_git_repository"):
        service.build(ProjectContextRequest(task="run request flow"))


def test_live_reading_leaves_repository_and_graph_home_unchanged(tmp_path: Path) -> None:
    root, head = _repository(tmp_path / "demo")
    (root / "pkg" / "flow.py").write_text("def run_request_flow():\n    return 2\n", encoding="utf-8")
    graph_home = tmp_path / "graph-home"
    graph_home.mkdir()
    (graph_home / "marker").write_text("x", encoding="utf-8")
    before_repository = _files(root)
    before_home = _files(graph_home)
    service = _service(working_folder=tmp_path)

    context = service.build(ProjectContextRequest(task="run request flow", cwd=str(root)))

    assert _files(root) == before_repository
    assert _files(graph_home) == before_home
    assert context.code_evidence[0].revision == f"git:{head}"
    assert "working_tree" in context.code_evidence[0].reasons


def test_repository_without_commits_has_null_revision(tmp_path: Path) -> None:
    root = tmp_path / "fresh"
    root.mkdir()
    (root / "flow.py").write_text("def run_request_flow():\n    return 1\n", encoding="utf-8")
    _git(root, "init", "-q")
    service = _service(working_folder=tmp_path)

    context = service.build(ProjectContextRequest(task="run request flow", cwd=str(root)))

    assert context.code_evidence
    assert context.code_evidence[0].revision is None
