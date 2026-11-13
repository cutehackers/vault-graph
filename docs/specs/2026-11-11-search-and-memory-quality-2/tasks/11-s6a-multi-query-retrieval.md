# 11. S6a 여러 표현 질의 합치기 (검색 서비스)

## id
11

## title
검색 서비스가 질의 1~4개의 후보를 같은 RRF로 합친다

## goal
검색 서비스가 질의 여러 개의 후보를 결정적으로 합친다. 의도2(방안A)를 담당한다.

## files
- src/vault_graph/retrieval/search/retrieval_service.py
- src/vault_graph/retrieval/search/candidate_ranking.py
- tests/test_retrieval_multi_query.py (신규)

## blockers
10

## acceptance
A-8 (결정적 결과와 오류 규칙 부분)

## checks
- `uv run --python 3.12 pytest -q tests/test_retrieval_multi_query.py tests/test_retrieval_service_search.py tests/test_retrieval_stage_trace.py`
- `uv run --python 3.12 ruff check src tests`
- `uv run --python 3.12 mypy src tests`

## done-when
- [ ] 질의 1~4개를 받아 표현마다 후보를 뽑고 RRF로 합친다. 같은 입력이면 같은 결과다.
- [ ] 빈 목록이나 4개 초과는 오류다.
- [ ] 표현 하나가 실패하면 나머지로 답하고 경고를 넣는다.
- [ ] 질의 하나일 때 결과가 이전과 같다.
