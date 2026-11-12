"""v1·v2 겹침 제외와 같은 교환 id 중복 (spec 2026-11-05 §4.2.7 마지막 bullet, §4.2.6-9, §6, A-9).

같은 세션 묶음 (`agent`, `session_id`)에 v1과 v2 파일이 함께 있으면, v2 교환의 시각 범위와 겹치는 v1
교환을 색인에서만 뺀다. 고정 Vault는 세션 3333의 v1 파트 둘(1, 2)과 v2 파트 하나(3)다.

- v1 파트1의 교환 셋: 본 대화 14:00:00~14:06:01, 서브에이전트 a7f3 14:00:02~14:00:05, 본 대화 14:07:00~14:07:05.
- v2 파트3의 교환 둘: u-201 14:00:00~14:06:01, s-301 14:00:02~14:00:05.
- v1 파트2의 교환 하나: 14:10:00~14:10:05.

그래서 v1 파트1의 앞 두 교환만 빠지고, 14:07:00 교환과 v1 파트2 교환은 남는다.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from tests.test_metadata_indexer_paths import catalog_for
from vault_graph.indexing.ingestion.document_normalizer import DocumentNormalizer, NormalizedDocument
from vault_graph.indexing.ingestion.session_group import (
    exchange_ranges,
    reprocess_session_groups,
    session_group_key,
)
from vault_graph.indexing.ingestion.vault_loader import VaultLoader
from vault_graph.indexing.metadata_indexer import MetadataIndexer
from vault_graph.storage.local.sqlite_metadata_store import SQLiteMetadataStore

FIXTURES = Path(__file__).parent / "fixtures"
V1_PART1 = FIXTURES / "session_v1" / "2026-11-03-33333333-3333-4333-8333-333333333333-part1.md"
V2_FIXTURES = FIXTURES / "session_v2" / "raw" / "sessions" / "claude-code"
V2_PART1 = V2_FIXTURES / "2026-11-03-33333333-3333-4333-8333-333333333333-part1.md"
V2_4444_PART1 = V2_FIXTURES / "2026-11-04-44444444-4444-4444-8444-444444444444-part1.md"
V2_4444_PART3 = V2_FIXTURES / "2026-11-04-44444444-4444-4444-8444-444444444444-part3.md"

SESSION_DIR = "raw/sessions/claude-code"
SESSION = "33333333-3333-4333-8333-333333333333"
V1_PART1_PATH = f"{SESSION_DIR}/2026-11-03-{SESSION}-part1.md"
V1_PART2_PATH = f"{SESSION_DIR}/2026-11-03-{SESSION}-part2.md"
V2_PART3_PATH = f"{SESSION_DIR}/2026-11-03-{SESSION}-part3.md"
NOTE_PATH = "wiki/notes/note.md"

V1_PART2 = f"""---
schema: vault-session/v1
agent: claude-code
session_id: "{SESSION}"
project: demo-app
part: 2
first_turn_uuid: u-210
first_turn_at: "2026-11-03T14:10:00.000Z"
last_turn_uuid: a-211
last_turn_at: "2026-11-03T14:10:05.000Z"
turn_count: 2
collected_at: "2026-11-03T14:20:00Z"
trigger: SessionEnd
---

## 2026-11-03T14:10:00.000Z user

Add a changelog entry for the secret fix.

## 2026-11-03T14:10:05.000Z assistant

Added the changelog entry.
"""

KEPT_V1_PART1_EXCHANGE = f"{V1_PART1_PATH}:2026-11-03T14:07:00.000Z user:1"
OVERLAPPED_V1_EXCHANGES = {
    f"{V1_PART1_PATH}:2026-11-03T14:00:00.000Z user:1",
    f"{V1_PART1_PATH}:2026-11-03T14:00:02.000Z subagent a7f3 user:1",
}


def write(root: Path, relative: str, text: str) -> None:
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def v2_part3_text() -> str:
    """The v2 fixture of session 3333, renumbered as part 3 after two v1 parts."""
    return V2_PART1.read_text(encoding="utf-8").replace("\npart: 1\n", "\npart: 3\n", 1)


def session_vault(root: Path, *, with_v2: bool = True) -> Path:
    """One session with v1 parts 1 and 2 (and v2 part 3), plus one wiki note."""
    write(root, V1_PART1_PATH, V1_PART1.read_text(encoding="utf-8"))
    write(root, V1_PART2_PATH, V1_PART2)
    if with_v2:
        write(root, V2_PART3_PATH, v2_part3_text())
    write(root, NOTE_PATH, "---\ntitle: Note\n---\n# Note\nUnrelated body\n")
    return root


def load(
    root: Path,
) -> tuple[tuple[NormalizedDocument, ...], dict[tuple[str, str], dict[str, tuple[str, str, str, bool] | None]]]:
    catalog = catalog_for(root)
    entry = catalog.resolve("main")
    normalizer = DocumentNormalizer()
    documents = []
    ranges = {}
    for loaded in VaultLoader().load_documents(entry=entry, scope=catalog.default_scope()):
        documents.append(normalizer.normalize(loaded))
        assert loaded.extracted_document is not None
        ranges[(loaded.vault_id, loaded.path)] = exchange_ranges(loaded.extracted_document)
    return tuple(documents), ranges


def parents(documents: tuple[NormalizedDocument, ...], path: str) -> set[str]:
    (document,) = (item for item in documents if item.document.path == path)
    return {chunk.parent_key for chunk in document.chunks if chunk.parent_key is not None}


def test_group_key_is_agent_and_session_id_of_session_files_only() -> None:
    assert session_group_key({"schema": "vault-session/v1", "agent": "claude-code", "session_id": SESSION}) == (
        f"claude-code:{SESSION}"
    )
    assert session_group_key({"schema": "vault-session/v2", "agent": "claude-code", "session_id": SESSION}) == (
        f"claude-code:{SESSION}"
    )
    assert session_group_key({"schema": "vault-session/v1", "session_id": SESSION}) is None
    assert session_group_key({"title": "Note", "agent": "claude-code", "session_id": SESSION}) is None


def test_exchange_ranges_read_v1_turn_times_and_v2_meta_times(tmp_path: Path) -> None:
    _, ranges = load(session_vault(tmp_path / "vault"))

    v1 = ranges[("main", V1_PART1_PATH)]
    assert v1[f"{V1_PART1_PATH}:2026-11-03T14:00:00.000Z user:1"] == (
        "2026-11-03T14:00:00.000Z",
        "2026-11-03T14:06:01.000Z",
        "main",
        True,
    )
    assert v1[KEPT_V1_PART1_EXCHANGE] == ("2026-11-03T14:07:00.000Z", "2026-11-03T14:07:05.000Z", "main", True)
    subagent_range = v1[f"{V1_PART1_PATH}:2026-11-03T14:00:02.000Z subagent a7f3 user:1"]
    assert subagent_range is not None and subagent_range[2] == "subagent:a7f3"
    v2 = ranges[("main", V2_PART3_PATH)]
    assert v2 == {
        f"{SESSION}:u-201": ("2026-11-03T14:00:00.000Z", "2026-11-03T14:06:01.000Z", "main", True),
        f"{SESSION}:s-301": ("2026-11-03T14:00:02.000Z", "2026-11-03T14:00:05.000Z", "subagent:a7f3", True),
    }
    assert ranges[("main", NOTE_PATH)] == {}


def test_v1_exchanges_inside_a_v2_time_range_are_left_out(tmp_path: Path) -> None:
    documents, ranges = load(session_vault(tmp_path / "vault"))
    before_v1_part1 = parents(documents, V1_PART1_PATH)
    assert OVERLAPPED_V1_EXCHANGES <= before_v1_part1

    result, warnings = reprocess_session_groups(documents, ranges)

    assert parents(result, V1_PART1_PATH) == {KEPT_V1_PART1_EXCHANGE}
    assert parents(result, V1_PART2_PATH) == parents(documents, V1_PART2_PATH)
    assert parents(result, V2_PART3_PATH) == {f"{SESSION}:u-201", f"{SESSION}:s-301"}
    assert [item.document.path for item in result] == [item.document.path for item in documents]
    assert warnings == ()


def test_v1_without_v2_in_its_group_keeps_every_exchange(tmp_path: Path) -> None:
    documents, ranges = load(session_vault(tmp_path / "vault", with_v2=False))

    result, warnings = reprocess_session_groups(documents, ranges)

    assert result == documents
    assert warnings == ()


def test_v2_of_another_session_does_not_remove_v1_exchanges(tmp_path: Path) -> None:
    root = session_vault(tmp_path / "vault", with_v2=False)
    write(root, V2_PART3_PATH, v2_part3_text().replace(SESSION, "99999999-9999-4999-8999-999999999999"))
    documents, ranges = load(root)

    result, _ = reprocess_session_groups(documents, ranges)

    assert parents(result, V1_PART1_PATH) == parents(documents, V1_PART1_PATH)


def test_v2_exchange_without_times_keeps_every_v1_exchange_and_warns_once(tmp_path: Path) -> None:
    root = session_vault(tmp_path / "vault", with_v2=False)
    text = v2_part3_text()
    text = text.replace(" started=2026-11-03T14:00:00.000Z ended=2026-11-03T14:06:01.000Z", "")
    text = text.replace(" started=2026-11-03T14:00:02.000Z", "")
    write(root, V2_PART3_PATH, text)
    documents, ranges = load(root)

    result, warnings = reprocess_session_groups(documents, ranges)

    assert parents(result, V1_PART1_PATH) == parents(documents, V1_PART1_PATH)
    assert len(warnings) == 1
    assert warnings[0].startswith("session_overlap_time_missing: ")
    assert V2_PART3_PATH in warnings[0]


def test_incomplete_group_keeps_every_v1_exchange_and_warns_once(tmp_path: Path) -> None:
    documents, ranges = load(session_vault(tmp_path / "vault"))

    result, warnings = reprocess_session_groups(
        documents, ranges, incomplete_groups={("main", f"claude-code:{SESSION}"): (V1_PART2_PATH,)}
    )

    assert parents(result, V1_PART1_PATH) == parents(documents, V1_PART1_PATH)
    assert len(warnings) == 1
    assert warnings[0].startswith("session_group_incomplete: ")
    assert V1_PART2_PATH in warnings[0]


def test_same_exchange_id_in_two_v2_files_stays_only_in_the_path_first_file(tmp_path: Path) -> None:
    root = tmp_path / "vault"
    write(root, f"{SESSION_DIR}/{V2_4444_PART1.name}", V2_4444_PART1.read_text(encoding="utf-8"))
    write(root, f"{SESSION_DIR}/{V2_4444_PART3.name}", V2_4444_PART3.read_text(encoding="utf-8"))
    documents, ranges = load(root)

    result, warnings = reprocess_session_groups(documents, ranges)

    session = "44444444-4444-4444-8444-444444444444"
    assert parents(result, f"{SESSION_DIR}/{V2_4444_PART1.name}") == {
        f"{session}:u-401",
        f"{session}:u-410",
        f"{session}:u-420",
    }
    assert parents(result, f"{SESSION_DIR}/{V2_4444_PART3.name}") == set()
    assert len(warnings) == 2
    assert all(warning.startswith("session_exchange_duplicate: ") for warning in warnings)


def test_indexing_leaves_vault_files_byte_for_byte_unchanged(tmp_path: Path) -> None:
    root = session_vault(tmp_path / "vault")

    def digests() -> dict[str, str]:
        return {
            path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(root.rglob("*"))
            if path.is_file()
        }

    before = digests()
    catalog = catalog_for(root)
    store = SQLiteMetadataStore(tmp_path / "store" / "metadata.sqlite3", initialize=True)
    indexer = MetadataIndexer(catalog=catalog, metadata_store=store)
    indexer.apply(scope=catalog.default_scope())
    indexer.apply(scope=catalog.default_scope(), full=True)

    assert digests() == before


def test_v1_part_starting_at_the_last_v2_turn_keeps_its_later_exchange(tmp_path: Path) -> None:
    """A continued v1 part opens with the last assistant turn of the v2 range (14:06:01) and then a new
    exchange at 14:10:00. Ranges that only touch at 14:06:01 do not overlap, so the new exchange, which no
    v2 file holds, stays searchable."""
    root = session_vault(tmp_path / "vault")
    continued = V1_PART2.replace(
        "\n## 2026-11-03T14:10:00.000Z user\n",
        "\n## 2026-11-03T14:06:01.000Z assistant\n\nThe secret is masked now.\n\n## 2026-11-03T14:10:00.000Z user\n",
    ).replace('first_turn_at: "2026-11-03T14:10:00.000Z"', 'first_turn_at: "2026-11-03T14:06:01.000Z"')
    write(root, V1_PART2_PATH, continued)
    documents, ranges = load(root)
    assert parents(documents, V1_PART2_PATH)

    result, _ = reprocess_session_groups(documents, ranges)

    assert parents(result, V1_PART2_PATH) == parents(documents, V1_PART2_PATH)


def test_v2_subagent_exchange_does_not_remove_a_v1_main_exchange(tmp_path: Path) -> None:
    """The v2 subagent exchange runs from 14:09 to 14:11, over the v1 main exchange at 14:10. The v2 file
    holds no main exchange for that time, so the v1 main exchange is the only copy and stays searchable."""
    root = session_vault(tmp_path / "vault")
    write(
        root,
        V2_PART3_PATH,
        v2_part3_text().replace(
            "scope=subagent:a7f3 started=2026-11-03T14:00:02.000Z ended=2026-11-03T14:00:05.000Z",
            "scope=subagent:a7f3 started=2026-11-03T14:09:00.000Z ended=2026-11-03T14:11:00.000Z",
        ),
    )
    documents, ranges = load(root)
    assert parents(documents, V1_PART2_PATH)

    result, _ = reprocess_session_groups(documents, ranges)

    assert parents(result, V1_PART2_PATH) == parents(documents, V1_PART2_PATH)


def test_continued_v2_copy_removes_only_v1_exchanges_its_turns_cover(tmp_path: Path) -> None:
    """The v2 part starts inside the main exchange (`continued=1`). Its meta times still say 14:00 to
    14:06:01, but the file holds no turn of that exchange before the cut, so the v1 main exchange at
    14:00 is the only copy of those turns and stays searchable."""
    root = session_vault(tmp_path / "vault")
    text = v2_part3_text()
    meta = "<!-- vg:exchange id=u-201 scope=main started=2026-11-03T14:00:00.000Z ended=2026-11-03T14:06:01.000Z"
    assert meta in text
    start = text.index(meta)
    end = text.index("\n", start)
    first_turn = text.index("\n### ", end)
    second_turn = text.index("\n### ", first_turn + 1)
    line = text[start:end].replace(" -->", " continued=1 -->")
    write(root, V2_PART3_PATH, text[:start] + line + "\n" + text[second_turn:])
    documents, ranges = load(root)
    main_exchange = f"{V1_PART1_PATH}:2026-11-03T14:00:00.000Z user:1"
    assert main_exchange in parents(documents, V1_PART1_PATH)

    result, _ = reprocess_session_groups(documents, ranges)

    assert main_exchange in parents(result, V1_PART1_PATH)
