from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from pytest import MonkeyPatch
from typer.testing import CliRunner

from tests.test_cli_search import _deterministic_text_embeddings, _unavailable_search_text_embeddings, write_page
from tests.test_context_pack_contract import make_pack, make_pack_with_warning
from tests.test_read_only_boundary import file_bytes
from vault_graph.app.catalog_service import CatalogService
from vault_graph.cli.main import app
from vault_graph.context import (
    ContextEvidence,
    ContextEvidenceRef,
    ContextPack,
    ContextPackActualScope,
    ContextPackRenderer,
    ContextPackRequest,
    ContextPackRequestedScope,
    ContextPackScope,
    ContextPackStoreRevision,
    ContextPackVault,
    ContextPackVaultRevision,
    ContextPackWarning,
    DefaultContextPackRenderer,
)
from vault_graph.ingestion.vault_catalog import VaultCatalog, VaultCatalogEntry
from vault_graph.storage.local.sqlite_metadata_store import SQLiteMetadataStore

runner = CliRunner()


class _RecordingContextPackBuilder:
    def __init__(self, pack: ContextPack) -> None:
        self.pack = pack
        self.calls: list[ContextPackRequest] = []
        self.include_graph_from_factory: bool | None = None

    def build(self, request: ContextPackRequest) -> ContextPack:
        self.calls.append(request)
        return self.pack


def _catalog(tmp_path: Path, vault_ids: tuple[str, ...] = ("default", "second")) -> VaultCatalog:
    entries = []
    for vault_id in vault_ids:
        root = tmp_path / vault_id
        root.mkdir(exist_ok=True)
        entries.append(VaultCatalogEntry.from_root(vault_id=vault_id, root_path=root, content_scopes=("wiki", "docs")))
    return VaultCatalog.from_entries(entries=entries, active_vault_id=vault_ids[0])


def state_tree(path: Path) -> tuple[str, ...]:
    if not path.exists():
        return ()
    return tuple(sorted(str(child.relative_to(path)) for child in path.rglob("*")))


def make_multi_vault_pack() -> ContextPack:
    first_ref = ContextEvidenceRef("default", "doc-shared", "chunk-shared")
    second_ref = ContextEvidenceRef("second", "doc-shared", "chunk-shared")
    first_evidence = ContextEvidence(
        ref=first_ref,
        path="wiki/shared.md",
        section="Shared",
        anchor="shared",
        content_hash="hash-default",
        raw_sha256="raw-default",
        metadata_index_revision="metadata-default",
        vault_revision="git-default",
        excerpt="default evidence",
        excerpt_token_count=2,
        truncated=False,
        retrieval_reasons=("keyword matched",),
        warnings=(),
    )
    second_evidence = ContextEvidence(
        ref=second_ref,
        path="wiki/shared.md",
        section="Shared",
        anchor="shared",
        content_hash="hash-second",
        raw_sha256="raw-second",
        metadata_index_revision="metadata-second",
        vault_revision="git-second",
        excerpt="second evidence",
        excerpt_token_count=2,
        truncated=False,
        retrieval_reasons=("vector matched",),
        warnings=(),
    )
    return replace(
        make_pack(),
        scope=ContextPackScope(
            requested=ContextPackRequestedScope(
                vault_ids=("default", "second"),
                content_scopes=("wiki", "docs"),
                include_cross_vault=False,
            ),
            actual_scopes=(
                ContextPackActualScope(
                    vault_ids=("default",),
                    content_scopes=("wiki", "docs"),
                    include_cross_vault=False,
                    scope_key="default:wiki,docs:local",
                ),
                ContextPackActualScope(
                    vault_ids=("second",),
                    content_scopes=("wiki", "docs"),
                    include_cross_vault=False,
                    scope_key="second:wiki,docs:local",
                ),
            ),
        ),
        vaults=(
            ContextPackVault(vault_id="default", display_name="default"),
            ContextPackVault(vault_id="second", display_name="second"),
        ),
        vault_revisions=(
            ContextPackVaultRevision(vault_id="default", revision="git-default", revision_kind="git"),
            ContextPackVaultRevision(vault_id="second", revision="git-second", revision_kind="git"),
        ),
        store_revisions=(
            ContextPackStoreRevision(
                kind="metadata",
                revision="metadata-default",
                vault_id="default",
                scope_key="default:wiki,docs:local",
            ),
            ContextPackStoreRevision(
                kind="metadata",
                revision="metadata-second",
                vault_id="second",
                scope_key="second:wiki,docs:local",
            ),
        ),
        warnings=(
            ContextPackWarning(
                code="stale_projection",
                severity="warning",
                message="Second Vault vector projection is stale.",
                affected_vault_ids=("second",),
                evidence_refs=(second_ref,),
                scope_key="second:wiki,docs:local",
                source_code="vector_stale",
                source_kind="retrieval",
            ),
        ),
        evidence=(first_evidence, second_evidence),
    )


class _SentinelRenderer:
    def __init__(self) -> None:
        self.json_pack: ContextPack | None = None
        self.markdown_pack: ContextPack | None = None

    def render_json(self, pack: ContextPack) -> str:
        self.json_pack = pack
        return '{"sentinel":"json"}\n'

    def render_markdown(self, pack: ContextPack) -> str:
        self.markdown_pack = pack
        return "SENTINEL MARKDOWN\n"


def _install_fake_context(
    *,
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
    builder: _RecordingContextPackBuilder,
    renderer: ContextPackRenderer | None = None,
) -> VaultCatalog:
    catalog = _catalog(tmp_path)

    def fake_catalog(_: Path) -> tuple[object, VaultCatalog]:
        return object(), catalog

    def fake_context_builder_service(
        _: Path,
        *,
        config: object,
        catalog: VaultCatalog,
        include_graph: bool = False,
    ) -> tuple[_RecordingContextPackBuilder, ContextPackRenderer]:
        builder.include_graph_from_factory = include_graph
        return builder, renderer or DefaultContextPackRenderer()

    monkeypatch.setattr("vault_graph.cli.main._catalog", fake_catalog)
    monkeypatch.setattr("vault_graph.cli.main._context_builder_service", fake_context_builder_service)
    return catalog


def test_cli_context_json_uses_context_pack_contract(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    builder = _RecordingContextPackBuilder(make_pack_with_warning())
    _install_fake_context(monkeypatch=monkeypatch, tmp_path=tmp_path, builder=builder)

    result = runner.invoke(app, ["context", "--state", str(tmp_path / "state"), "--format", "json", "Build context"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["context_pack_schema_version"] == "context-pack-v1"
    assert payload["warnings"][0]["code"] == "graph_unavailable"
    assert builder.calls[0].goal == "Build context"
    assert builder.calls[0].budget.max_tokens == 8000
    assert builder.calls[0].retrieval_limit == 10
    assert builder.calls[0].include_graph is False


def test_cli_context_uses_injected_renderer_for_markdown_and_preserves_warnings(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    builder = _RecordingContextPackBuilder(make_pack_with_warning(code="search_degraded", message="Vector unavailable"))
    renderer = _SentinelRenderer()
    _install_fake_context(monkeypatch=monkeypatch, tmp_path=tmp_path, builder=builder, renderer=renderer)

    result = runner.invoke(app, ["context", "--state", str(tmp_path / "state"), "Build context"])

    assert result.exit_code == 0
    assert result.stdout == "SENTINEL MARKDOWN\n"
    assert renderer.markdown_pack is builder.pack
    assert renderer.markdown_pack.warnings[0].code == "search_degraded"


def test_cli_context_uses_injected_renderer_for_json(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    builder = _RecordingContextPackBuilder(make_pack())
    renderer = _SentinelRenderer()
    _install_fake_context(monkeypatch=monkeypatch, tmp_path=tmp_path, builder=builder, renderer=renderer)

    result = runner.invoke(app, ["context", "--state", str(tmp_path / "state"), "--format", "json", "Build context"])

    assert result.exit_code == 0
    assert result.stdout == '{"sentinel":"json"}\n'
    assert renderer.json_pack is builder.pack


def test_cli_context_passes_limit_budget_and_graph_flags(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    builder = _RecordingContextPackBuilder(make_pack())
    _install_fake_context(monkeypatch=monkeypatch, tmp_path=tmp_path, builder=builder)

    result = runner.invoke(
        app,
        [
            "context",
            "--state",
            str(tmp_path / "state"),
            "--all-vaults",
            "--include-graph",
            "--include-cross-vault",
            "--max-tokens",
            "1200",
            "--limit",
            "7",
            "Build context",
        ],
    )

    assert result.exit_code == 0
    request = builder.calls[0]
    assert builder.include_graph_from_factory is True
    assert request.budget.max_tokens == 1200
    assert request.retrieval_limit == 7
    assert request.include_graph is True
    assert request.include_cross_vault is True
    assert request.requested_scope.vault_ids == ("default", "second")
    assert request.requested_scope.include_cross_vault is True


def test_cli_context_validates_options_before_opening_stores(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    def fail_factory(*_: object, **__: object) -> object:
        raise AssertionError("invalid options must not open context stores")

    monkeypatch.setattr("vault_graph.cli.main._context_builder_service", fail_factory, raising=False)

    invalid_format = runner.invoke(
        app,
        ["context", "--state", str(tmp_path / "state"), "--format", "xml", "Build"],
    )
    assert invalid_format.exit_code == 1
    assert "unsupported_format" in invalid_format.stdout
    empty_goal = runner.invoke(app, ["context", "--state", str(tmp_path / "state"), "   "])
    budget_too_small = runner.invoke(
        app, ["context", "--state", str(tmp_path / "state"), "--max-tokens", "999", "Build"]
    )
    invalid_limit = runner.invoke(
        app, ["context", "--state", str(tmp_path / "state"), "--limit", "0", "Build"]
    )
    assert empty_goal.exit_code == 1
    assert "empty_goal" in empty_goal.stdout
    assert budget_too_small.exit_code == 1
    assert "context_budget_too_small" in budget_too_small.stdout
    assert invalid_limit.exit_code == 1
    assert "context_limit_must_be_positive" in invalid_limit.stdout


def test_cli_context_rejects_invalid_scope_flag_combinations(tmp_path: Path) -> None:
    both_scope_flags = runner.invoke(
        app,
        ["context", "--state", str(tmp_path / "state"), "--vault-id", "default", "--all-vaults", "Build"],
    )
    cross_without_graph = runner.invoke(
        app,
        ["context", "--state", str(tmp_path / "state"), "--all-vaults", "--include-cross-vault", "Build"],
    )
    cross_without_all_vaults = runner.invoke(
        app,
        ["context", "--state", str(tmp_path / "state"), "--include-graph", "--include-cross-vault", "Build"],
    )

    assert both_scope_flags.exit_code == 1
    assert "Use either --vault-id or --all-vaults" in both_scope_flags.stdout
    assert cross_without_graph.exit_code == 1
    assert "include_cross_vault_requires_multi_vault_graph_scope" in cross_without_graph.stdout
    assert cross_without_all_vaults.exit_code == 1
    assert "include_cross_vault_requires_multi_vault_graph_scope" in cross_without_all_vaults.stdout


def test_cli_context_unknown_vault_does_not_open_builder_or_graph(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    state_path = tmp_path / "state"
    runner.invoke(app, ["init", "--vault", str(vault_root), "--state", str(state_path)])

    def fail_context_builder(*_: object, **__: object) -> object:
        raise AssertionError("unknown vault must not open context builder dependencies")

    def fail_graph_open(_: object) -> object:
        raise AssertionError("unknown vault must not open graph retrieval state")

    monkeypatch.setattr("vault_graph.cli.main._context_builder_service", fail_context_builder, raising=False)
    monkeypatch.setattr("vault_graph.cli.main._graph_retrieval_service", fail_graph_open)

    result = runner.invoke(
        app,
        ["context", "--state", str(state_path), "--vault-id", "missing", "--include-graph", "Build"],
    )

    assert result.exit_code == 1
    assert "unknown vault_id: missing" in result.stdout


def test_cli_context_rejects_single_vault_cross_vault_before_opening_builder_or_graph(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    state_path = tmp_path / "state"
    runner.invoke(app, ["init", "--vault", str(vault_root), "--state", str(state_path)])

    def fail_context_builder(*_: object, **__: object) -> object:
        raise AssertionError("invalid single-vault cross-vault scope must not open context builder dependencies")

    def fail_graph_open(_: object) -> object:
        raise AssertionError("invalid single-vault cross-vault scope must not open graph retrieval state")

    monkeypatch.setattr("vault_graph.cli.main._context_builder_service", fail_context_builder)
    monkeypatch.setattr("vault_graph.cli.main._graph_retrieval_service", fail_graph_open)

    result = runner.invoke(
        app,
        [
            "context",
            "--state",
            str(state_path),
            "--all-vaults",
            "--include-graph",
            "--include-cross-vault",
            "Build",
        ],
    )

    assert result.exit_code == 1
    assert "include_cross_vault requires multiple requested vault_ids" in result.stdout


def test_cli_context_without_include_graph_does_not_open_graph_state(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr("vault_graph.cli.main._text_embeddings", _deterministic_text_embeddings)
    monkeypatch.setattr("vault_graph.cli.main._search_text_embeddings", _deterministic_text_embeddings)

    def fail_graph_open(_: object) -> None:
        raise AssertionError("plain context must not open graph retrieval state")

    monkeypatch.setattr("vault_graph.cli.main._graph_retrieval_service", fail_graph_open)
    vault_root = tmp_path / "vault"
    write_page(vault_root, "wiki/page.md", "# Page\nGraphRAG evidence\n")
    state_path = tmp_path / "state"
    runner.invoke(app, ["init", "--vault", str(vault_root), "--state", str(state_path)])
    runner.invoke(app, ["index", "--state", str(state_path)])
    before = file_bytes(vault_root)

    result = runner.invoke(app, ["context", "--state", str(state_path), "GraphRAG"])

    assert result.exit_code == 0
    assert "wiki/page.md" in result.stdout
    assert file_bytes(vault_root) == before


def test_cli_context_missing_metadata_exits_nonzero_without_creating_projection_files(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    write_page(vault_root, "wiki/page.md", "# Page\nGraphRAG evidence\n")
    state_path = tmp_path / "state"
    runner.invoke(app, ["init", "--vault", str(vault_root), "--state", str(state_path)])
    before_state = state_tree(state_path)

    result = runner.invoke(app, ["context", "--state", str(state_path), "GraphRAG"])

    assert result.exit_code == 1
    assert "metadata_unavailable" in result.stdout or "keyword_index_unavailable" in result.stdout
    assert state_tree(state_path) == before_state
    assert not (state_path / "metadata" / "metadata.sqlite3").exists()
    assert not (state_path / "vector").exists()
    assert not (state_path / "graph").exists()
    assert not (state_path / "projection_cache").exists()
    assert not (state_path / "data" / "projection_cache").exists()


def test_cli_context_missing_keyword_projection_exits_nonzero_without_creating_extra_state(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    write_page(vault_root, "wiki/page.md", "# Page\nGraphRAG evidence\n")
    state_path = tmp_path / "state"
    runner.invoke(app, ["init", "--vault", str(vault_root), "--state", str(state_path)])
    metadata_store = SQLiteMetadataStore(CatalogService(state_path=state_path).metadata_path, initialize=True)
    with metadata_store.connect_for_tests() as connection:
        connection.execute("DROP TABLE keyword_projection_metadata")
        connection.execute("DROP TABLE keyword_chunks")
    before_state = state_tree(state_path)

    result = runner.invoke(app, ["context", "--state", str(state_path), "GraphRAG"])

    assert result.exit_code == 1
    assert "keyword_index_unavailable" in result.stdout
    assert state_tree(state_path) == before_state
    assert not (state_path / "vector").exists()
    assert not (state_path / "graph").exists()


def test_cli_context_all_vaults_preserves_requested_vault_ids(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    builder = _RecordingContextPackBuilder(make_pack())
    _install_fake_context(monkeypatch=monkeypatch, tmp_path=tmp_path, builder=builder)

    result = runner.invoke(
        app,
        ["context", "--state", str(tmp_path / "state"), "--all-vaults", "--format", "json", "Build"],
    )

    assert result.exit_code == 0
    assert builder.calls[0].requested_scope.vault_ids == ("default", "second")


def test_cli_context_all_vaults_preserves_evidence_warning_and_revision_vault_ids(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    builder = _RecordingContextPackBuilder(make_multi_vault_pack())
    _install_fake_context(monkeypatch=monkeypatch, tmp_path=tmp_path, builder=builder)

    result = runner.invoke(
        app,
        ["context", "--state", str(tmp_path / "state"), "--all-vaults", "--format", "json", "Build"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert [item["vault_id"] for item in payload["vaults"]] == ["default", "second"]
    assert [item["ref"]["vault_id"] for item in payload["evidence"]] == ["default", "second"]
    assert payload["warnings"][0]["affected_vault_ids"] == ["second"]
    assert payload["warnings"][0]["evidence_refs"][0]["vault_id"] == "second"
    assert [item["vault_id"] for item in payload["vault_revisions"]] == ["default", "second"]
    assert [item["vault_id"] for item in payload["store_revisions"]] == ["default", "second"]
    markdown = DefaultContextPackRenderer().render_markdown(builder.pack)
    assert "[second] wiki/shared.md#shared" in markdown
    assert "second:wiki,docs:local" in markdown
    assert "stale_projection" in markdown


def test_cli_context_all_vaults_uses_real_retrieval_and_preserves_evidence_vault_ids(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr("vault_graph.cli.main._text_embeddings", _deterministic_text_embeddings)
    monkeypatch.setattr("vault_graph.cli.main._search_text_embeddings", _deterministic_text_embeddings)
    first = tmp_path / "first"
    second = tmp_path / "second"
    write_page(first, "wiki/first.md", "# First\nGraphRAG shared evidence from first vault\n")
    write_page(second, "wiki/second.md", "# Second\nGraphRAG shared evidence from second vault\n")
    state_path = tmp_path / "state"
    runner.invoke(app, ["init", "--vault", str(first), "--state", str(state_path)])
    runner.invoke(app, ["vault", "add", "second", "--path", str(second), "--state", str(state_path)])
    index_result = runner.invoke(app, ["index", "--state", str(state_path), "--all-vaults"])

    result = runner.invoke(app, ["context", "--state", str(state_path), "--all-vaults", "--format", "json", "GraphRAG"])

    assert index_result.exit_code == 0
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["scope"]["requested"]["vault_ids"] == ["default", "second"]
    evidence_by_vault = {item["ref"]["vault_id"]: item["path"] for item in payload["evidence"]}
    assert evidence_by_vault["default"] == "wiki/first.md"
    assert evidence_by_vault["second"] == "wiki/second.md"


def test_cli_context_vector_unavailable_returns_keyword_pack_with_warning(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr("vault_graph.cli.main._text_embeddings", _deterministic_text_embeddings)
    monkeypatch.setattr("vault_graph.cli.main._search_text_embeddings", _unavailable_search_text_embeddings)
    vault_root = tmp_path / "vault"
    write_page(vault_root, "wiki/page.md", "# Page\nGraphRAG evidence\n")
    state_path = tmp_path / "state"
    runner.invoke(app, ["init", "--vault", str(vault_root), "--state", str(state_path)])
    index_result = runner.invoke(app, ["index", "--state", str(state_path)])

    result = runner.invoke(app, ["context", "--state", str(state_path), "--format", "json", "GraphRAG"])

    assert index_result.exit_code == 0
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["evidence"][0]["path"] == "wiki/page.md"
    assert any(
        warning["code"] == "search_degraded" and warning["source_code"] == "embedding_model_unavailable"
        for warning in payload["warnings"]
    )


def test_cli_context_include_graph_preserves_graph_unavailable_warning(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr("vault_graph.cli.main._text_embeddings", _deterministic_text_embeddings)
    monkeypatch.setattr("vault_graph.cli.main._search_text_embeddings", _deterministic_text_embeddings)

    class _UnavailableGraphSearchSource:
        def graph_candidates_for_search(self, **_: object) -> object:
            from vault_graph.errors import SearchError

            raise SearchError("graph_missing")

    def graph_factory(_: Path) -> tuple[object, VaultCatalog, _UnavailableGraphSearchSource]:
        catalog = VaultCatalog.from_entries(
            entries=(VaultCatalogEntry.from_root(vault_id="default", root_path=vault_root),),
            active_vault_id="default",
        )
        return object(), catalog, _UnavailableGraphSearchSource()

    vault_root = tmp_path / "vault"
    write_page(vault_root, "wiki/page.md", "# Page\nGraphRAG evidence\n")
    state_path = tmp_path / "state"
    runner.invoke(app, ["init", "--vault", str(vault_root), "--state", str(state_path)])
    runner.invoke(app, ["index", "--state", str(state_path)])
    before_vault = file_bytes(vault_root)
    before_state = state_tree(state_path)
    monkeypatch.setattr("vault_graph.cli.main._graph_retrieval_service", graph_factory)

    result = runner.invoke(
        app,
        ["context", "--state", str(state_path), "--include-graph", "--format", "json", "GraphRAG"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert any(warning["code"] == "graph_unavailable" for warning in payload["warnings"])
    assert payload["backend"]["graph_store"]["used"] is False
    assert file_bytes(vault_root) == before_vault
    assert state_tree(state_path) == before_state


def test_cli_context_all_vaults_does_not_modify_registered_vault_files(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    write_page(first, "wiki/page.md", "# First\nGraphRAG evidence\n")
    write_page(second, "wiki/page.md", "# Second\nGraphRAG evidence\n")
    state_path = tmp_path / "state"
    runner.invoke(app, ["init", "--vault", str(first), "--state", str(state_path)])
    runner.invoke(app, ["vault", "add", "second", "--path", str(second), "--state", str(state_path)])
    before_first = file_bytes(first)
    before_second = file_bytes(second)
    builder = _RecordingContextPackBuilder(make_multi_vault_pack())

    def fake_context_builder_service(
        _: Path,
        *,
        config: object,
        catalog: VaultCatalog,
        include_graph: bool = False,
    ) -> tuple[_RecordingContextPackBuilder, ContextPackRenderer]:
        return builder, DefaultContextPackRenderer()

    monkeypatch.setattr("vault_graph.cli.main._context_builder_service", fake_context_builder_service)

    result = runner.invoke(app, ["context", "--state", str(state_path), "--all-vaults", "GraphRAG"])

    assert result.exit_code == 0
    assert builder.calls[0].requested_scope.vault_ids == ("default", "second")
    assert file_bytes(first) == before_first
    assert file_bytes(second) == before_second
