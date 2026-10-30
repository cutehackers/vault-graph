## id

7

## title

1차-2 `vault-map.json`을 읽고 프로젝트를 찾으며, `vg setup`과 `vg status`에 반영한다

## goal

프로젝트와 Vault의 연결 정보를 `vault-map.json` 하나에서 읽는다. 회상(1차-3)과 remember(1차-4)가 `cwd`에서 연결 Vault를 찾을 수 있게 된다. spec Intent 2와 결정9를 다룬다.

## files

- `src/vault_graph/operation/integration/vault_map.py` (새 파일)
- `src/vault_graph/project/context/project_binding_reader.py` (작업 4의 Protocol 파일에 VaultMap 읽기 Protocol 추가)
- `src/vault_graph/interface/composition/query_scope_resolution.py` (map을 먼저 보고 프로젝트가 없으면 `project-bindings.json`을 씀. 실제 위치는 구현 시 확인)
- `src/vault_graph/operation/integration/project_binding_catalog.py`
- `src/vault_graph/interface/cli/main.py` (`--vault-map`, `VAULT_GRAPH_VAULT_MAP`, `setup --vault`를 선택 인자로, status 출력)
- `tests/test_vault_map.py`
- `tests/test_cli_vault_map_setup_status.py`
- `tests/fixtures/vault_map/` (구조만 남기고 경로는 가림)

사용자 범위 router(`$HOME/.claude/vault-builder/llm_wiki_router.py`)는 읽기만 한다.

## blockers

2, 4

## acceptance

A-8, A-9, A-20, A-22 (`project-bindings.json` 관련 코드와 `vg vault add`를 지우지 않음)

## checks

- `uv run --python 3.12 --all-packages --all-extras pytest -q tests/test_vault_map.py tests/test_cli_vault_map_setup_status.py tests/test_feature_import_direction.py tests/test_cli_surface_boundary.py`
- CI 검증 세 명령 (작업 1의 checks와 같음)

## done-when

- [ ] 구현 전에 router `find_project`(204행부터)를 읽고 같은 규칙으로 맞췄다
- [ ] version 2를 읽고, 다른 version이나 깨진 JSON이면 경고하고 무시하며, 파일이 없으면 `project-bindings.json`을 쓴다
- [ ] root, remote, 폴더 이름 순서로 찾고, 한 단계에서 둘 이상 맞으면 정하지 않는다
- [ ] git worktree 안의 `cwd`와 심볼릭 링크 `cwd`도 같은 프로젝트를 찾는다
- [ ] 모든 테스트 전후로 fixture 파일의 해시가 같다
- [ ] `vg setup`에서 `--vault`를 생략하면 map의 Vault가 모두 등록되고, `--vault`를 주면 `28f1c96`과 결과가 같다
- [ ] `vg status`가 map 위치, 버전, 등록되지 않은 map Vault를 보여 준다
- [ ] 조회 명령은 Graph Home에 새 파일을 만들지 않는다
