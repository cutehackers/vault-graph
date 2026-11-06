## id
36

## title
S10g MCP 도구 5개, `curate_memory` prompt, 기존 도구 선택 입력

## goal
세션 안 에이전트가 "기억 정리해" 한 마디로 정리 흐름을 돌릴 수 있다. (Intent 6)

## spec
§4.4.4 MCP, §4.4.12, 호환 규칙

## acceptance
A-23, A-32, A-31, A-29(S10)

## files
- src/vault_graph/interface/mcp/mcp_tools.py
- src/vault_graph/interface/mcp/mcp_memory_tools.py
- src/vault_graph/interface/mcp/mcp_prompts.py
- src/vault_graph/interface/mcp/mcp_server.py
- tests/test_mcp_curation_tools.py (신규)
- tests/test_mcp_curate_prompt.py (신규)

## blockers
1, 27, 29, 32, 33

## checks
pytest tests/test_mcp_curation_tools.py tests/test_mcp_curate_prompt.py tests/test_mcp_memory_tools.py tests/test_mcp_memory_tools_module.py -q

## wave
11

## done-when
- [ ] `list_memory_candidates`, `mark_candidates_reviewed`, `import_auto_memory`, `supersede_claim`, `restore_memory`가 있고 총 19개이며 기존 14개의 입출력은 그대로다
- [ ] prompt `curate_memory` 본문에 여섯 단계가 있다
- [ ] 쓰기 도구 결과가 후보 키와 처리 기록에 규칙대로 이어진다
- [ ] vg 경로와 `recall.sh` 경로의 첫 줄 확인 기록을 PR에 남긴다(A-29)
- [ ] vault-graph pytest 전체 통과, 독립 커밋

## notes
`mcp_tools.py`는 #29 뒤에, `mcp_memory_tools.py`는 #11 뒤에 수정한다. #42가 이후 wave에서 `mcp_memory_tools.py`를 다시 수정한다.
