# 20. S9 색인 전 키워드 검색 (2단계 따라잡기)

## id
20

## title
첫 세션 시작의 따라잡기 색인을 `--no-vector` 1단계와 벡터 2단계로 나눈다

## goal
첫 세션 시작 뒤 벡터 색인이 끝나기 전에도 키워드 검색이 된다. 의도4를 담당한다. 첫 PR 범위에 든다.

## files
(경로는 코드에서 확인함: 따라잡기 프로세스는 hook_commands.py의 `run_catch_up_index`와 `_run_vg_index`, 벡터 필요 판단은 recall_index_refresh.py의 `vectors_need_catch_up`)
- src/vault_graph/interface/cli/hook_commands.py
- src/vault_graph/interface/composition/recall_index_refresh.py
- tests/test_cli_hook_session_start.py
- tests/test_catch_up_two_stage.py (신규)

## blockers
1

## acceptance
A-12

## checks
- `uv run --python 3.12 pytest -q tests/test_catch_up_two_stage.py tests/test_cli_hook_session_start.py`
- `uv run --python 3.12 ruff check src tests`
- `uv run --python 3.12 mypy src tests`

## done-when
- [ ] 구현 전에 Vault 6개로 `--no-vector` 1단계 시간을 재서 기록했다.
- [ ] 색인이 없는 Graph Home에서 따라잡기가 `--no-vector` 색인, 벡터 색인 순서로 돈다.
- [ ] 1단계가 끝난 뒤 `search_vault`가 키워드 결과와 `vector_stale` 경고를 낸다.
