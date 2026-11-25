## id

2

## title

저장소 선택 순서와 git 저장소 결과를 `ProjectContextService`에 넣는다

## goal

등록 저장소가 0개여도 서비스가 cwd의 git 저장소에서 코드 증거를 내고, 등록 저장소 경로와 Vault 규칙은 그대로 유지한다. Intent의 "등록 0개여도 결과가 나온다"와 "`repository_id`는 지금처럼"을 서비스에서 이룬다.

## units

D1, D2, D6, D7, D11, I2, I3, I4, I5, I6, F1, F2, F3, F4, A1, A4, A7, A9

## files

- `src/vault_graph/project/context/project_context_service.py`
- `src/vault_graph/project/context/project_context_models.py`
- `src/vault_graph/interface/composition/code_index_factory.py`
- `tests/test_project_context_live_repository.py`
- `tests/test_project_context_models.py`

## blockers

1

## checks

- `tests/test_project_context_live_repository.py`
- `tests/test_project_context_models.py`
- `tests/test_live_repository_reader.py`
- `tests/test_project_context_service.py`
- `tests/test_project_context_import_boundaries.py`

## done-when

- [ ] `_resolve_repository`가 `repository_id`, 대상 경로(`project_path`, 없으면 `cwd`)의 등록 저장소, 그 경로의 git 뿌리 순서로 고른다. 인자가 없으면 binding이 있는 유일한 등록 저장소, 그다음 주입된 서버 작업 폴더 순서다.
- [ ] `ProjectContextRequest`에 `cwd` 필드가 생기고, `ProjectContext.binding`이 `ProjectBinding | None`이 된다. `ProjectBinding`의 빈 `vault_ids` 거부는 그대로다.
- [ ] 새 Protocol `ProjectLiveCodeReader`와 `ProjectVaultResolver`를 만든다. 서비스는 reader 구현을 직접 import하지 않고, `open_project_context_service`가 구현체를 넣는다.
- [ ] git 저장소 증거에 `git:<폴더 이름>` 이름표, `code:<symbol_id>`와 `code:line:<상대 경로>:<줄>` evidence id, `git:<HEAD>` revision, `live_symbol_match`/`live_line_match`와 `working_tree` 이유가 붙는다. 경고 `code_live_read`가 늘 나오고 impact와 test 증거는 비어 있다. 경로는 상대 경로뿐이다.
- [ ] Vault가 정해지면 `ProjectBinding(repository_id=<이름표>, ...)`으로 지금과 같은 Vault 근거를 붙인다. 없으면 `binding=None`, Vault 근거 없음, `project_vault_scope_unresolved` 경고이고 활성 Vault로 넘어가지 않는다.
- [ ] git 밖, 없는 경로, git 실행 불가는 `not_a_git_repository; ...` 꼴 `ValueError`를 던진다. 메시지에 등록 안내와 경로가 없고, git 실행 불가는 "git could not be run."으로 구별한다.
- [ ] `repository_id`가 있으면 git 읽기가 불리지 않는다. 등록 저장소 안의 경로는 투영이 없으면 `code_index_unavailable`, binding이 없으면 `scope_required`로 지금과 같다.
- [ ] 호출 전후에 저장소(`.git` 포함)와 Graph Home의 바이트가 같다.
- [ ] 기존 `tests/test_project_context_service.py`를 고치지 않고 통과하고, `tests/test_project_context_import_boundaries.py`도 통과한다.
