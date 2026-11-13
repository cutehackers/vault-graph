# 작업 2. Reranker 포트, RRF 섞기, 재정렬 입력, 검색 서비스 연결

## id

2

## title

`Reranker` 포트, RRF 섞기, 재정렬 입력, 검색 서비스 연결

## goal

가짜 `Reranker`를 주입하면 검색이 refill 뒤 slice 앞에서 상위 30개를 RRF로 다시 정렬하고, 순위 번호와 `stage_trace`가 최종 순서를 따른다. 결과는 더하거나 빼지 않는다(Intent 1과 I1).

## units

I1, I4, I5, I6, D6, D7, D8, D12, D13, F4, F5, F9, F10, A3, A4, A5, A10, A11, A12

## files

- `src/vault_graph/retrieval/search/reranker.py`
- `src/vault_graph/retrieval/search/retrieval_service.py`
- `src/vault_graph/retrieval/search/evidence_result_assembly.py`
- `tests/test_reranker.py`
- `tests/test_retrieval_service_search.py`

## blockers

1

## checks

- `tests/test_reranker.py`
- `tests/test_retrieval_service_search.py`

## done-when

- [ ] `retrieval/search/reranker.py`에 포트 `Reranker.rerank(query, passages) -> list[int]`와 `RerankError`가 있다.
- [ ] RRF 섞기(`1/(k+기존 순위) + w/(k+재정렬 순위)`, 동점이면 기존 순위 우선)와 `rank`·`result_id` 재부여가 같은 파일에 있다. `k`, `w`, `N=30`은 임시 상수이고 작업 7이 고정한다.
- [ ] `resolve_results`가 결과마다 내부 전용 재정렬 텍스트를 함께 돌려주고 `RetrievalResult` 필드는 그대로다. 문서는 frontmatter title·summary와 가장 높은 조각 전문이고, `page_card`면 조각 전문만 쓴다. 세션은 인용 창이다. `resolve_chunk`를 다시 부르지 않는다.
- [ ] `RetrievalService`가 `Reranker`를 선택 인자로 받고, 없으면 기존 동작과 같다.
- [ ] 재정렬 위치는 refill 루프 뒤, `results[: request.limit]` 앞이다. 결과 집합이 같고 N 밖은 원래 순서로 뒤에 붙는다. 결과가 1개 이하면 모델을 부르지 않고 경고도 trace 항목도 없다.
- [ ] 여러 Vault 결과가 섞여도 Vault 이름과 종류가 그대로다.
- [ ] 정확한 제목 질의 시나리오에서 순서를 뒤집는 가짜 모델로도 RRF 식대로 나오는지 `tests/test_reranker.py`가 보인다.
- [ ] `stage_trace`의 `document_ranks`가 재정렬 뒤 순서이고, 재정렬이 돌면 `rerank` 항목(대상 수, 결과별 전 순위·모델 순위, 시간, preset)이 있다. 꺼져 있으면 항목이 없다.
- [ ] `evidence` 모드에서 세션 결과도 같은 경로로 재정렬되고 입력은 인용 창이다.
- [ ] 켠 검색 전후로 Vault, Graph Home, 모델 폴더의 파일 목록과 수정 시각이 같다. 켠 검색과 끈 검색의 `resolve_chunk` 호출 수도 같다.
