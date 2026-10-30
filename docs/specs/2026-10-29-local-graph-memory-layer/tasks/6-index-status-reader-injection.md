## id

6

## title

보완3 색인 서비스가 상태 조회기를 직접 만들지 않게 한다

## goal

M03 색인 서비스가 M15 구현을 생성하지 않는다. 공개 `IndexService.status`는 그대로 남는다 (VG-MOD DEP-02).

## files

- `src/vault_graph/indexing/index_service.py`
- `src/vault_graph/interface/composition/local_index_service_factory.py`
- `tests/test_feature_import_direction.py`

## blockers

2

## acceptance

A-20

## checks

- `uv run --python 3.12 --all-packages --all-extras pytest -q tests/test_feature_import_direction.py`
- `uv run --python 3.12 --all-packages --all-extras pytest -q tests -k status`
- CI 검증 세 명령 (작업 1의 checks와 같음)

## done-when

- [ ] `vg status`와 MCP 상태 응답이 같다
- [ ] `IndexService.status` 시그니처가 같다
- [ ] `tests/test_feature_import_direction.py` 예외 목록에서 발견5-b가 빠졌다
