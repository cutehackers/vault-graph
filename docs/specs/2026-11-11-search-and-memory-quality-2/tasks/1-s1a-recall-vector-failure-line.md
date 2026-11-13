# 1. S1a 벡터 실패 경고를 회상 출력에 넣는다

## id
1

## title
벡터 색인 실패 경고를 세션 시작 회상 출력(표준 출력)에 넣는다

## goal
벡터 색인 실패가 에이전트의 회상 문맥에 보인다. 의도4(기억이 검색에 닿는 경로를 지킨다, 색인 실패가 보인다)를 담당한다. 첫 PR 범위(작업 1, 2, 3, 4, 5, 8, 20)에 든다.

## files
- src/vault_graph/context/pack/recall.py
- src/vault_graph/interface/cli/hook_commands.py
- src/vault_graph/indexing/vector_failure_log.py
- tests/test_cli_hook_session_start.py
- tests/test_recall_l3_section.py (필요 시)

## blockers
없음

## acceptance
A-1

## checks
- `uv run --python 3.12 pytest -q tests/test_cli_hook_session_start.py tests/test_recall_l3_section.py tests/test_recall_budget.py`
- `uv run --python 3.12 ruff check src tests`
- `uv run --python 3.12 mypy src tests`

## done-when
- [ ] 실패 기록(`logs/vector-index-failures.json`)이 있으면 session-start 표준 출력의 "가져오는 방법" 절에 실패 한 줄이 있다.
- [ ] 표준 오류 경고는 그대로 나온다.
- [ ] 백그라운드 따라잡기 프로세스가 벡터 밖의 이유로 죽어도 같은 실패 기록에 남는다.
- [ ] 실패 기록이 없으면 출력이 이전과 같다.
