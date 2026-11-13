# 19. S8c 검색 질의 기록 (`usage/`)

## id
19

## title
에이전트가 던진 검색 질의와 그 뒤에 연 페이지를 Graph Home `usage/`에 남긴다

## goal
층1 질문을 고를 재료가 생긴다. 의도3을 담당한다(결정13).

## files
(경로는 코드에서 확인함: 기록은 `JsonlUsageLog.append_events`, 이벤트 빌더는 recall.py의 `fetched_event` 옆)
- src/vault_graph/interface/mcp/mcp_tools.py
- src/vault_graph/interface/mcp/mcp_service_factory.py
- src/vault_graph/context/pack/recall.py
- tests/test_usage_log.py
- tests/test_mcp_search_query_log.py (신규)

## blockers
12, 17

## acceptance
spec 4.3.4, 6장(결정13). A-11에는 직접 대응하지 않는다.

## checks
- `uv run --python 3.12 pytest -q tests/test_usage_log.py tests/test_mcp_search_query_log.py tests/test_mcp_resource_usage_log.py tests/test_mcp_tools.py`
- `uv run --python 3.12 ruff check src tests`
- `uv run --python 3.12 mypy src tests`

## done-when
- [ ] 질의 문자열에 `operation/sessions/redact.py`의 가림 규칙을 적용한 뒤 `usage/`에 기록한다.
- [ ] Vault에는 쓰지 않는다.
- [ ] 평가 실행 중에는 기록하지 않는다.
- [ ] `queries` 사용 비율을 기록한다(위험3).
