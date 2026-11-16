# 23. c-event-dates

## id
23

## title
날짜 범위를 사실의 사건 날짜까지 넓히고, 범위 안 결과를 먼저 채운다

## goal
첫 C가 세션 날짜로만 걸러 LongMemEval에서 나빠진 문제(X24)를 논문 방식(X25)으로 고친다. 교환 시각이나 그 교환 사실의 사건 날짜가 범위 안이면 범위 안이고, 범위 안 결과를 먼저 채운 뒤 남은 칸을 범위 밖 결과로 채운다. 비교용 엄격 모드를 둔다.

## units
D9, D11, D12, D30, D31, A6, A9

## files
- src/vault_graph/storage/interfaces/metadata_store.py
- src/vault_graph/storage/local/sqlite_metadata_store.py
- src/vault_graph/retrieval/search/search_response.py
- src/vault_graph/retrieval/search/retrieval_service.py
- src/vault_graph/interface/cli/main.py
- src/vault_graph/interface/mcp/mcp_tools.py
- tests/benchmarks/longmemeval_run.py
- tests/test_retrieval_service_search.py
- tests/test_cli_search.py
- tests/test_mcp_tools.py
- tests/test_longmemeval_run_session_count.py

## blockers
11, 16

## checks
- tests/test_retrieval_service_search.py
- tests/test_cli_search.py
- tests/test_mcp_tools.py
- tests/test_longmemeval_run_session_count.py

## done-when
- [ ] 메타데이터 저장소의 범위 조회가 사실 조각 날짜가 범위 안인 교환의 조각도 범위 안으로 준다(D30)
- [ ] 범위를 주면 범위 안 결과가 먼저 오고 남은 칸은 범위 없는 같은 검색의 결과로 채워진다(D31)
- [ ] 엄격 모드(`vg search --date-strict`, 검색 요청 필드)는 범위 안 결과만 남기고 `date_unknown_excluded`·`date_range_empty`를 붙인다
- [ ] 범위가 없으면 후보, 순서, 경고, `stage_trace`가 변경 전과 같다(I5)
- [ ] MCP 세 도구 설명이 범위는 대화 시기나 사건 시기를 가리킬 수 있고 범위 안 결과가 먼저 온다고 적는다
- [ ] `longmemeval_run --date-rules`에 엄격 모드를 고르는 인자가 있다
