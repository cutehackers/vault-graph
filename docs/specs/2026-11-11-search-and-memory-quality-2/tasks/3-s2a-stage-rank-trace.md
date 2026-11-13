# 3. S2a 검색 단계별 순위 추적 훅

## id
3

## title
검색 서비스가 신호별 순위와 합친 뒤 순위를 추적해 돌려주게 한다

## goal
평가 도구가 정답의 키워드·벡터·그래프 순위, 합친 뒤 조각 순위, 문서 순위를 읽을 수 있다. 의도1(정답을 잃는 단계를 기록한다)을 담당한다. 첫 PR 범위에 든다.

## files
- src/vault_graph/retrieval/search/retrieval_service.py
- src/vault_graph/retrieval/search/candidate_ranking.py
- src/vault_graph/retrieval/search/search_response.py
- tests/test_retrieval_service_search.py
- tests/test_retrieval_stage_trace.py (신규)

## blockers
없음

## acceptance
A-3 (단계별 순위 기록의 전제)

## checks
- `uv run --python 3.12 pytest -q tests/test_retrieval_service_search.py tests/test_retrieval_stage_trace.py tests/test_retrieval_result_contract.py tests/test_graph_retrieval_service.py`
- `uv run --python 3.12 ruff check src tests`
- `uv run --python 3.12 mypy src tests`

## done-when
- [ ] 추적을 끄면 기본 검색 결과와 순서가 변하지 않고 기존 검색 테스트가 통과한다.
- [ ] 추적을 켜면 신호별 순위, 합친 뒤 조각 순위, 문서로 접은 뒤 순위를 돌려준다.
- [ ] 추적이 사용 기록을 남기지 않는다.
