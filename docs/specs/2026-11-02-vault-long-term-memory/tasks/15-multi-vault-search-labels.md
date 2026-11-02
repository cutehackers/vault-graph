## id

15

## title

[vault-graph] G3b. V2. 범위 없는 검색이 프로젝트 연결 Vault 전부를 찾고, 결과에 `vault_name`과 `vault_role`을 붙인다

## goal

한 번의 검색이 프로젝트의 모든 Vault를 관련도 순 한 목록으로 돌려주고, 결과마다 출처 Vault 이름과 종류가 보인다. spec Intent 2, 결정13·15·S2·S9를 다룬다.

## files

저장소: vault-graph (이 worktree, 브랜치 `feat/jh/local-graph`)

- `src/vault_graph/interface/composition/vault_labels.py` (새 파일)
- `src/vault_graph/interface/composition/query_scope_resolution.py` (`default_query_vault_ids`)
- `src/vault_graph/interface/mcp/mcp_tools.py`, `mcp_tool_serialization.py` (`search_vault`, `ask_vault`, `build_context_pack`의 `cwd`와 결과 필드)
- `src/vault_graph/interface/cli/main.py` (`search`, `ask`, `context`)
- `src/vault_graph/interface/http/http_server.py`, `http_serialization.py`
- `tests/test_query_scope_resolution.py`
- `tests/test_vault_labels.py` (새 파일)
- `tests/test_mcp_tools.py`
- `tests/test_http_server.py`
- `tests/test_cli_search_vault_labels.py` (새 파일)

## blockers

12, 14

## acceptance

A-5 (단위 수준. 실제 Vault 증명은 작업 21), A-19, A-22

## checks

vault-graph worktree에서 실행한다.

- `uv run --python 3.12 --all-packages --all-extras pytest -q tests/test_query_scope_resolution.py tests/test_vault_labels.py tests/test_mcp_tools.py tests/test_http_server.py tests/test_cli_search_vault_labels.py tests/test_feature_import_direction.py`
- `uv run --python 3.12 --all-packages --all-extras pytest -q`

## done-when

- [x] 범위는 요청 `scope`, `cwd` 프로젝트의 등록된 연결 Vault 전부, 활성 Vault 순으로 정한다
- [x] MCP 세 도구는 선택 입력 `cwd`를 받고 없으면 서버 작업 디렉터리를 쓴다. CLI는 프로세스 작업 디렉터리, HTTP는 선택 필드 `cwd`를 쓴다
- [x] 프로젝트 Vault가 하나도 등록되지 않았으면 활성 Vault로 돌아가지 않고 빈 결과와 "`vg setup` 필요" 경고를 돌려준다
- [x] 일부만 색인됐으면 빠진 Vault 이름을 경고에 적는다
- [x] map에 없는 Vault는 `vault_name`, `vault_role`이 null이다
- [x] CLI 텍스트 결과 줄 앞에 `[<vault_name>·<vault_role>]`이 붙는다
- [x] `RetrievalResult`는 바뀌지 않았고, 코드가 role 값으로 분기하지 않는다
- [x] 명시한 `scope`의 결과는 두 필드 추가 외에 변경 전과 같다
- [x] 실제 Claude Code 세션에서 MCP 서버 작업 디렉터리를 확인하고 결과를 커밋 메시지에 적었다(위험10)

멈춤: 여러 Vault 결합에 `fuse_candidates`의 순서 변경이 필요하면 보고한다.

기록 (2026-11-02): pytest 1701 passed, 1 skipped. 위험10 확인: 이 Claude Code 세션이 띄운 stdio MCP 서버(codegraph, llm-wiki router)의 작업 디렉터리는 세션 프로젝트 폴더(이 worktree)였다. 데스크톱 앱 수준 MCP(codeflow)는 `/`에서 돈다. 그래서 `cwd` 없는 검색은 보통 프로젝트 Vault를 찾지만, 에이전트는 `cwd`를 넘기는 것이 안전하다. 남은 차이: 등록 Vault가 없을 때 `ask`·`context`는 빈 결과 대신 `vg setup` 오류를 낸다(요청 타입이 Vault 1개 이상을 요구). 이름표는 검색 결과에만 붙고(V2 "검색 결과 JSON"), HTTP `cwd`는 `/search`에만 있다.
