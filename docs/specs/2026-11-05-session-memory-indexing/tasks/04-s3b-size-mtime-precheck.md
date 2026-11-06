## id
4

## title
S3b 문서 표 `source_size`, `source_mtime_ns` 사전 검사

## goal
바뀐 파일이 없으면 Vault 파일을 하나도 열지 않는다. (Intent 5)

## spec
§4.3.3 둘째, 위험B4

## acceptance
A-18(사전 검사 부분)

## files
- src/vault_graph/indexing/metadata_indexer.py
- src/vault_graph/storage/local/sqlite_metadata_store.py
- src/vault_graph/storage/interfaces/metadata_store.py
- tests/test_metadata_precheck.py (신규)

## blockers
1

## checks
pytest tests/test_metadata_precheck.py tests/test_metadata_indexer.py tests/test_metadata_indexer_paths.py -q

## wave
2

## done-when
- [ ] 증분 run에서 `(size, mtime_ns)`가 같으면 파일을 열지 않고, 다르면 `content_hash`로 확정한다
- [ ] full run은 사전 검사를 보지 않는다
- [ ] git checkout과 `sessions capture` 뒤 mtime 변화를 기록한다(위험B4)
- [ ] vault-graph pytest 전체 통과, 독립 커밋

## notes
#24가 같은 파일에 `session_group_key`를 더한다. 사전 검사가 건너뛴 파일도 묶음에 들어가야 하므로 문서 표 스키마를 #24가 이어서 확장할 수 있게 둔다.
