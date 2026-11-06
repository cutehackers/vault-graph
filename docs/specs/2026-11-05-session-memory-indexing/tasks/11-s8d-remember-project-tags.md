## id
11

## title
S8d `remember`의 계층 표시: `project_id`, draft의 `project`와 `tags`

## goal
vg로 저장한 기억이 프로젝트 요약과 L3에 나타난다. (Intent 6)

## spec
§4.4.3

## acceptance
A-21

## files
- src/vault_graph/operation/memory/memory_requests.py
- src/vault_graph/operation/memory/memory_drafts.py
- src/vault_graph/interface/mcp/mcp_memory_tools.py
- tests/test_remember_project_tags.py (신규)

## blockers
1, 6

## checks
pytest tests/test_remember_project_tags.py tests/test_memory_drafts.py tests/test_mcp_memory_tools.py -q

## wave
3

## done-when
- [ ] `cwd`가 프로젝트면 draft에 `project: <id>`가 있고, `correction`·`rule`이면 `tags`에도 같은 값이 있다
- [ ] 프로젝트 밖이면 `project`가 없다. `update_memory`는 `project`를 바꾸지 않는다
- [ ] vault-graph pytest 전체 통과, 독립 커밋

## notes
요청S4와 무관하다.
