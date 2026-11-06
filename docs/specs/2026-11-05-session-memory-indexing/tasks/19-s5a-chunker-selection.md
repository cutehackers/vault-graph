## id
19

## title
S5a 조각기 선택: `select_chunker`, Protocol `embedding_input`, `embedding_input_for`, `ChunkSnapshot` 선택 필드

## goal
세션 조각기를 끼울 자리가 생기고, 일반 문서의 동작은 바이트 단위로 그대로다. (Intent 3, 4)

## spec
§4.2.6-1·2, §4.2.6-6·8의 필드, §4.2.9

## acceptance
A-4(일반 문서, 알 수 없는 v9)

## files
- src/vault_graph/indexing/ingestion/chunker_selection.py (신규)
- src/vault_graph/indexing/ingestion/document_chunking.py
- src/vault_graph/indexing/ingestion/document_normalizer.py
- src/vault_graph/indexing/ingestion/document_snapshots.py
- src/vault_graph/indexing/vector_index_adapter.py
- tests/test_document_chunking.py
- tests/test_chunker_selection.py (신규)

## blockers
1, 17, 3, 4

## checks
pytest tests/test_chunker_selection.py tests/test_document_chunking.py tests/test_vector_indexer.py tests/test_feature_import_direction.py -q

## wave
6

## done-when
- [ ] `schema` 없는 파일과 일반 문서의 조각 id, `text`, `source_locators`, 임베딩 입력이 `abc77e7`과 바이트 단위로 같다
- [ ] 모르는 `vault-session/v9`는 일반 조각기와 경고 한 줄이다
- [ ] M03 → M02 가져오기가 허용 방향 테스트를 통과한다
- [ ] vault-graph pytest 전체 통과, 독립 커밋

## notes
시작 때 실제 세션 파일로 새 조각기를 dry-run해 조각 수를 센다(위험A1, 읽기 전용, 사람 컴퓨터 필요). 결과는 #31 보고서에 합친다.
