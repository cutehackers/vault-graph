# 8. mcp-date-args

## id
8

## title
MCP 검색 도구 셋에 날짜 인자와 설명을 더한다

## goal
에이전트가 "지난주"를 날짜로 계산해 넘기면 그 기간 세션만 찾는다. Intent 2를 맡는다.

## units
D12, F5, A8, A9

## files
- src/vault_graph/interface/mcp/mcp_tools.py
- tests/test_mcp_tools.py

## blockers
5, 7

## checks
- tests/test_mcp_tools.py

## done-when
- [ ] `search_vault`, `ask_vault`, `build_context_pack`이 `since`·`until`을 검색 요청에 넘긴다
- [ ] 세 도구 설명에 오늘 날짜로 계산해 넘기고 질의에서는 뺀다는 문장과 예시 하나가 있다
- [ ] 잘못된 입력은 MCP 입력 오류가 된다
- [ ] MCP 경로는 날짜 해석기를 부르지 않는다
