# 6. time-columns

## id
6

## title
교환마다 시작·끝 시각을 메타데이터 저장소에 색인한다

## goal
날짜로 거를 수 있는 열이 생긴다. 원문 창과 조각 id는 바이트 단위로 같다. Intent 2를 맡는다.

## units
D8, I1, F4, A3, A7

## files
- src/vault_graph/indexing/ingestion/session_exchange_v2_chunker.py
- src/vault_graph/storage/local/sqlite_metadata_store.py
- tests/test_session_exchange_v2_chunker.py

## blockers
1, 2, 3

## checks
- tests/test_session_exchange_v2_chunker.py

## done-when
- [ ] `chunks` 표 새 열이 메타 줄 `started`·`ended`, `first_turn_at`, 파일 이름 날짜 순으로 채워진다
- [ ] 셋 다 없으면 열이 비고 색인 경고가 하나 남는다
- [ ] 스키마 판을 올려 메타데이터만 다시 색인하고 벡터는 다시 만들지 않는다
- [ ] 창 `text`, 조각 id, `source_locators`, 임베딩 입력이 변경 전 고정값과 바이트 단위로 같다
