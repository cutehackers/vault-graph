## id

4

## title

보완5 M12와 M17 사이 binding 순환을 끊는다

## goal

M12가 binding 읽기 Protocol만 알게 된다. 1차-2가 같은 자리에 `vault-map.json` 읽기 Protocol을 둘 수 있다 (spec 4.2.2, S9).

## files

- `src/vault_graph/project/context/project_context_service.py`
- `src/vault_graph/project/context/project_binding_reader.py` (새 파일, binding 읽기 Protocol)
- `src/vault_graph/operation/integration/project_binding_catalog.py`
- `src/vault_graph/interface/composition/code_index_factory.py`
- `tests/test_feature_import_direction.py`

## blockers

2

## acceptance

A-20 (보완 계획의 완료 증거 포함)

## checks

- `uv run --python 3.12 --all-packages --all-extras pytest -q tests/test_feature_import_direction.py tests/test_project_context_import_boundaries.py tests/test_project_context_read_only_boundary.py`
- `uv run --python 3.12 --all-packages --all-extras pytest -q tests -k "project_bind or explore_project"`
- CI 검증 세 명령 (작업 1의 checks와 같음)

## done-when

- [ ] M12가 M17을 가져오는 곳이 0건이다
- [ ] `ProjectBinding` DTO는 M12에 있고 M17 catalog가 Protocol을 구현한다
- [ ] `explore_project`와 `vg project bind`의 회귀 결과가 같다
- [ ] `tests/test_feature_import_direction.py` 예외 목록에서 발견8-a가 빠졌다
