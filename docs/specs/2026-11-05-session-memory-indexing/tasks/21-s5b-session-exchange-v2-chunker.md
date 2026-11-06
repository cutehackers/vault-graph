## id
21

## title
S5b `session-exchange-v2` 조각기: 교환 읽기, 창 자르기, 조각 id, 위치, 512 토큰 경고

## goal
세션 조각이 도구 이름 한 줄이 아니라 교환 단위 창이 된다. (Intent 3, 4)

## spec
§4.2.6-3·4·5·7·9·10·11, §6 v2 행

## acceptance
A-4(v2), A-5

## files
- src/vault_graph/indexing/ingestion/session_exchange_v2_chunker.py (신규)
- tests/test_session_exchange_v2_chunker.py (신규)
- tests/test_session_chunk_id_stability.py (신규)
- tests/fixtures/session_v2/ (신규, 폴더 전체)

## blockers
1, 19

## checks
pytest tests/test_session_exchange_v2_chunker.py tests/test_session_chunk_id_stability.py -q

## wave
7

## done-when
- [ ] v2 고정 파일에서 숨은 메타 줄이 창 본문에 없고, 창은 공백 토큰 160 이하이며 겹치지 않는다
- [ ] renderer 버전과 파트 번호만 바꾼 사본의 조각 id가 같고, 새 파트가 기존 id를 바꾸지 않는다
- [ ] 메타 줄이 깨졌거나 교환 id가 두 파일에 있으면 경고 한 줄과 규칙대로 처리한다
- [ ] vault-graph pytest 전체 통과, 독립 커밋

## notes
고정 v2 파일은 요청S10 산출물이 없어도 4.2.5 계약으로 손으로 만든다. 실제 Vault 도구 출력과의 일치는 #25 E2E에서 확인한다.
