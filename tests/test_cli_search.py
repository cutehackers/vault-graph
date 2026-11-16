import json
from datetime import date
from pathlib import Path

import pytest
from pytest import MonkeyPatch
from typer.testing import CliRunner

from tests.test_cli_vector_indexing import _ConfiguredDeterministicTextEmbeddings
from vault_graph.interface.cli.main import _search_text_embeddings, app
from vault_graph.operation.scope.vault_catalog import VaultCatalog, VaultCatalogEntry
from vault_graph.retrieval.search.retrieval_result import RetrievalResult, RetrievalSignal, StoreRevision
from vault_graph.retrieval.search.search_response import SearchResponse
from vault_graph.storage.interfaces.metadata_store import EvidenceReference

runner = CliRunner()


def write_page(root: Path, path: str, body: str) -> None:
    file_path = root / path
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(body, encoding="utf-8")


def _deterministic_text_embeddings(_: object) -> _ConfiguredDeterministicTextEmbeddings:
    from tests.test_vector_indexer import SPEC

    return _ConfiguredDeterministicTextEmbeddings(SPEC)


class _UnavailableSearchTextEmbeddings(_ConfiguredDeterministicTextEmbeddings):
    def can_embed_without_download(self) -> bool:
        return False


def _unavailable_search_text_embeddings(_: object) -> _UnavailableSearchTextEmbeddings:
    from tests.test_vector_indexer import SPEC

    return _UnavailableSearchTextEmbeddings(SPEC)


def test_cli_search_uses_active_vault_by_default(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr("vault_graph.interface.cli.main._text_embeddings", _deterministic_text_embeddings)
    monkeypatch.setattr("vault_graph.interface.cli.main._search_text_embeddings", _deterministic_text_embeddings)
    vault_root = tmp_path / "vault"
    write_page(vault_root, "wiki/page.md", "# Page\nGraphRAG evidence\n")
    graph_home_path = tmp_path / "state"
    runner.invoke(app, ["init", "--vault", str(vault_root), "--graph-home", str(graph_home_path)])
    runner.invoke(app, ["index", "--graph-home", str(graph_home_path)])

    result = runner.invoke(app, ["search", "--graph-home", str(graph_home_path), "GraphRAG"])

    assert result.exit_code == 0
    assert "default" in result.stdout
    assert "wiki/page.md" in result.stdout
    assert "GraphRAG evidence" in result.stdout


def test_cli_search_text_output_prints_resolved_scope_for_zero_results(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr("vault_graph.interface.cli.main._text_embeddings", _deterministic_text_embeddings)
    monkeypatch.setattr("vault_graph.interface.cli.main._search_text_embeddings", _unavailable_search_text_embeddings)
    vault_root = tmp_path / "vault"
    write_page(vault_root, "wiki/page.md", "# Page\nGraphRAG evidence\n")
    graph_home_path = tmp_path / "state"
    runner.invoke(app, ["init", "--vault", str(vault_root), "--graph-home", str(graph_home_path)])
    runner.invoke(app, ["index", "--graph-home", str(graph_home_path)])

    result = runner.invoke(app, ["search", "--graph-home", str(graph_home_path), "missing"])

    assert result.exit_code == 0
    assert "vault_ids: default" in result.stdout
    assert "actual_scopes: default:raw,wiki,docs,scratch/reports" in result.stdout
    assert "results: 0" in result.stdout


def test_cli_search_json_uses_search_response_contract(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr("vault_graph.interface.cli.main._text_embeddings", _deterministic_text_embeddings)
    monkeypatch.setattr("vault_graph.interface.cli.main._search_text_embeddings", _deterministic_text_embeddings)
    vault_root = tmp_path / "vault"
    write_page(vault_root, "wiki/page.md", "# Page\nGraphRAG evidence\n")
    graph_home_path = tmp_path / "state"
    runner.invoke(app, ["init", "--vault", str(vault_root), "--graph-home", str(graph_home_path)])
    runner.invoke(app, ["index", "--graph-home", str(graph_home_path)])

    result = runner.invoke(app, ["search", "--graph-home", str(graph_home_path), "--format", "json", "GraphRAG"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["query_text"] == "GraphRAG"
    assert payload["result_count"] == 1
    assert payload["results"][0]["vault_id"] == "default"
    assert payload["results"][0]["kind"] == "evidence_chunk"
    assert payload["warnings"] == []


def test_cli_search_after_graph_indexing_does_not_expose_graph_expansion(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr("vault_graph.interface.cli.main._text_embeddings", _deterministic_text_embeddings)
    monkeypatch.setattr("vault_graph.interface.cli.main._search_text_embeddings", _deterministic_text_embeddings)
    vault_root = tmp_path / "vault"
    write_page(vault_root, "wiki/page.md", "# Page\nGraphRAG evidence\n")
    graph_home_path = tmp_path / "state"
    runner.invoke(app, ["init", "--vault", str(vault_root), "--graph-home", str(graph_home_path)])
    index_result = runner.invoke(app, ["index", "--graph-home", str(graph_home_path)])

    result = runner.invoke(app, ["search", "--graph-home", str(graph_home_path), "GraphRAG"])

    assert index_result.exit_code == 0
    assert result.exit_code == 0
    assert "results:" in result.stdout
    assert "graph_" not in result.stdout
    assert "related" not in result.stdout
    assert "decision-trace" not in result.stdout
    assert "include_graph" not in result.stdout


def test_cli_search_without_include_graph_does_not_open_graph_store(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr("vault_graph.interface.cli.main._text_embeddings", _deterministic_text_embeddings)
    monkeypatch.setattr("vault_graph.interface.cli.main._search_text_embeddings", _deterministic_text_embeddings)

    def fail_graph_open(_: object) -> None:
        raise AssertionError("plain search must not open graph retrieval state")

    monkeypatch.setattr("vault_graph.interface.cli.main._graph_retrieval_service", fail_graph_open)
    vault_root = tmp_path / "vault"
    write_page(vault_root, "wiki/page.md", "# Page\nGraphRAG evidence\n")
    graph_home_path = tmp_path / "state"
    runner.invoke(app, ["init", "--vault", str(vault_root), "--graph-home", str(graph_home_path)])
    runner.invoke(app, ["index", "--graph-home", str(graph_home_path)])

    result = runner.invoke(app, ["search", "--graph-home", str(graph_home_path), "GraphRAG"])

    assert result.exit_code == 0
    assert "wiki/page.md" in result.stdout


def test_cli_search_include_graph_renders_graph_signal(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    root = tmp_path / "vault"
    root.mkdir()
    catalog = VaultCatalog.from_entries(
        entries=[VaultCatalogEntry.from_root(vault_id="default", root_path=root)],
        active_vault_id="default",
    )
    fake_service = _FakeSearchService()

    def fake_search_service(
        state: Path, *, include_graph: bool = False
    ) -> tuple[object, VaultCatalog, "_FakeSearchService"]:
        assert include_graph is True
        return object(), catalog, fake_service

    monkeypatch.setattr("vault_graph.interface.cli.main._search_service", fake_search_service)

    result = runner.invoke(app, ["search", "--graph-home", str(tmp_path / "state"), "--include-graph", "GraphRAG"])

    assert result.exit_code == 0
    assert fake_service.include_graph is True
    assert "signals: graph:1" in result.stdout


def test_cli_search_include_cross_vault_requires_include_graph_and_all_vaults(tmp_path: Path) -> None:
    without_graph = runner.invoke(
        app,
        ["search", "--graph-home", str(tmp_path / "state"), "--include-cross-vault", "GraphRAG"],
    )
    without_all_vaults = runner.invoke(
        app,
        ["search", "--graph-home", str(tmp_path / "state"), "--include-graph", "--include-cross-vault", "GraphRAG"],
    )

    assert without_graph.exit_code == 1
    assert without_all_vaults.exit_code == 1
    assert "include_cross_vault_requires_multi_vault_graph_scope" in without_graph.stdout
    assert "include_cross_vault_requires_multi_vault_graph_scope" in without_all_vaults.stdout


def test_cli_search_scope_flags_are_mutually_exclusive(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    graph_home_path = tmp_path / "state"
    runner.invoke(app, ["init", "--vault", str(vault_root), "--graph-home", str(graph_home_path)])

    result = runner.invoke(
        app, ["search", "--graph-home", str(graph_home_path), "--vault-id", "default", "--all-vaults", "GraphRAG"]
    )

    assert result.exit_code == 1
    assert "Use either --vault-id or --all-vaults" in result.stdout


def test_cli_search_missing_keyword_projection_exits_nonzero_without_writes(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    write_page(vault_root, "wiki/page.md", "# Page\nGraphRAG evidence\n")
    graph_home_path = tmp_path / "state"
    runner.invoke(app, ["init", "--vault", str(vault_root), "--graph-home", str(graph_home_path)])

    result = runner.invoke(app, ["search", "--graph-home", str(graph_home_path), "GraphRAG"])

    assert result.exit_code == 1
    assert "keyword_index_unavailable" in result.stdout or "metadata_unavailable" in result.stdout
    assert not (graph_home_path / "metadata" / "metadata.sqlite3").exists()


def test_search_text_embeddings_uses_local_files_only(tmp_path: Path) -> None:
    from vault_graph.operation.scope.catalog_service import CatalogService

    config = CatalogService(graph_home_path=tmp_path / "state")

    embeddings = _search_text_embeddings(config)

    assert embeddings.config.local_files_only is True


class _FakeSearchService:
    def __init__(self) -> None:
        self.include_graph = False
        self.searches: list[tuple[date | None, date | None]] = []
        self.date_strict: list[bool] = []

    def search(
        self,
        *,
        query_text: str,
        requested_scope: object,
        limit: int,
        output_format: str,
        include_graph: bool,
        include_cross_vault: bool,
        mode: str,
        include_retired: bool = False,
        since: date | None = None,
        until: date | None = None,
        date_strict: bool = False,
    ) -> SearchResponse:
        self.include_graph = include_graph
        self.searches.append((since, until))
        self.date_strict.append(date_strict)
        assert query_text.startswith("GraphRAG")
        assert include_cross_vault is False
        assert mode == "knowledge"
        evidence = EvidenceReference(
            vault_id="default",
            document_id="doc-1",
            chunk_id="chunk-1",
            path="wiki/page.md",
            section="GraphRAG",
            anchor="graphrag",
            content_hash="chunk-hash",
            raw_sha256="raw-hash",
            metadata_index_revision="metadata-1",
            vault_revision="vault-1",
        )
        return SearchResponse(
            query_text=query_text,
            requested_scope=requested_scope,  # type: ignore[arg-type]
            actual_scopes=(requested_scope,),  # type: ignore[arg-type]
            limit=limit,
            result_count=1,
            candidate_count=1,
            dropped_candidate_count=0,
            results=(
                RetrievalResult(
                    result_id="default:chunk-1:rank-1",
                    vault_id="default",
                    kind="evidence_chunk",
                    title="wiki/page.md#graphrag",
                    summary="GraphRAG evidence",
                    rank=1,
                    evidence=(evidence,),
                    signals=(
                        RetrievalSignal(
                            kind="graph",
                            source_id="graph:default:relationship-1:chunk-1",
                            rank=1,
                            score=0.8,
                            backend="graph-projection-v1",
                            index_revision="graph-1",
                            explanation="GraphRAG -> Search via depends_on",
                        ),
                    ),
                    relationship_status="not_applicable",
                    warnings=(),
                    store_revisions=(StoreRevision(kind="graph", revision="graph-1"),),
                ),
            ),
            warnings=(),
            degraded=False,
            store_revisions=(),
            generated_at="2026-06-11T00:00:00+00:00",
        )


# --- Spec 2026-11-16 A4: session results are folded by default, with no new argument ---

SESSION_QUERY = "tombstone sweeper archived folders"
SESSIONS_DIR = "raw/sessions/claude-code"
SESSION_ONE = "11111111-1111-4111-8111-111111111111"
SESSION_TWO = "22222222-2222-4222-8222-222222222222"


def _session_part(session_id: str, part: int, day: str, exchanges: list[tuple[str, str]], *, agent: bool) -> str:
    """A vault-session/v2 part file with one exchange per (id, assistant answer)."""
    body = [
        "---",
        "schema: vault-session/v2",
        "renderer: vg-session-md/2.0",
        *(["agent: claude-code"] if agent else []),
        f'session_id: "{session_id}"',
        f"part: {part}",
        f'first_turn_at: "{day}T10:00:00.000Z"',
        f"exchange_count: {len(exchanges)}",
        "---",
        "",
    ]
    for number, (exchange_id, answer) in enumerate(exchanges):
        started = f"{day}T10:{number:02d}:00.000Z"
        body += [
            f"## How does the sweeper behave? {started} · {exchange_id}",
            f"<!-- vg:exchange id={exchange_id} scope=main started={started} ended={started} outcome=answered -->",
            "",
            f"### user · {started} · {exchange_id}",
            "",
            "How does the sweeper behave?",
            "",
            f"### assistant · {started} · a-{exchange_id}",
            "",
            answer,
            "",
        ]
    return "\n".join(body)


def write_two_sessions(vault_root: Path, *, agent: bool) -> None:
    """Session one matches in three exchanges over two part files. Session two matches in one exchange."""
    write_page(
        vault_root,
        f"{SESSIONS_DIR}/2026-11-01-{SESSION_ONE}-part1.md",
        _session_part(
            SESSION_ONE,
            1,
            "2026-11-01",
            [
                ("u-001", "The tombstone sweeper skips archived folders: archived folders are frozen."),
                ("u-002", "The tombstone sweeper runs nightly over archived folders."),
            ],
            agent=agent,
        ),
    )
    write_page(
        vault_root,
        f"{SESSIONS_DIR}/2026-11-02-{SESSION_ONE}-part2.md",
        _session_part(
            SESSION_ONE, 2, "2026-11-02", [("u-003", "The tombstone sweeper was renamed last week.")], agent=agent
        ),
    )
    write_page(
        vault_root,
        f"{SESSIONS_DIR}/2026-11-03-{SESSION_TWO}-part1.md",
        _session_part(
            SESSION_TWO,
            1,
            "2026-11-03",
            [("u-009", "The sweeper moves archived folders to cold storage.")],
            agent=agent,
        ),
    )


def _indexed_session_home(tmp_path: Path, monkeypatch: MonkeyPatch, *, agent: bool) -> Path:
    monkeypatch.setattr("vault_graph.interface.cli.main._text_embeddings", _deterministic_text_embeddings)
    monkeypatch.setattr("vault_graph.interface.cli.main._search_text_embeddings", _deterministic_text_embeddings)
    vault_root = tmp_path / "vault"
    write_two_sessions(vault_root, agent=agent)
    graph_home_path = tmp_path / "state"
    initialized = runner.invoke(app, ["init", "--vault", str(vault_root), "--graph-home", str(graph_home_path)])
    assert initialized.exit_code == 0, initialized.output
    indexed = runner.invoke(app, ["index", "--graph-home", str(graph_home_path)])
    assert indexed.exit_code == 0, indexed.output
    return graph_home_path


def _session_of(result: dict[str, object]) -> str:
    evidence = result["evidence"]
    assert isinstance(evidence, list)
    path = str(evidence[0]["path"])
    return SESSION_ONE if SESSION_ONE in path else SESSION_TWO


def test_cli_evidence_search_folds_one_session_into_one_result_by_default(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    (tmp_path / "unkeyed").mkdir()
    (tmp_path / "keyed").mkdir()
    unkeyed_home = _indexed_session_home(tmp_path / "unkeyed", monkeypatch, agent=False)
    keyed_home = _indexed_session_home(tmp_path / "keyed", monkeypatch, agent=True)
    command = ["search", "--mode", "evidence", "--format", "json", SESSION_QUERY]

    unkeyed = runner.invoke(app, [command[0], "--graph-home", str(unkeyed_home), *command[1:]])
    keyed = runner.invoke(app, [command[0], "--graph-home", str(keyed_home), *command[1:]])

    assert unkeyed.exit_code == 0, unkeyed.output
    assert keyed.exit_code == 0, keyed.output
    # Without `agent` there is no session key: every matched exchange is its own result.
    unfolded = json.loads(unkeyed.stdout)["results"]
    assert sorted(_session_of(result) for result in unfolded) == [SESSION_ONE] * 3 + [SESSION_TWO]
    # With the key and no flag, each session is one result and session one carries its other exchanges.
    folded = json.loads(keyed.stdout)["results"]
    assert sorted(_session_of(result) for result in folded) == [SESSION_ONE, SESSION_TWO]
    one = next(result for result in folded if _session_of(result) == SESSION_ONE)
    assert {item["path"] for item in one["evidence"]} == {
        f"{SESSIONS_DIR}/2026-11-01-{SESSION_ONE}-part1.md",
        f"{SESSIONS_DIR}/2026-11-02-{SESSION_ONE}-part2.md",
    }
    assert len(one["evidence"]) == 3
    assert "session_exchanges_attached" in {warning["code"] for warning in one["warnings"]}


# --- Spec 2026-11-16 A8: `--since`, `--until`, `--when` date arguments (D10, D13, F5) ---


def _fake_search(tmp_path: Path, monkeypatch: MonkeyPatch) -> _FakeSearchService:
    root = tmp_path / "vault"
    root.mkdir()
    catalog = VaultCatalog.from_entries(
        entries=[VaultCatalogEntry.from_root(vault_id="default", root_path=root)],
        active_vault_id="default",
    )
    fake_service = _FakeSearchService()

    def fake_search_service(
        state: Path, *, include_graph: bool = False
    ) -> tuple[object, VaultCatalog, _FakeSearchService]:
        return object(), catalog, fake_service

    monkeypatch.setattr("vault_graph.interface.cli.main._search_service", fake_search_service)
    monkeypatch.setattr("vault_graph.interface.cli.main._local_today", lambda: date(2026, 11, 16))
    return fake_service


def _search_args(tmp_path: Path, *args: str) -> list[str]:
    return ["search", "--graph-home", str(tmp_path / "state"), "--vault-id", "default", *args, "GraphRAG"]


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        ((), (None, None)),
        (("--since", "2026-11-03"), (date(2026, 11, 3), None)),
        (("--until", "2026-11-03"), (None, date(2026, 11, 3))),
        (("--since", "2026-11-01", "--until", "2026-11-03"), (date(2026, 11, 1), date(2026, 11, 3))),
        (("--since", "2026-11-03", "--until", "2026-11-03"), (date(2026, 11, 3), date(2026, 11, 3))),
        # 2026-11-16 is a Monday: last week is Monday 11-09 to Sunday 11-15.
        (("--when", "last week"), (date(2026, 11, 9), date(2026, 11, 15))),
        (("--when", "지난주"), (date(2026, 11, 9), date(2026, 11, 15))),
        (("--when", "3 days ago"), (date(2026, 11, 13), date(2026, 11, 13))),
    ],
)
def test_cli_search_passes_the_date_range_to_the_search(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    args: tuple[str, ...],
    expected: tuple[date | None, date | None],
) -> None:
    fake_service = _fake_search(tmp_path, monkeypatch)

    result = runner.invoke(app, _search_args(tmp_path, *args))

    assert result.exit_code == 0, result.output
    assert fake_service.searches == [expected]


@pytest.mark.parametrize(
    ("args", "reason"),
    [
        (("--since", "2026/11/03"), "since must be a YYYY-MM-DD date"),
        (("--until", "yesterday"), "until must be a YYYY-MM-DD date"),
        (("--since", "2026-02-30"), "since is not a real date"),
        (("--since", "2026-11-04", "--until", "2026-11-03"), "since 2026-11-04 is after until 2026-11-03"),
        (("--when", "sometime soon"), "cannot resolve date expression 'sometime soon'"),
        (("--when", "last week", "--since", "2026-11-01"), "--when cannot be used with --since or --until"),
        (("--when", "last week", "--until", "2026-11-01"), "--when cannot be used with --since or --until"),
    ],
)
def test_cli_search_rejects_bad_date_arguments_with_exit_code_2_and_never_searches(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    args: tuple[str, ...],
    reason: str,
) -> None:
    fake_service = _fake_search(tmp_path, monkeypatch)

    result = runner.invoke(app, _search_args(tmp_path, *args))

    assert result.exit_code == 2
    assert result.stdout == ""
    lines = result.stderr.splitlines()
    assert len(lines) == 1
    assert reason in lines[0]
    assert fake_service.searches == []


def test_cli_search_does_not_read_dates_from_the_query_text(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    fake_service = _fake_search(tmp_path, monkeypatch)

    result = runner.invoke(
        app, ["search", "--graph-home", str(tmp_path / "state"), "--vault-id", "default", "GraphRAG last week"]
    )

    assert result.exit_code == 0, result.output
    assert fake_service.searches == [(None, None)]


@pytest.fixture
def utc_local_time(monkeypatch: MonkeyPatch):  # type: ignore[no-untyped-def]
    import time

    monkeypatch.setenv("TZ", "UTC")
    time.tzset()
    yield
    monkeypatch.undo()
    time.tzset()


@pytest.mark.usefixtures("utc_local_time")
def test_cli_search_date_strict_keeps_only_sessions_in_the_range(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    graph_home = _indexed_session_home(tmp_path, monkeypatch, agent=True)
    command = ["search", "--graph-home", str(graph_home), "--mode", "evidence", "--format", "json", "--date-strict"]

    since_only = runner.invoke(app, [*command, "--since", "2026-11-03", SESSION_QUERY])
    until_only = runner.invoke(app, [*command, "--until", "2026-11-02", SESSION_QUERY])

    assert since_only.exit_code == 0, since_only.output
    assert until_only.exit_code == 0, until_only.output
    assert [_session_of(result) for result in json.loads(since_only.stdout)["results"]] == [SESSION_TWO]
    assert [_session_of(result) for result in json.loads(until_only.stdout)["results"]] == [SESSION_ONE]


@pytest.mark.usefixtures("utc_local_time")
def test_cli_search_date_range_puts_sessions_in_the_range_first(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    graph_home = _indexed_session_home(tmp_path, monkeypatch, agent=True)
    command = ["search", "--graph-home", str(graph_home), "--mode", "evidence", "--format", "json"]

    since_only = runner.invoke(app, [*command, "--since", "2026-11-03", SESSION_QUERY])
    until_only = runner.invoke(app, [*command, "--until", "2026-11-02", SESSION_QUERY])

    assert since_only.exit_code == 0, since_only.output
    assert until_only.exit_code == 0, until_only.output
    since_body = json.loads(since_only.stdout)
    assert [_session_of(result) for result in since_body["results"]] == [SESSION_TWO, SESSION_ONE]
    assert [_session_of(result) for result in json.loads(until_only.stdout)["results"]] == [SESSION_ONE, SESSION_TWO]
    assert not any(warning["code"].startswith("date_") for warning in since_body["warnings"])


@pytest.mark.parametrize(("args", "expected"), [((), [False]), (("--date-strict",), [True])])
def test_cli_search_passes_date_strict_to_the_search(
    tmp_path: Path, monkeypatch: MonkeyPatch, args: tuple[str, ...], expected: list[bool]
) -> None:
    fake_service = _fake_search(tmp_path, monkeypatch)

    result = runner.invoke(app, _search_args(tmp_path, "--since", "2026-11-03", *args))

    assert result.exit_code == 0, result.output
    assert fake_service.date_strict == expected
