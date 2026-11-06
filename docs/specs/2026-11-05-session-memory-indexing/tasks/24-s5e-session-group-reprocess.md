## id
24

## title
S5e 같은 세션 묶음 재처리: `session_group_key`, v1·v2 겹침 제외, 중복 교환 id, family 재계획

## goal
증분 색인 결과가 full run 결과와 같고, 겹친 v1 교환은 색인에서만 빠진다. (Intent 4, 5)

## spec
§4.2.7 마지막, §4.2.13, §6

## acceptance
A-9, A-36

## files
- src/vault_graph/indexing/metadata_indexer.py
- src/vault_graph/storage/local/sqlite_metadata_store.py
- src/vault_graph/storage/interfaces/metadata_store.py
- src/vault_graph/indexing/ingestion/session_group.py (신규)
- tests/test_session_group_reprocess.py (신규)
- tests/test_session_v1_v2_overlap.py (신규)

## blockers
1, 4, 21, 22, 23

## checks
pytest tests/test_session_group_reprocess.py tests/test_session_v1_v2_overlap.py tests/test_metadata_indexer.py -q

## wave
8

## done-when
- [ ] v1 파트 둘 + v2 파트 하나의 증분 결과(조각 id 집합, 키워드 행, 벡터 메타데이터)가 full run과 같고, v2를 지우면 v1 교환이 돌아온다
- [ ] `supersedes` family가 바뀐 문서에서도 증분과 full이 같고, 바뀐 파일이 없는 묶음은 열지 않는다
- [ ] 색인 전후 Vault 파일 sha256이 같다
- [ ] 시각이 없는 v2 교환은 v1을 하나도 빼지 않고 경고한다
- [ ] vault-graph pytest 전체 통과, 독립 커밋

## notes
묶음 키는 frontmatter의 (`agent`, `session_id`)다. 같은 묶음의 다른 파일을 읽지 못하면 겹침 제외를 하지 않고 경고한다.
