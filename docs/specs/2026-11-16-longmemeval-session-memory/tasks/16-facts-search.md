# 16. facts-search

## id
16

## title
사실 키 맞음을 원 교환으로 바꾸고 `include_fact_keys`로 뺀다

## goal
사실만 맞은 질문도 원 세션 교환을 근거로 받는다. 사실 텍스트는 응답에 나오지 않는다. Intent 3을 맡는다.

## units
D21, I3, I6, F12, A18

## files
- src/vault_graph/retrieval/search/evidence_result_assembly.py
- src/vault_graph/retrieval/search/search_response.py
- src/vault_graph/retrieval/search/retrieval_service.py
- src/vault_graph/retrieval/search/candidate_ranking.py
- tests/test_session_facts_index.py

## blockers
15

## checks
- tests/test_session_facts_index.py

## done-when
- [ ] 사실 조각 가중치가 keyword·vector보다 낮게 시작한다
- [ ] 사실만 맞은 단위가 원 교환의 첫 창으로 바뀌어 발췌와 근거가 원문에서 온다
- [ ] 원 교환 창이 색인에 없으면 사실 조각을 버리고 `fact_source_missing` 경고를 붙인다
- [ ] 사실 텍스트가 발췌, 제목, 근거 경로에 나오지 않는다
- [ ] `include_fact_keys=false`와 첨부 없는 Vault의 결과가 B 전과 같다
