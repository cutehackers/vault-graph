## id
17

## title
S2c 임베딩 캐시: Graph Home `cache/embeddings.sqlite3`

## goal
캐시가 데워지면 `--full`도 모델을 열지 않고, 죽은 run이 캐시로 이어진다. (Intent 5)

## spec
§4.3.5, §6 캐시 행

## acceptance
A-17

## files
- src/vault_graph/storage/local/embedding_cache.py (신규)
- src/vault_graph/indexing/vector_index_adapter.py
- src/vault_graph/interface/composition/local_index_service_factory.py
- tests/test_embedding_cache.py (신규)
- tests/test_vector_index_cache_integration.py (신규)

## blockers
1, 13

## checks
pytest tests/test_embedding_cache.py tests/test_vector_index_cache_integration.py -q

## wave
5

## done-when
- [ ] 캐시가 데워진 `--full`의 모델 입력이 0개다
- [ ] 캐시를 지우고 다시 만든 벡터가 같다
- [ ] 발행 뒤 캐시 키 수가 활성 세대 벡터 수 이하이고, 깨진 캐시는 경고 한 줄로 우회한다
- [ ] vault-graph pytest 전체 통과, 독립 커밋

## notes
캐시는 세대 밖이며 지워도 다음 run이 다시 임베딩할 뿐이다.
