"""Read vault-map.json version 2 and find the project of a folder (spec 4.2.2, A-8).

Fixtures in tests/fixtures/vault_map keep only the structure of the real map. Paths use the
``{base}`` token, which each test replaces with its own temporary folder in a copy.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest

from vault_graph.interface.composition.query_scope_resolution import resolve_project_vaults
from vault_graph.operation.integration.vault_map import (
    DEFAULT_VAULT_MAP_PATH,
    VAULT_MAP_ENV,
    MappedVault,
    VaultMap,
    VaultMapError,
    load_vault_map,
    open_vault_map,
    vault_map_path,
)
from vault_graph.operation.scope.vault_catalog import VaultCatalog, VaultCatalogEntry
from vault_graph.project.context.project_binding import ProjectBinding
from vault_graph.project.context.project_binding_reader import VaultMapReader

FIXTURES = Path(__file__).parent / "fixtures" / "vault_map"


def fixture_hashes() -> dict[str, str]:
    return {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(FIXTURES.iterdir())}


@pytest.fixture(autouse=True)
def fixture_files_stay_unchanged() -> Iterator[None]:
    before = fixture_hashes()
    yield
    assert fixture_hashes() == before


def render_fixture(name: str, base: Path, target: Path | None = None) -> Path:
    """Copy a fixture with ``{base}`` replaced. The fixture file itself is only read."""
    text = (FIXTURES / name).read_text(encoding="utf-8").replace("{base}", str(base))
    destination = target or base / "map" / name
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(text, encoding="utf-8")
    return destination


def git(folder: Path, *arguments: str) -> None:
    subprocess.run(
        ["git", "-C", str(folder), "-c", "user.name=t", "-c", "user.email=t@example.test", *arguments],
        check=True,
        capture_output=True,
    )


def make_repo(path: Path, *, origin: str | None = None) -> Path:
    path.mkdir(parents=True)
    git(path, "init", "-q")
    if origin is not None:
        git(path, "remote", "add", "origin", origin)
    return path


def make_vaults(base: Path) -> None:
    for name in ("personal", "team"):
        (base / "vaults" / name / "wiki").mkdir(parents=True)


@pytest.fixture
def base(tmp_path: Path) -> Path:
    # Resolve once so macOS /var -> /private/var does not hide path equality.
    return tmp_path.resolve()


@pytest.fixture
def mapped(base: Path) -> VaultMap:
    make_vaults(base)
    return load_vault_map(render_fixture("vault-map-v2.json", base))


def test_loads_version_two_vaults_and_projects(mapped: VaultMap, base: Path) -> None:
    assert mapped.version == 2
    assert mapped.vaults == (
        MappedVault(name="personal", path=base / "vaults" / "personal", role="personal"),
        MappedVault(name="team", path=base / "vaults" / "team", role="team"),
    )
    assert isinstance(mapped, VaultMapReader)


@pytest.mark.parametrize("name", ["vault-map-v1.json", "vault-map-broken.json", "vault-map-bad-shape.json"])
def test_other_version_or_broken_file_is_refused(base: Path, name: str) -> None:
    path = render_fixture(name, base)
    before = path.read_bytes()

    with pytest.raises(VaultMapError):
        load_vault_map(path)
    opened = open_vault_map(path)

    assert opened.state == "invalid"
    assert opened.vault_map is None
    assert opened.warning is not None and str(path) in opened.warning
    assert path.read_bytes() == before


def test_missing_file_opens_as_missing_without_warning_or_creating_it(base: Path) -> None:
    path = base / "nowhere" / "vault-map.json"

    opened = open_vault_map(path)

    assert opened.state == "missing"
    assert opened.vault_map is None
    assert opened.warning is None
    assert not path.parent.exists()


def test_open_reports_loaded_version(base: Path) -> None:
    opened = open_vault_map(render_fixture("vault-map-v2.json", base))

    assert opened.state == "loaded"
    assert opened.version == 2
    assert opened.vault_map is not None


def test_path_prefers_option_then_environment_then_default(base: Path) -> None:
    option = base / "option.json"
    environment = base / "environment.json"

    assert vault_map_path(option, environ={VAULT_MAP_ENV: str(environment)}) == option
    assert vault_map_path(None, environ={VAULT_MAP_ENV: str(environment)}) == environment
    assert vault_map_path(None, environ={}) == DEFAULT_VAULT_MAP_PATH.expanduser()
    assert DEFAULT_VAULT_MAP_PATH.parts[-3:] == (".claude", "vault-builder", "vault-map.json")


def test_default_path_follows_claude_config_dir_like_vault_builder(base: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # vault-builder writes the map under $CLAUDE_CONFIG_DIR/vault-builder when the variable is non-empty
    # (vault-builder tools/vault_migration/installing.py resolve_user_paths).
    home = base / "home"
    config = home / "cfg"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv(VAULT_MAP_ENV, raising=False)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(config))
    expected = config / "vault-builder" / "vault-map.json"

    assert vault_map_path(None, environ={"CLAUDE_CONFIG_DIR": str(config)}) == expected
    assert vault_map_path(None) == expected
    assert vault_map_path(None, environ={"CLAUDE_CONFIG_DIR": "~/cfg"}) == expected
    assert vault_map_path(None, environ={"CLAUDE_CONFIG_DIR": ""}) == home / ".claude" / "vault-builder" / (
        "vault-map.json"
    )
    assert vault_map_path(None, environ={}) == home / ".claude" / "vault-builder" / "vault-map.json"
    environment = base / "environment.json"
    both = {VAULT_MAP_ENV: str(environment), "CLAUDE_CONFIG_DIR": str(config)}
    assert vault_map_path(None, environ=both) == environment


def test_cli_vault_map_help_names_the_claude_config_dir_default() -> None:
    from vault_graph.interface.cli.main import VAULT_MAP_OPTION_HELP

    assert "$CLAUDE_CONFIG_DIR/vault-builder/vault-map.json" in VAULT_MAP_OPTION_HELP
    assert "$HOME/.claude/vault-builder/vault-map.json" in VAULT_MAP_OPTION_HELP


def test_root_stage_finds_project_from_root_and_subfolder(mapped: VaultMap, base: Path) -> None:
    repo = make_repo(base / "repos" / "alpha")
    (repo / "src" / "deep").mkdir(parents=True)

    for cwd in (repo, repo / "src" / "deep"):
        match = mapped.find_project(cwd)
        assert (match.project_id, match.stage) == ("alpha", "root")
        assert [vault.name for vault in mapped.vaults_for(cwd)] == ["personal"]


def test_worktree_and_symlink_cwd_find_the_same_project(mapped: VaultMap, base: Path) -> None:
    repo = make_repo(base / "repos" / "alpha")
    git(repo, "commit", "-q", "--allow-empty", "-m", "first")
    worktree = base / "worktrees" / "alpha-feature"
    git(repo, "worktree", "add", "-q", "-b", "feature", str(worktree))
    link = base / "links" / "alpha"
    link.parent.mkdir()
    link.symlink_to(repo, target_is_directory=True)

    for cwd in (worktree, link):
        match = mapped.find_project(cwd)
        assert (match.project_id, match.stage) == ("alpha", "root")


def test_remote_stage_matches_normalized_remote_and_keeps_vault_order(mapped: VaultMap, base: Path) -> None:
    repo = make_repo(base / "repos" / "beta", origin="git@GIT.example.test:org/beta.git")

    match = mapped.find_project(repo)

    assert (match.project_id, match.stage) == ("beta", "remote")
    assert [vault.name for vault in mapped.vaults_for(repo)] == ["team", "personal"]


def test_name_stage_uses_folder_name(mapped: VaultMap, base: Path) -> None:
    repo = make_repo(base / "repos" / "gamma")

    match = mapped.find_project(repo)

    assert (match.project_id, match.stage) == ("gamma", "name")


def test_two_matches_in_one_stage_decide_nothing(mapped: VaultMap, base: Path) -> None:
    repo = make_repo(base / "repos" / "delta-c", origin="ssh://git@git.example.test/org/delta.git")

    match = mapped.find_project(repo)

    assert match.project_id is None
    assert match.candidates == ("delta", "delta-copy")
    assert mapped.vaults_for(repo) == ()


def test_outside_git_or_unknown_repo_finds_nothing(mapped: VaultMap, base: Path) -> None:
    plain = base / "plain"
    plain.mkdir()
    unknown = make_repo(base / "repos" / "unknown")

    for cwd in (plain, unknown):
        match = mapped.find_project(cwd)
        assert match.project_id is None
        assert match.candidates == ()
        assert mapped.vaults_for(cwd) == ()


def _catalog(base: Path, **roots: Path) -> VaultCatalog:
    entries = [VaultCatalogEntry.from_root(vault_id=vault_id, root_path=root) for vault_id, root in roots.items()]
    return VaultCatalog.from_entries(entries=entries, active_vault_id=entries[0].vault_id)


class _Bindings:
    def __init__(self, *bindings: ProjectBinding) -> None:
        self._bindings = bindings

    def entries(self) -> tuple[ProjectBinding, ...]:
        return self._bindings

    def resolve(self, repository_id: str) -> ProjectBinding:
        for binding in self._bindings:
            if binding.repository_id == repository_id:
                return binding
        raise ValueError(f"missing project binding for repository_id: {repository_id}")


def test_map_project_wins_and_is_matched_to_registered_vaults_by_real_path(mapped: VaultMap, base: Path) -> None:
    repo = make_repo(base / "repos" / "beta", origin="https://git.example.test/org/beta.git")
    catalog = _catalog(base, main=base / "vaults" / "personal")
    bindings = _Bindings(ProjectBinding(repository_id="beta-repo", vault_ids=("main",)))

    result = resolve_project_vaults(
        repo,
        vault_map=mapped,
        vault_catalog=catalog,
        bindings=bindings,
        repository_roots={"beta-repo": repo},
    )

    assert result.source == "vault-map"
    assert result.project_id == "beta"
    assert result.vault_ids == ("main",)
    assert [vault.name for vault in result.unregistered_vaults] == ["team"]


def test_project_bindings_are_used_when_map_is_missing_or_has_no_project(mapped: VaultMap, base: Path) -> None:
    repo = make_repo(base / "repos" / "unknown")
    catalog = _catalog(base, main=base / "vaults" / "personal")
    bindings = _Bindings(ProjectBinding(repository_id="unknown-repo", vault_ids=("main",)))
    (repo / "sub").mkdir()

    for vault_map in (mapped, None):
        result = resolve_project_vaults(
            repo / "sub",
            vault_map=vault_map,
            vault_catalog=catalog,
            bindings=bindings,
            repository_roots={"unknown-repo": repo},
        )
        assert (result.source, result.project_id, result.vault_ids) == ("project-bindings", "unknown-repo", ("main",))


def test_ambiguous_map_project_does_not_fall_back(mapped: VaultMap, base: Path) -> None:
    repo = make_repo(base / "repos" / "delta-c", origin="git@git.example.test:org/delta.git")
    catalog = _catalog(base, main=base / "vaults" / "personal")
    bindings = _Bindings(ProjectBinding(repository_id="delta-repo", vault_ids=("main",)))

    result = resolve_project_vaults(
        repo,
        vault_map=mapped,
        vault_catalog=catalog,
        bindings=bindings,
        repository_roots={"delta-repo": repo},
    )

    assert result.source is None
    assert result.vault_ids == ()
    assert result.reason is not None and "delta, delta-copy" in result.reason


def test_nothing_found_reports_reason(base: Path) -> None:
    make_vaults(base)
    plain = base / "plain"
    plain.mkdir()
    catalog = _catalog(base, main=base / "vaults" / "personal")

    result = resolve_project_vaults(plain, vault_map=None, vault_catalog=catalog)

    assert result.source is None
    assert result.vault_ids == ()
    assert result.reason is not None


def test_reading_the_map_does_not_change_it(base: Path) -> None:
    make_vaults(base)
    path = render_fixture("vault-map-v2.json", base)
    before = json.loads(path.read_text(encoding="utf-8"))
    repo = make_repo(base / "repos" / "alpha")

    load_vault_map(path).vaults_for(repo)

    assert json.loads(path.read_text(encoding="utf-8")) == before


def _write_map(base: Path, projects: dict[str, object]) -> Path:
    """Write a version 2 map with the personal and team Vaults and the given projects."""
    path = base / "map" / "vault-map-default-write.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "version": 2,
        "vaults": {
            "personal": {"path": str(base / "vaults" / "personal"), "role": "personal"},
            "team": {"path": str(base / "vaults" / "team"), "role": "team"},
        },
        "projects": projects,
    }
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_default_write_vault_is_given_with_the_project_match(base: Path) -> None:
    make_vaults(base)
    repo = make_repo(base / "repos" / "alpha")
    path = _write_map(
        base, {"alpha": {"root": str(repo), "vaults": ["personal", "team"], "default_write_vault": "team"}}
    )

    vault_map = load_vault_map(path)
    match = vault_map.find_project(repo)

    assert match.default_write_vault == MappedVault(name="team", path=base / "vaults" / "team", role="team")
    assert vault_map.default_write_vaults == {"alpha": "team"}
    assert vault_map.warnings == ()


def test_map_without_default_write_vault_gives_none_and_no_warning(mapped: VaultMap, base: Path) -> None:
    repo = make_repo(base / "repos" / "alpha")

    assert mapped.find_project(repo).default_write_vault is None
    assert mapped.default_write_vaults == {name: None for name in ("alpha", "beta", "delta", "delta-copy", "gamma")}
    assert mapped.warnings == ()


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (7, "is not a string"),
        (None, "is not a string"),
        (["team"], "is not a string"),
        ("team", "is not in the project vaults"),
        ("ghost", "is not in the project vaults"),
    ],
)
def test_bad_default_write_vault_is_ignored_with_a_warning(base: Path, value: object, expected: str) -> None:
    make_vaults(base)
    repo = make_repo(base / "repos" / "alpha")
    path = _write_map(base, {"alpha": {"root": str(repo), "vaults": ["personal"], "default_write_vault": value}})

    opened = open_vault_map(path)

    assert opened.state == "loaded"
    assert opened.warning is None
    assert opened.vault_map is not None
    match = opened.vault_map.find_project(repo)
    assert match.project_id == "alpha"
    assert [vault.name for vault in match.vaults] == ["personal"]
    assert match.default_write_vault is None
    assert opened.vault_map.default_write_vaults == {"alpha": None}
    (warning,) = opened.vault_map.warnings
    assert "alpha" in warning and "default_write_vault" in warning and expected in warning


def test_default_write_vault_missing_from_map_vaults_is_ignored_with_a_warning(base: Path) -> None:
    make_vaults(base)
    repo = make_repo(base / "repos" / "alpha")
    path = _write_map(
        base, {"alpha": {"root": str(repo), "vaults": ["personal", "ghost"], "default_write_vault": "ghost"}}
    )

    vault_map = load_vault_map(path)

    assert vault_map.find_project(repo).default_write_vault is None
    (warning,) = vault_map.warnings
    assert "alpha" in warning and "ghost" in warning and "not listed in the map vaults" in warning


def test_one_bad_project_field_keeps_other_projects_defaults(base: Path) -> None:
    make_vaults(base)
    alpha = make_repo(base / "repos" / "alpha")
    beta = make_repo(base / "repos" / "beta")
    path = _write_map(
        base,
        {
            "alpha": {"root": str(alpha), "vaults": ["personal"], "default_write_vault": 1},
            "beta": {"root": str(beta), "vaults": ["team", "personal"], "default_write_vault": "personal"},
        },
    )

    vault_map = load_vault_map(path)

    assert vault_map.find_project(alpha).default_write_vault is None
    beta_default = vault_map.find_project(beta).default_write_vault
    assert beta_default is not None and beta_default.name == "personal"
    assert vault_map.default_write_vaults == {"alpha": None, "beta": "personal"}
    assert len(vault_map.warnings) == 1
