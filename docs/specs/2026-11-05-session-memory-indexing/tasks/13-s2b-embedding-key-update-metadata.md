## id
13

## title
S2b 임베딩 키와 메타데이터 지문 분리, `update_metadata`

## goal
내용이 같은 조각은 지문이 달라도 다시 임베딩하지 않고, 덧붙인 만큼만 임베딩한다. (Intent 5)

## spec
§4.3.2, 위험B2

## acceptance
A-14

## files
- packages/vector-index/src/vector_index/planning.py (실제 계획 모듈 이름은 시작 때 확인)
- src/vault_graph/storage/interfaces/vector_store.py
- src/vault_graph/storage/local/chroma_vector_store.py
- src/vault_graph/indexing/vector_index_adapter.py
- tests/test_vector_embedding_key_plan.py (신규)
- tests/test_chroma_update_metadata.py (신규)

## blockers
1, 9

## checks
pytest tests/test_vector_embedding_key_plan.py tests/test_chroma_update_metadata.py tests/test_vector_store_contract.py packages/vector-index/tests -q

## wave
4

## done-when
- [ ] 첫 테스트로 `update` 전후 Chroma 벡터 값이 같음을 확인했다(위험B2)
- [ ] 조각 100개 문서 끝에 20개 분량을 덧붙이면 모델 입력이 새 조각과 마지막 조각 합 이하이고, family만 바뀌면 0개다
- [ ] 처음 전환하는 run이 일반 문서의 임베딩 키만 채운다
- [ ] vault-graph pytest 전체 통과, 독립 커밋

## notes
`plan_index`에 선택 필드 `metadata_fingerprint`와 결과 `metadata_updates`를 더하는 것이 핵심이다. 필드가 없으면 지금 동작과 같아야 한다(`docs/SPEC.md` §8.3).
