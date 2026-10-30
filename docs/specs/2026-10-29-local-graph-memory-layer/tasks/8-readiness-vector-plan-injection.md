## id

8

## title

보완2 준비 상태 판정이 벡터 색인기를 직접 만들지 않게 한다

## goal

M14 준비 상태 판정이 M03 구현을 가져오지 않는다. "벡터 색인이 최신인가" 판정은 composition이 주입한다 (VG-MOD DEP-02).

## files

- `src/vault_graph/operation/readiness/search_readiness_service.py`
- `src/vault_graph/interface/composition/read_only_service_factory.py`
- `src/vault_graph/interface/cli/main.py` (`ReadOnlySearchReadiness` 생성 지점)
- `tests/test_feature_import_direction.py`

## blockers

2

## acceptance

A-20

## checks

- `uv run --python 3.12 --all-packages --all-extras pytest -q tests/test_feature_import_direction.py`
- `uv run --python 3.12 --all-packages --all-extras pytest -q tests -k readiness`
- CI 검증 세 명령 (작업 1의 checks와 같음)

## done-when

- [ ] 준비 상태 결과와 경고의 회귀 결과가 같다
- [ ] `tests/test_feature_import_direction.py` 예외 목록에서 발견6이 빠졌다
