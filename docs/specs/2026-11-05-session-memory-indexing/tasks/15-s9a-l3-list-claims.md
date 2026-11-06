## id
15

## title
S9a L3 목록과 claim 행 대체 제외: `current_claims`, L3 목록 계산

## goal
대체된 claim 행이 회상과 L3에서 빠지고, 목록은 저장 없이 색인에서 계산된다. (Intent 8)

## spec
§4.4.6 대체 제외, §4.4.7 L3 목록, 위험D3

## acceptance
A-25(claim 부분), A-27(S9)

## files
- src/vault_graph/context/memory/claims.py (신규)
- src/vault_graph/context/memory/project_memory.py
- tests/test_current_claims.py (신규)
- tests/test_l3_list.py (신규)

## blockers
1, 10

## checks
pytest tests/test_current_claims.py tests/test_l3_list.py tests/test_project_memory_service.py -q

## wave
4

## done-when
- [ ] claim 표(`OPERATING-SCHEMA.md:192-200`)의 `superseded` 행이 목록에서 빠지고 현재 행은 남는다
- [ ] 형식을 읽지 못하면 그 페이지는 페이지 단위로만 다루고 경고 한 줄이다
- [ ] Graph Home과 Vault에 L3 목록 파일이 없다
- [ ] vault-graph pytest 전체 통과, 독립 커밋

## notes
시작 때 실제 페이지로 claim 표 파서를 검증한다(위험D3).
