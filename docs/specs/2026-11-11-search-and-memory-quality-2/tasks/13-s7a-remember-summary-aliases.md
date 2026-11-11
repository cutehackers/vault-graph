# 13. S7a `remember`/`update_memory`의 summary·aliases

## id
13

## title
`remember`와 `update_memory`가 summary와 aliases를 받는다

## goal
쓰는 시점에 summary와 aliases를 넣어 Vault 페이지 frontmatter에 실린다. 의도3(기억 품질)을 담당한다. 값은 호출하는 에이전트가 쓰고 vault-graph는 만들지 않는다.

## files
(경로는 코드에서 확인함: `RememberInput`/`UpdateMemoryInput`은 mcp_memory_tools.py, 요청과 draft는 operation/memory)
- src/vault_graph/interface/mcp/mcp_memory_tools.py
- src/vault_graph/operation/memory/memory_requests.py
- src/vault_graph/operation/memory/memory_drafts.py
- src/vault_graph/operation/memory/memory_write_service.py
- tests/test_mcp_memory_tools.py
- tests/test_memory_write_service.py

## blockers
10

## acceptance
A-9

## checks
- `uv run --python 3.12 pytest -q tests/test_mcp_memory_tools.py tests/test_mcp_memory_tools_module.py tests/test_memory_write_service.py tests/test_memory_write_boundary.py`
- `uv run --python 3.12 ruff check src tests`
- `uv run --python 3.12 mypy src tests`

## done-when
- [ ] 시작할 때 Vault 검증(publish-draft)이 summary, aliases를 받는지 확인해 결과를 남겼다.
- [ ] 두 필드가 publish-draft와 review propose 경로로 frontmatter에 쓰인다. Vault 파일은 Vault 도구만 쓴다.
- [ ] `basis=stated`이고 summary가 없으면 결과에 경고를 넣고 거절하지는 않는다.
- [ ] Vault가 필드를 거절하면 그 필드 없이 다시 시도하지 않고 거절 이유를 그대로 돌려준다.
