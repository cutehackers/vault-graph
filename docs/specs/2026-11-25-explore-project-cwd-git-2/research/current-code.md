# `explore_project` 현재 코드 확인 결과

확인일: 2026-11-25. 코드: 커밋 `fd21e3f`. 파일을 직접 읽어 확인했고 실행하지는 않았다.

## 저장소 고르기

### X1. 등록 저장소가 없으면 `explore_project`는 범위 오류로 실패한다
- source: `src/vault_graph/project/context/project_context_service.py:305-340@fd21e3f`, `src/vault_graph/interface/mcp/mcp_tools.py:1696-1728@fd21e3f`

`_resolve_repository`는 `repository_id`가 있으면 카탈로그에서 찾고, `project_path`가 있으면 그 경로를 품은 등록 저장소를 찾는다. 하나가 아니면 `unregistered_project_path`를 던진다. 둘 다 없으면 binding이 있는 등록 저장소가 정확히 하나일 때만 그것을 고르고, 아니면 `scope_required`를 던진다. MCP 어댑터는 이 오류를 `invalid_parameter`로 바꾸고 "`vg project bind`로 등록하라"거나 "등록 저장소 경로를 넘기라"는 복구 안내를 붙인다. 등록 저장소에 binding이 없으면 `missing project binding`이 나오고 이것도 `scope_required`로 바뀐다.

### X2. `explore_project`는 `cwd`를 받지 않고, 다른 도구는 `cwd`가 없으면 서버 작업 폴더를 쓴다
- source: `src/vault_graph/interface/mcp/mcp_tools.py:183-199@fd21e3f`, `mcp_tools.py:1085-1102@fd21e3f`, `mcp_tools.py:1392-1412@fd21e3f`, `mcp_tools.py:439@fd21e3f`, `mcp_tools.py:615@fd21e3f`, `mcp_tools.py:757@fd21e3f`

`ExploreProjectInput`과 MCP 도구 서명은 `task`, `project_path`, `repository_id`, `max_tokens`, `depth`, `limit`만 받는다. `parse_explore_project_input`은 `project_path`와 `repository_id`를 함께 주면 거절한다. 검색, 회상, 후보 목록 도구는 `cwd`가 None이면 `Path.cwd()`를 쓴다. 서버 안내문은 "Most tools take an optional cwd"라고 적는다.

### X3. `ProjectBinding`은 빈 Vault 목록을 거부하고, `ProjectContext`는 binding을 반드시 가진다
- source: `src/vault_graph/project/context/project_binding.py:23-26@fd21e3f`, `src/vault_graph/project/context/project_context_models.py:173-193@fd21e3f`, `src/vault_graph/interface/mcp/mcp_tool_serialization.py:165-178@fd21e3f`

`ProjectBinding.__post_init__`은 `vault_ids`가 비면 `ValueError`를 던진다. `ProjectContext.binding`의 타입은 `ProjectBinding`이고, `binding.repository_id`가 `repository_id`와 다르면 생성이 실패한다. MCP payload는 `dataclasses.asdict(context)`라서 `binding` 객체가 그대로 응답에 들어간다.

## 코드 증거

### X4. 코드 증거는 활성 코드 투영의 `CodeQueryService`에서만 나온다
- source: `src/vault_graph/interface/composition/code_index_factory.py:93-155@fd21e3f`, `src/vault_graph/project/context/project_context_service.py:258-276@fd21e3f`

`open_project_context_service`는 활성 SQLite 코드 세대를 열어 `CodeQueryService`를 만들고, 세대가 없으면 None을 넘긴다. 서비스는 None이면 코드 증거 없이 `code_index_unavailable` 경고와 `vg code index` 안내를 낸다. 영향(impact)과 관련 테스트도 같은 서비스의 `get_impact`에서만 나온다.

### X5. 폴더의 Vault는 `vault-map.json`, 그다음 project binding으로만 정하고 활성 Vault로 넘어가지 않는다
- source: `src/vault_graph/interface/composition/query_scope_resolution.py:49-81@fd21e3f`, `docs/FEATURES.md:421-424@fd21e3f`

`resolve_project_vaults(cwd, vault_map=, vault_catalog=, bindings=, repository_roots=)`는 map 프로젝트가 있으면 그 등록 Vault를, 없으면 등록 저장소 binding의 Vault를 돌려준다. 둘 다 없으면 빈 `vault_ids`와 이유 문장을 돌려준다. FEATURES는 `explore_project`가 활성 Vault를 추측하지 않는다고 적는다.

### X6. git 실행 도우미는 실패하면 None을 돌려주고, 주 worktree 뿌리를 찾는 함수가 있다
- source: `src/vault_graph/operation/scope/git_command.py:13-28@fd21e3f`, `src/vault_graph/operation/integration/vault_map.py:321-330@fd21e3f`

`run_git(folder, *args, timeout_s=None) -> str | None`은 git이 없거나, 실패하거나, 시간을 넘기면 None이다. `main_worktree_root(start)`는 `--git-common-dir`로 주 worktree 뿌리를 찾는다. linked worktree 안에서는 `--show-toplevel`(그 worktree 뿌리)과 결과가 다르다.

### X7. Python·Dart 파서는 파일 하나를 메모리에서 파싱하고, 스캐너에 언어·테스트 판정 규칙이 있다
- source: `src/vault_graph/project/code/python_parser.py:37-48@fd21e3f`, `src/vault_graph/project/code/dart_parser.py:37-43@fd21e3f`, `src/vault_graph/project/code/code_models.py:156-170@fd21e3f`, `code_models.py:196-211@fd21e3f`, `src/vault_graph/project/code/source_scanning.py:171-209@fd21e3f`

`PythonCodeParserAdapter().parse(CodeFileInput)`와 `DartCodeParserAdapter().parse(...)`는 `CodeParseResult`를 돌려주고 디스크에 쓰지 않는다. 결과의 `CodeSymbolRecord`는 `symbol_id`, `name`, `qualified_name`, `signature`, `start_line`, `end_line`을 가진다. 스캐너의 `_language_for_path`는 `.py`, `.dart`만 언어로 보고, `_is_test_path`가 테스트 파일을 가린다. 등록 경로의 revision은 `git:<HEAD>` 꼴이고, `head-and-working-tree` 정책에서는 `git status`를 실행한다.

### X8. 응답 직렬화는 `vg-source://` URI와 안전한 상대 경로만 남긴다
- source: `src/vault_graph/interface/mcp/mcp_tool_serialization.py:1109-1160@fd21e3f`, `src/vault_graph/project/code/source_evidence_reader.py:89-90@fd21e3f`

코드 증거의 `source_uri`는 `vg-source://<quote(repository_id)>/<relative_path>#L<a>-L<b>`와 정확히 맞을 때만 남고, 아니면 None이 된다. 안전하지 않은 `relative_path`도 None이 된다. 이 URI를 여는 MCP resource 처리기는 없다(`interface/`에서 `vg-source`를 찾으면 직렬화 검사 한 곳뿐이다).

## 안내문, 문서, 테스트

### X9. MCP 안내문, 프롬프트, FEATURES는 등록 저장소를 전제로 적는다
- source: `src/vault_graph/interface/mcp/mcp_server.py:85-86@fd21e3f`, `src/vault_graph/interface/mcp/mcp_prompts.py:147@fd21e3f`, `docs/FEATURES.md:283@fd21e3f`, `docs/FEATURES.md:394@fd21e3f`, `docs/FEATURES.md:421-422@fd21e3f`, `docs/TODO.md:139-147@fd21e3f`

서버 안내문은 "configured Vaults and registered repositories"와 "For coding tasks, call explore_project first"를, 프롬프트는 "for the registered project"를 적는다. FEATURES는 "Needs a registered, bound repository"라고 적고 도구 서명에 `cwd`가 없다. TODO의 결정5 항목은 열린 체크박스다.

### X10. 기존 테스트는 경로 노출, 어댑터 읽기 전용, import 경계를 본다
- source: `tests/test_mcp_explore_project.py:112-130@fd21e3f`, `tests/test_mcp_explore_project.py:175-187@fd21e3f`, `tests/test_mcp_explore_project_read_only_boundary.py:32-52@fd21e3f`, `tests/test_project_context_service.py:213@fd21e3f`, `tests/test_project_context_import_boundaries.py:8-10@fd21e3f`

잘못된 입력 오류 메시지에 `/private/repository` 경로가 없어야 한다. binding 없음은 `scope_required`로 바뀌어야 한다. 읽기 전용 테스트는 가짜 서비스를 쓰는 어댑터만 보고 실제 git 읽기는 보지 않는다. 서비스 테스트는 인자 없는 요청이 binding이 있는 유일한 등록 저장소를 고르는지 본다. `project/context/` 모듈은 `vault_graph.storage`를 import하면 안 된다.
