# 2. session-default

## id
2

## title
세션 단위 결과가 CLI와 MCP에서 인자 없이 기본으로 동작한다

## goal
`vg search --mode evidence`와 `search_vault`가 접힌 결과를 기본으로 준다. 결과 단위를 기본 동작으로 하자는 결정을 지킨다.

## units
D6, A4

## files
- tests/test_cli_search.py
- tests/test_mcp_tools.py
- (필요하면 추가 가능) src/vault_graph/interface/cli/main.py
- (필요하면 추가 가능) src/vault_graph/interface/mcp/mcp_tools.py

## blockers
1

## checks
- tests/test_cli_search.py
- tests/test_mcp_tools.py

## done-when
- [ ] 인자 없이 `vg search --mode evidence`가 접힌 결과를 준다는 시험이 있다
- [ ] 인자 없이 `search_vault`가 접힌 결과를 준다는 시험이 있다
- [ ] 모드나 플래그 없이 1번 task 결과가 그대로 나온다
- [ ] 기본 동작이 이미 맞으면 시험만 쓰고, src 수정이 필요할 때만 위 CLI·MCP src 파일을 고친다
- [ ] D24 관문(4번 task)을 못 넘으면 이 기본 동작을 들이지 않는다는 조건을 보고서에 연결한다
