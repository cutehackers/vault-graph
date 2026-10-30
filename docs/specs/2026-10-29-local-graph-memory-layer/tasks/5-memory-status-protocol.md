## id

5

## title

보완6 M10이 M15 타입에 의존하지 않게 한다

## goal

기억 조회(M10)가 상태 보고 타입 없이 동작한다. 1차-3 회상이 M10을 쓰기 전에 이 의존이 정리된다 (spec S9).

## files

- `src/vault_graph/context/memory/memory_request_context.py`
- `src/vault_graph/context/memory/timeline_memory.py`
- `src/vault_graph/context/memory/memory_status_view.py` (새 파일, 기억 조회가 쓰는 필드만 담은 Protocol)
- `tests/test_feature_import_direction.py`

## blockers

2

## acceptance

A-20

## checks

- `uv run --python 3.12 --all-packages --all-extras pytest -q tests/test_feature_import_direction.py`
- `uv run --python 3.12 --all-packages --all-extras pytest -q tests -k memory`
- CI 검증 세 명령 (작업 1의 checks와 같음)

## done-when

- [ ] M10이 M15를 가져오는 곳이 0건이다 (`TYPE_CHECKING` 포함)
- [ ] `tests/test_feature_import_direction.py` 예외 목록에서 발견5가 빠졌다
