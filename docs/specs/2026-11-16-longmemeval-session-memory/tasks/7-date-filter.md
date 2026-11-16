# 7. date-filter

## id
7

## title
`SearchRequest`에 `since`·`until`을 더하고 후보 단계에서 거른다

## goal
날짜 범위와 겹치는 교환만 후보로 올라온다. 범위가 없으면 지금과 같다. Intent 2를 맡는다.

## units
D9, D10, D11, I5, F6, A6

## files
- src/vault_graph/retrieval/search/search_response.py
- src/vault_graph/retrieval/search/retrieval_service.py
- src/vault_graph/storage/local/chroma_vector_store.py
- src/vault_graph/storage/local/vector_store_adapter.py
- src/vault_graph/storage/local/sqlite_keyword_index.py
- tests/test_retrieval_service_search.py

## blockers
6

## checks
- tests/test_retrieval_service_search.py

## done-when
- [ ] 메타데이터 저장소가 범위와 겹치는 조각 id를 주고, 키워드·벡터 검색이 그 안에서 후보를 만든다
- [ ] `since`·`until`은 양 끝 포함이고 이 컴퓨터 시간대로 비교한다
- [ ] 날짜 없는 결과는 빠지고 `date_unknown_excluded`에 개수가 있다
- [ ] 결과가 없으면 빈 목록과 `date_range_empty`다
- [ ] 범위가 없으면 후보, 순서, 경고, `stage_trace`가 변경 전과 같다
- [ ] R3의 검색 p95 1초를 재서 적는다
