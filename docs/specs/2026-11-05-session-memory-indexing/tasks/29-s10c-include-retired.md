## id
29

## title
S10c `include_retired`: 폐기 페이지 검색 옵션

## goal
에이전트가 폐기된 사실을 찾고 같은 내용을 다시 저장하지 않게 된다. (Intent 8)

## spec
§4.4.13-1

## acceptance
A-39(검색 부분), A-32(선택 입력)

## files
- src/vault_graph/retrieval/search/evidence_result_assembly.py
- src/vault_graph/interface/cli/main.py
- src/vault_graph/interface/mcp/mcp_tools.py
- tests/test_search_include_retired.py (신규)

## blockers
1, 23

## checks
pytest tests/test_search_include_retired.py tests/test_mcp_memory_tools.py -q

## wave
9

## done-when
- [ ] 옵션 없이는 폐기 페이지가 없고, 참이면 `status`, `retired_reason`, `retired_at`, `superseded_by`와 함께 나온다
- [ ] 회상 출력은 옵션과 상관없이 같다
- [ ] 기존 입력·출력 필드는 그대로다
- [ ] vault-graph pytest 전체 통과, 독립 커밋

## notes
`evidence_result_assembly.py`는 #23 뒤에 수정한다. `main.py`는 #8 뒤에 수정한다.
