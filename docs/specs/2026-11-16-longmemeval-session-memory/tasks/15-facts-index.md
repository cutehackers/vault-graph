# 15. facts-index

## id
15

## title
`.facts.md` 첨부를 읽어 `derived` 조각으로 색인한다

## goal
사실이 원 교환을 찾는 열쇠로만 색인된다. 원문 창은 그대로다. `docs/contracts/vault-session-facts-v1.md`를 따른다. Intent 3을 맡는다.

## units
D28, I1, A3

## files
- src/vault_graph/indexing/ingestion/session_facts_chunker.py
- src/vault_graph/indexing/ingestion/session_group.py
- src/vault_graph/indexing/ingestion/chunker_selection.py
- tests/test_session_facts_index.py

## blockers
6, 13

## checks
- tests/test_session_facts_index.py

## done-when
- [ ] `schema: vault-session-facts/v1`로 첨부를 알아보고 세션 묶음 규칙에는 넣지 않는다
- [ ] 줄마다 `parent_key`가 원 교환(`<session_id>:<exchange_id>`)이고 시각이 줄 날짜인 `derived` 조각이 하나 생긴다
- [ ] 모르는 판은 경고 하나와 함께 색인하지 않는다
- [ ] 첨부가 옆에 있어도 원문 창 `text`, 조각 id, `source_locators`, 임베딩 입력이 바이트 단위로 같다
- [ ] 새 파일이 `indexing/ingestion/`(M02)에 있어 `tests/test_feature_import_direction.py`를 어기지 않는다
