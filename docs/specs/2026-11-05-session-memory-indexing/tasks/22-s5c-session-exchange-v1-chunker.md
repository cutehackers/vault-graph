## id
22

## title
S5c `session-exchange-v1` 조각기

## goal
원본이 없는 v1 파일도 교환 단위로 색인된다. (Intent 3, 4)

## spec
§4.2.7(겹침 제외 제외), 위험A3

## acceptance
A-4(v1), A-9(v1 조각 0개 확인)

## files
- src/vault_graph/indexing/ingestion/session_exchange_v1_chunker.py (신규)
- tests/test_session_exchange_v1_chunker.py (신규)
- tests/fixtures/session_v1/ (신규, 폴더 전체)

## blockers
1, 19

## checks
pytest tests/test_session_exchange_v1_chunker.py -q

## wave
7

## done-when
- [ ] 고정 v1 파일(도구 전용 턴, 태그 감싼 user 턴, 서브에이전트, 이어진 교환, 160 초과 턴, 사람 턴 없음)이 기대 창 목록과 같다
- [ ] 고정 v1 파일 하나는 실제 `sessions capture` 결과를 고쳐서 만들었다
- [ ] 세션 파일에 `document-block-window-v2` 조각이 0개다
- [ ] vault-graph pytest 전체 통과, 독립 커밋

## notes
v1·v2 겹침 제외는 #24가 한다. 압축이 있었던 v1 파트 파일을 열어 본다(위험A3).
