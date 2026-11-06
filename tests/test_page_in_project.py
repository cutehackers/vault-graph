"""The project scope rule ``page_in_project`` (spec 2026-11-05 §4.4.2, A-20).

The table test builds each ``VaultProjectScope`` from a fixture ``vault-map.json`` so that
"field absent" goes through the same reader as the real map.
"""

from __future__ import annotations

import ast
import json
from dataclasses import dataclass, replace
from pathlib import Path

import pytest

from tests.test_mcp_tools import _registry, fake_factory, project_setup
from tests.test_project_memory_service import make_service
from tests.test_session_recall import NOW, FakeDocuments, FakeProposals, FakeUsage, doc
from tests.test_session_recall import FakeScope as FakeResolver
from tests.test_sqlite_metadata_store import make_chunk, make_document
from vault_graph.context.memory.project_scope import (
    UNMAPPED_VAULT_SCOPE,
    page_in_project,
)
from vault_graph.context.pack.recall import RecallPorts, RecallScope, recall
from vault_graph.indexing.ingestion.document_normalizer import DocumentSnapshot
from vault_graph.interface.mcp.mcp_tools import SummarizeProjectMemoryInput
from vault_graph.operation.integration.vault_map import MappedVaultScope, load_vault_map
from vault_graph.operation.scope.vault_catalog import QueryScope

SRC = Path(__file__).parents[1] / "src" / "vault_graph"
ABSENT = "absent"


@dataclass(frozen=True)
class FakeScope:
    linked_projects: frozenset[str]
    sharable: bool


def _map_scope(tmp_path: Path, *, links: str, sharable: object) -> MappedVaultScope:
    vault: dict[str, object] = {"path": str(tmp_path / "vaults" / "shared"), "role": "personal"}
    if sharable != ABSENT:
        vault["sharable"] = sharable
    projects = {"alpha": {"root": str(tmp_path / "repos" / "alpha"), "vaults": ["shared"]}}
    if links == "many":
        projects["beta"] = {"root": str(tmp_path / "repos" / "beta"), "vaults": ["shared"]}
    path = tmp_path / "vault-map.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"version": 2, "vaults": {"shared": vault}, "projects": projects}), encoding="utf-8")
    return load_vault_map(path).project_scope("shared")


def _expected(project: str | None, links: str, sharable: object) -> bool:
    if project == "alpha":
        return True  # rule 1
    if project == "beta":
        return False  # rule 1
    if links == "one":
        return True  # rule 2, whatever sharable says
    return sharable is True  # rule 3, absent is false


@pytest.mark.parametrize("sharable", [True, False, ABSENT])
@pytest.mark.parametrize("links", ["one", "many"])
@pytest.mark.parametrize("project", ["alpha", "beta", None])
def test_eighteen_cases_follow_rules_one_to_three(
    tmp_path: Path, project: str | None, links: str, sharable: object
) -> None:
    scope = _map_scope(tmp_path, links=links, sharable=sharable)
    frontmatter = {} if project is None else {"project": project}

    assert page_in_project(frontmatter, "alpha", vault_scope=scope) is _expected(project, links, sharable)


@pytest.mark.parametrize("links", ["one", "many"])
@pytest.mark.parametrize("project", ["alpha", "beta", None])
def test_absent_sharable_gives_the_same_result_as_false(tmp_path: Path, project: str | None, links: str) -> None:
    frontmatter = {} if project is None else {"project": project}
    absent = _map_scope(tmp_path / "a", links=links, sharable=ABSENT)
    false = _map_scope(tmp_path / "f", links=links, sharable=False)

    assert page_in_project(frontmatter, "alpha", vault_scope=absent) is page_in_project(
        frontmatter, "alpha", vault_scope=false
    )


def test_single_project_vault_page_belongs_to_that_project_even_when_sharable_is_false() -> None:
    scope = FakeScope(linked_projects=frozenset({"alpha"}), sharable=False)

    assert page_in_project({}, "alpha", vault_scope=scope) is True


def test_single_project_vault_page_does_not_belong_to_another_project() -> None:
    scope = FakeScope(linked_projects=frozenset({"alpha"}), sharable=True)

    assert page_in_project({}, "beta", vault_scope=scope) is False


@pytest.mark.parametrize("value", [None, "", [], "  "])
def test_empty_project_values_count_as_absent(value: object) -> None:
    many = FakeScope(linked_projects=frozenset({"alpha", "beta"}), sharable=False)

    assert page_in_project({"project": value}, "alpha", vault_scope=many) is False


def test_project_list_matches_any_listed_project() -> None:
    many = FakeScope(linked_projects=frozenset({"alpha", "beta"}), sharable=False)

    assert page_in_project({"project": ["beta", " alpha "]}, "alpha", vault_scope=many) is True
    assert page_in_project({"project": ["beta"]}, "alpha", vault_scope=many) is False


def test_tagged_page_is_outside_when_the_folder_has_no_project() -> None:
    many = FakeScope(linked_projects=frozenset({"alpha", "beta"}), sharable=True)

    assert page_in_project({"project": "alpha"}, None, vault_scope=many) is False


def test_vault_without_map_links_belongs_to_the_project_that_reached_it() -> None:
    assert page_in_project({}, "alpha", vault_scope=UNMAPPED_VAULT_SCOPE) is True
    assert page_in_project({}, None, vault_scope=UNMAPPED_VAULT_SCOPE) is True
    assert page_in_project({"project": "beta"}, "alpha", vault_scope=UNMAPPED_VAULT_SCOPE) is False


def _defines(path: Path, name: str) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return any(isinstance(node, ast.FunctionDef) and node.name == name for node in ast.walk(tree))


def test_page_in_project_is_defined_once_in_memory_views_and_recall_has_no_own_rule() -> None:
    owners = sorted(path.relative_to(SRC).as_posix() for path in SRC.rglob("*.py") if _defines(path, "page_in_project"))

    assert owners == ["context/memory/project_scope.py"]
    assert not _defines(SRC / "context" / "pack" / "recall.py", "_in_project")


def test_search_modules_do_not_use_the_project_scope_rule() -> None:
    """The rule is for recall, L3 lists and cleanup bundles. Search results keep every page."""
    users = sorted(
        path.relative_to(SRC).as_posix()
        for path in SRC.rglob("*.py")
        if "project_scope" in path.read_text(encoding="utf-8")
    )

    assert not [path for path in users if path.startswith(("retrieval/", "context/pack/context_pack"))]


def _recall_titles(scopes: dict[str, FakeScope]) -> str:
    pages = (
        doc(
            "wiki/decisions/shared.md",
            vault_id="personal",
            title="Shared untagged",
            type="decision",
            updated="2026-10-29",
        ),
        doc(
            "wiki/decisions/mine.md",
            vault_id="personal",
            title="Alpha tagged",
            type="decision",
            project="alpha",
            updated="2026-10-29",
        ),
        doc(
            "wiki/decisions/beta.md",
            vault_id="personal",
            title="Beta tagged",
            type="decision",
            project="beta",
            updated="2026-10-29",
        ),
        doc(
            "wiki/decisions/own.md",
            vault_id="alpha-vault",
            title="Project vault untagged",
            type="decision",
            updated="2026-10-29",
        ),
    )
    by_vault: dict[str, tuple[DocumentSnapshot, ...]] = {}
    for page in pages:
        by_vault[page.vault_id] = (*by_vault.get(page.vault_id, ()), page)
    ports = RecallPorts(
        scope=FakeResolver(RecallScope(project_id="alpha", vault_ids=("alpha-vault", "personal"), vault_scopes=scopes)),
        documents=FakeDocuments(by_vault),
        usage=FakeUsage(),
        proposals=FakeProposals({}),
    )
    return recall(Path("/repos/alpha"), source="startup", session_id="s", ports=ports, now=NOW).text


SHARED_FALSE = {
    "personal": FakeScope(linked_projects=frozenset({"alpha", "beta"}), sharable=False),
    "alpha-vault": FakeScope(linked_projects=frozenset({"alpha"}), sharable=False),
}


def test_recall_leaves_out_untagged_pages_of_a_shared_vault_that_is_not_sharable() -> None:
    text = _recall_titles(SHARED_FALSE)

    assert "Alpha tagged" in text
    assert "Project vault untagged" in text
    assert "Shared untagged" not in text
    assert "Beta tagged" not in text


def test_recall_keeps_untagged_pages_of_a_sharable_shared_vault() -> None:
    scopes = {**SHARED_FALSE, "personal": FakeScope(linked_projects=frozenset({"alpha", "beta"}), sharable=True)}
    text = _recall_titles(scopes)

    assert "Shared untagged" in text
    assert "Beta tagged" not in text


def _decision(path: str, **frontmatter: object) -> DocumentSnapshot:
    return replace(make_document("main", path, "decision"), frontmatter={"type": "decision", **frontmatter})


def test_project_memory_summary_uses_the_same_rule(tmp_path: Path) -> None:
    documents = (
        _decision("wiki/decisions/untagged.md"),
        _decision("wiki/decisions/alpha.md", project="alpha"),
        _decision("wiki/decisions/beta.md", project="beta"),
    )
    chunks = tuple(make_chunk("main", item.document_id, item.path, chunk_id=item.path) for item in documents)
    service = make_service(tmp_path, documents=documents, chunks=chunks)
    requested = QueryScope(vault_ids=("main",), content_scopes=("wiki",))

    def paths(sharable: bool) -> set[str]:
        scope = FakeScope(linked_projects=frozenset({"alpha", "beta"}), sharable=sharable)
        projection = service.summarize(requested_scope=requested, project_id="alpha", vault_scopes={"main": scope})
        return {item.path for item in projection.vaults[0].decisions}

    assert paths(False) == {"wiki/decisions/alpha.md"}
    assert paths(True) == {"wiki/decisions/alpha.md", "wiki/decisions/untagged.md"}
    unscoped = service.summarize(requested_scope=requested)
    assert len(unscoped.vaults[0].decisions) == 3


def test_mcp_summary_passes_the_cwd_project_and_vault_scopes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo, services = project_setup(tmp_path, monkeypatch)
    factory = fake_factory()

    _registry(services, factory).summarize_project_memory(SummarizeProjectMemoryInput(cwd=str(repo)))

    call = factory.project_memory_service.calls[0]
    assert call["project_id"] == "repo"
    scopes = call["vault_scopes"]
    assert isinstance(scopes, dict)
    assert scopes["p-id"] == MappedVaultScope(linked_projects=frozenset({"repo"}), sharable=False)


def test_mcp_summary_outside_a_map_project_is_not_narrowed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, services = project_setup(tmp_path, monkeypatch)
    outside = tmp_path / "outside"
    outside.mkdir()
    factory = fake_factory()

    _registry(services, factory).summarize_project_memory(SummarizeProjectMemoryInput(cwd=str(outside)))

    call = factory.project_memory_service.calls[0]
    assert call["project_id"] is None and call["vault_scopes"] is None
