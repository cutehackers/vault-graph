## id

2

## title

보완1 기능 영역 사이 가져오기 방향 테스트를 추가한다

## goal

새 모듈(vault_map, recall, remember)이 기능 간 방향 규칙을 어기면 바로 실패하도록 검사를 먼저 세운다. 1차-2 이후 작업이 구조를 나쁘게 만들지 않게 하는 spec S9의 선행 조건이다.

## files

- `tests/test_feature_import_direction.py` (새 파일, 이하 `T`)

결정 (2026-10-30 승인): 제안한 파일 이름을 그대로 쓴다. 영역 표에 미리 넣을 새 모듈 경로는 `src/vault_graph/operation/integration/vault_map.py`, `src/vault_graph/operation/integration/remember_service.py`, `src/vault_graph/interface/composition/adapters/vault_publish_cli.py`, `src/vault_graph/context/pack/recall.py`, `src/vault_graph/storage/local/usage_log.py`다.

## blockers

1

## acceptance

A-6, A-20

## checks

- `uv run --python 3.12 --all-packages --all-extras pytest -q tests/test_feature_import_direction.py tests/test_functional_module_boundaries.py`
- CI 검증 세 명령 (작업 1의 checks와 같음)

## done-when

- [ ] 영역 매핑, 허용 방향, 계약 모듈 목록이 테스트 안의 표로 있다
- [ ] 현재 위반(보완 계획 발견5~8)이 파일·대상 단위 예외 목록으로 고정되어 있고, 예외가 늘어나면 실패한다
- [ ] 지연 가져오기와 `TYPE_CHECKING` 가져오기도 검사한다
- [ ] 아직 없는 새 모듈 경로 다섯 개가 영역 표에 미리 들어 있다
- [ ] 임의 위반을 넣으면 실패하는 것을 한 번 확인했다 (그 위반은 커밋하지 않음)
