## id
28

## title
S10b 정리 꾸러미 1: L1·세션 교환 후보, 처리 기록, 비교 재료 포트

## goal
결정적인 후보 목록과 "처리한 후보는 다시 안 올린다"는 규칙이 있다. (Intent 6)

## spec
§4.4.4 표와 빠지는 규칙 1~3, 위험D2, 위험D11

## acceptance
A-22(L1·세션 교환), A-38(근거 판단, 180일)

## files
- src/vault_graph/context/memory/memory_candidates.py (신규)
- src/vault_graph/storage/local/reviewed_log.py (신규)
- tests/test_memory_candidates_l1_session.py (신규)
- tests/test_reviewed_log.py (신규)

## blockers
1, 18, 24

## checks
pytest tests/test_memory_candidates_l1_session.py tests/test_reviewed_log.py -q

## wave
9

## done-when
- [ ] 같은 상태로 두 번 부르면 결과가 같고, 파일 경로만 적은 근거는 교환을 빼지 않고 줄 범위를 적은 근거는 그 교환만 뺀다
- [ ] 180일보다 오래된 교환은 후보에 없다
- [ ] `reviewed.jsonl`은 Graph Home에만 있고 지우면 후보가 다시 나온다
- [ ] vault-graph pytest 전체 통과, 독립 커밋

## notes
비교 재료는 `SimilarPageFinder` 포트로 받고 가짜로 테스트한다. 실제 연결은 #32다. 시작 때 Vault 근거 표기 규칙(`OPERATING-SCHEMA.md`, `ingest.py:44`)과 실제 페이지를 읽는다(위험D2, D11). 요청S8과 무관하다.
