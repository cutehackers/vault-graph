## id
2

## title
S1 원인5: 토큰 예산 배치 반복자, 배치별 저장, 아레나 설정

## goal
전체 재색인의 메모리 상한을 만들 수 있다. 측정은 #20이 한다. (Intent 5)

## spec
§4.3.4, 위험B5

## acceptance
A-16(코드 부분)

## files
- packages/vector-index/src/vector_index/indexing.py
- src/vault_graph/indexing/vector_index_adapter.py
- src/vault_graph/interface/composition/adapters/text_embeddings.py
- src/vault_graph/interface/composition/local_index_service_factory.py
- packages/vector-index/tests/test_embedding_batches.py (신규)
- tests/test_vector_batch_persist.py (신규)

## blockers
1

## checks
pytest packages/vector-index/tests/test_embedding_batches.py tests/test_vector_batch_persist.py tests/test_vector_indexer.py -q

## wave
2

## done-when
- [ ] 모든 배치가 `항목 수 × 최대 추정 토큰 ≤ token_budget`과 `항목 수 ≤ max_batch_items`를 지키고, 배치마다 Chroma 쓰기가 한 번이다
- [ ] `embed_items`는 반복자를 모아 돌려주는 함수로 남고, `embedding_batch_size`만 있는 설정이 동작한다
- [ ] `cpu_mem_arena`가 설정으로 fastembed에 전달된다
- [ ] vault-graph pytest 전체 통과, 독립 커밋

## notes
`vector_index_adapter.py`는 #1, #9, #13, #17, #19가 차례로 수정한다(wave로 분리됨).
