## id

3

## title

MCP에 `cwd`와 `not_a_git_repository`를 열고 안내문, FEATURES, TODO를 고친다

## goal

에이전트가 `cwd`를 넘겨 `explore_project`를 부르면 등록 없이 코드 결과가 나온다. 안내문과 문서도 새 동작을 말한다. 이 task는 Intent의 오류 규칙과 "먼저 부르라는 도구가 설정 없이 동작한다"를 이룬다.

## units

D8, D9, D10, F9, A2, A3, A8, A10, A11, A12

## files

- `src/vault_graph/interface/mcp/mcp_tools.py`
- `src/vault_graph/interface/mcp/mcp_server.py`
- `src/vault_graph/interface/mcp/mcp_prompts.py`
- `src/vault_graph/interface/mcp/mcp_tool_serialization.py`
- `docs/FEATURES.md`
- `docs/TODO.md`
- `tests/test_mcp_explore_project.py`

## blockers

2

## checks

- `tests/test_mcp_explore_project.py`
- `tests/test_project_context_live_repository.py`
- `tests/test_project_context_service.py`
- `tests/test_project_context_scope.py`
- 수동: mcp_server.py 안내문, mcp_prompts.py의 Implementation Context 프롬프트, docs/FEATURES.md의 explore_project 세 곳, docs/TODO.md 결정5 항목을 읽어 "등록 필요" 문장이 없고 cwd와 git 저장소 읽기가 적혀 있는지, 등록 스캐너의 .venv symlink 문제가 후속 항목으로 있는지 본다
- 수동: 변경 파일 목록을 spec §4.5와 대조하고(사실 추출기, vault-builder, source_scanning.py, repository_catalog.py 변경 없음), 원격 branch와 PR이 새로 생기지 않았는지 본다
- 수동: 등록 저장소가 없는 Graph Home으로 MCP 서버를 띄워 이 worktree를 cwd로 explore_project(task="explore_project repository resolution")를 부르고 10초 안에 ProjectContextService 심볼 증거가 나오는지 본 뒤, 저장소의 전체 검증 명령을 실행한다

## done-when

- [ ] `ExploreProjectInput`, `parse_explore_project_input`, MCP 도구 서명에 `cwd: str | None = None`이 있다. 우선순위는 `repository_id`가 `project_path`와 `cwd`보다 앞이고, `project_path`가 `cwd`보다 앞이다. `project_path`와 `repository_id`를 함께 주면 지금처럼 거절하고, 빈 `cwd`는 `invalid_arguments`다.
- [ ] `not_a_git_repository`가 `invalid_parameter`로 나가고, 메시지 "The folder is not inside a git repository."와 안내 "Pass cwd set to a folder inside a git repository."에 등록, bind, `repository_id`, 받은 경로가 없다. `unregistered_project_path`는 더 나오지 않는다.
- [ ] `binding`이 null인 응답이 직렬화된다. 필요하면 `mcp_tool_serialization.py`를 고친다.
- [ ] 안내문은 "registered repositories or the git repository of cwd", 프롬프트는 "for the project in cwd"로 바뀐다. 안내문 문구를 고정한 기존 테스트가 있으면 함께 고친다.
- [ ] `docs/FEATURES.md`의 `explore_project` 세 곳이 새 동작과 `cwd`를 적고 "활성 Vault를 추측하지 않는다"는 남긴다. `docs/TODO.md` 결정5 항목에 체크하고 등록 스캐너 symlink 문제를 후속 항목으로 적는다.
- [ ] 기존 `tests/test_project_context_service.py`, `tests/test_mcp_explore_project.py`, `tests/test_project_context_scope.py` 사례는 고치지 않고 통과하고, 새 사례(`repository_id`+`cwd`, 등록 저장소 안 경로의 `code_index_unavailable`/`scope_required`, A2의 세 경우, A8 우선순위)가 통과한다.
- [ ] 변경 파일이 §4.5 목록 안에 있고 push와 PR이 없다. 이 저장소에서 실제 MCP 호출이 10초 안에 코드 증거를 내고, 전체 검증과 `tests/test_project_context_import_boundaries.py`가 통과한다.
