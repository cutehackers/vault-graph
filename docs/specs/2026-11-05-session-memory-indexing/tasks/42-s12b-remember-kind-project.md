## id
42

## title
S12b `remember(kind="project")`: brief 첫 작성 경로

## goal
에이전트가 프로젝트당 하나의 brief를 기존 쓰기 경로로 만들 수 있다. (Intent 6)

## spec
§4.4.7 brief 페이지, §6 brief 행

## acceptance
A-27(S12 vg 쪽)

## files
- src/vault_graph/operation/memory/memory_requests.py
- src/vault_graph/operation/memory/memory_drafts.py
- src/vault_graph/operation/memory/memory_write_service.py
- src/vault_graph/interface/mcp/mcp_memory_tools.py
- tests/test_remember_kind_project.py (신규)

## blockers
1, 40, 요청S9(외부, E2E는 #43)

## checks
pytest tests/test_remember_kind_project.py tests/test_mcp_memory_tools.py -q

## wave
14

## done-when
- [ ] 경로가 `wiki/projects/<project>.md`이고 `type: project`, `project: <id>`이다
- [ ] `cwd` 프로젝트가 없으면 `rejected`이고, brief가 이미 있으면 `rejected`와 "`update_memory`를 쓰라"이다
- [ ] `wiki/projects/`에 draft를 만드는 호출이 `remember`·`update_memory` 경로뿐이다(검색 확인)
- [ ] vault-graph pytest 전체 통과, 독립 커밋

## notes
Vault가 종류 `project`를 모르면(요청S9 전) Vault가 거부하고 vg는 `rejected`와 Vault 메시지를 전달한다.
