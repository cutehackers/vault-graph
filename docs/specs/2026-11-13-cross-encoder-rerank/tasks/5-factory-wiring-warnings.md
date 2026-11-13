# 작업 5. 읽기 전용 팩토리와 CLI 검색에 연결, 경고와 기본 꺼짐

## id

5

## title

읽기 전용 팩토리와 CLI 검색에 연결, 경고와 기본 꺼짐

## goal

설정이 켜져 있으면 MCP·HTTP·CLI 검색이 실제 모델로 재정렬하고, 안 되면 기존 순서에 경고 하나만 붙여 답한다. 설정이 없거나 꺼져 있으면 결과가 변경 전과 같다(Intent 2, 3).

## units

I3, D11, D17, F1, F2, F3, A2, A7

## files

- `src/vault_graph/interface/composition/read_only_service_factory.py`
- `src/vault_graph/interface/cli/main.py`
- `src/vault_graph/retrieval/search/retrieval_service.py`
- `src/vault_graph/retrieval/search/reranker.py`
- `tests/test_reranker.py`
- `tests/test_reranker_config.py`
- `tests/test_retrieval_service_search.py`

## blockers

1, 2, 3, 4

## checks

- `tests/test_reranker.py`
- `tests/test_reranker_config.py`
- `tests/test_retrieval_service_search.py`

## done-when

- [ ] 읽기 전용 팩토리와 CLI 검색이 `configs/reranker.json`을 읽어 켜져 있을 때만 `Reranker`를 서비스에 넘긴다.
- [ ] 설정 파일이 없거나 `enabled: false`이면 순서, `rank`, `result_id`, 경고, `stage_trace`가 변경 전과 같다.
- [ ] 모델 파일이 없으면 기존 순서와 `reranker_unavailable` 경고 하나로 답한다. 경고는 `vg reranker use <preset>`을 안내하고 내려받거나 다른 모델로 바꾸지 않는다. 모델 확인은 첫 재정렬 때 한 번 한다.
- [ ] 재정렬 중 `RerankError`는 기존 순서와 `rerank_failed` 경고 하나로 답한다. 그 질의에만 적용되고 다음 질의는 다시 시도한다.
- [ ] JSON 오류, `version` 불일치, 목록에 없는 `model`이면 재정렬을 끄고 `reranker_config_invalid` 경고 하나로 답한다. 검색은 실패하지 않는다.
- [ ] 세 경고 중 정확히 하나만 붙고 예외가 없다.
- [ ] 기본값은 꺼짐이고 `vg setup`은 재정렬 모델을 받지 않는다.
