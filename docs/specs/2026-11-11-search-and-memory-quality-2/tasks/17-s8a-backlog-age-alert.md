# 17. S8a 정리 대기 나이 중앙값과 회상 맨 위 알림

## id
17

## title
정리 대기 줄에 나이 중앙값을 넣고 기준을 넘으면 회상 맨 위로 올린다

## goal
정리가 밀리면 세션 시작 회상 맨 위에 알림이 뜬다. 의도3을 담당한다. 정리는 자동으로 돌리지 않는다(결정12).

## files
- src/vault_graph/context/pack/recall_backlog.py
- src/vault_graph/context/pack/recall.py
- src/vault_graph/interface/composition/memory_candidate_sources.py (`CandidateBacklogCounter`가 나이를 돌려주게 함)
- tests/test_recall_backlog.py

## blockers
1, 13, 14

## acceptance
A-11 (알림 부분)

## checks
- `uv run --python 3.12 pytest -q tests/test_recall_backlog.py tests/test_cli_hook_session_start.py tests/test_recall_budget.py`
- `uv run --python 3.12 ruff check src tests`
- `uv run --python 3.12 mypy src tests`

## done-when
- [ ] "정리 대기" 줄에 나이 중앙값이 들어간다.
- [ ] 중앙값이 목표7(결정8로 확정된 값, 가정은 7일)을 넘으면 그 줄이 회상 맨 위로 올라가고 "지금 정리가 필요하다"가 적힌다.
- [ ] 정리를 자동으로 돌리는 코드를 넣지 않는다(결정12).
