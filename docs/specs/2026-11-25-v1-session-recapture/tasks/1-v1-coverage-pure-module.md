# 1. v1 덮음 판단과 교환 수 세기를 M19 순수 모듈로 만든다

## id
1

## title
v1 덮음 판단과 교환 수 세기를 M19 순수 모듈로 만든다

## goal
파일이나 프로세스 없이 "어느 v1 part가 덮이지 않았나"와 "정규화 줄의 교환 수와 첫·끝 id"를 정할 수 있다. Intent의 "v1 part가 v2로 덮였는지 판단한다"의 기반이다.

## units
- I2
- D2
- A1

## files
- src/vault_graph/operation/sessions/v1_coverage.py
- tests/test_session_v1_coverage.py

## blockers
(none)

## checks
- tests/test_session_v1_coverage.py
- tests/test_feature_import_direction.py
- tests/test_functional_module_boundaries.py
- tests/test_module_import_cycles.py
- tests/test_grouped_module_layout.py

## done-when
- [ ] part 머리 DTO, `uncovered_v1_parts(parts)`, `exchange_summary(lines)`가 있고 M01 밖을 가져오지 않는다
- [ ] A1의 경우(교환 메타 범위 포함, `last_turn_at` 무시, 섞인 세션, 다른 Vault·세션 제외, 두 part 이음 불인정, 밀리초 유무, 읽지 못하는 v1 part는 따로 반환)를 테스트가 확인한다
- [ ] `exchange_summary`가 턴 없는 교환을 세지 않는다는 테스트가 있다
- [ ] 배치 규칙 테스트 네 개가 통과한다
