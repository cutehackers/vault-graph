## id
9

## title
S2a 벡터 목록 표: `VectorManifestStore` 포트와 SQLite 구현, 계획이 표를 읽게 함

## goal
증분 계획이 Chroma 전체 조회 없이 표로 돈다. (Intent 5)

## spec
§4.3.1 근본

## acceptance
A-15

## files
- src/vault_graph/storage/interfaces/vector_manifest_store.py (신규)
- src/vault_graph/storage/local/sqlite_vector_manifest_store.py (신규)
- src/vault_graph/indexing/vector_index_adapter.py
- tests/test_vector_manifest_store.py (신규)
- tests/test_vector_manifest_rebuild.py (신규)

## blockers
1, 2

## checks
pytest tests/test_vector_manifest_store.py tests/test_vector_manifest_rebuild.py tests/test_index_service_vector_reconcile.py -q

## wave
3

## done-when
- [ ] 증분 계획 중 Chroma 목록 조회가 한 번도 불리지 않는다
- [ ] 표 삭제나 행 하나 삭제 뒤 증분 색인이 표를 다시 만들고 계획이 같다
- [ ] Chroma 쓰기에 성공한 배치만 표에 쓴다
- [ ] vault-graph pytest 전체 통과, 독립 커밋

## notes
표 위치는 세대의 `vector/manifest.sqlite3`다.
