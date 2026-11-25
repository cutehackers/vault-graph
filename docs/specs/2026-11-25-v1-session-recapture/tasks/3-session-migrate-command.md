# 3. `vg session migrate` 명령과 adapter를 만든다

## id
3

## title
`vg session migrate` 명령과 adapter를 만든다

## goal
사용자가 `vg session migrate [--dry-run]`로 덮이지 않은 v1 part가 있는 세션만 골라 v2로 다시 수집하고, 결과를 검증된 출력과 종료 코드로 받을 수 있다. Intent의 "v1을 v2로 모두 옮기고 교환 수·Vault 쓰기 규칙을 지킨다"를 구현한다.

## units
- I1
- I3
- I4
- D3
- D5
- D6
- D7
- D8
- D9
- D10
- F1
- F2
- F3
- F4
- F5
- F6
- F7
- F8
- F9
- F10
- F11
- A2
- A3
- A4
- A5
- A6
- A7
- A8
- A9

## files
- src/vault_graph/interface/composition/adapters/session_migration.py
- src/vault_graph/interface/cli/session_commands.py
- tests/test_cli_session_migrate.py

## blockers
1, 2

## checks
- tests/test_cli_session_migrate.py
- tests/test_session_v1_coverage.py
- tests/test_feature_import_direction.py
- tests/test_functional_module_boundaries.py
- tests/test_module_import_cycles.py
- tests/test_grouped_module_layout.py
- tests/test_cli_session_recapture.py
- tests/test_cli_session_export.py

## done-when
- [ ] `vg session migrate`가 `--vault`(여러 번), `--dry-run`, `--graph-home`, `--vault-map`을 받고 에이전트는 claude-code 하나다
- [ ] part frontmatter를 읽어 대상 세션을 고르고, 원본 찾기, 1시간 규칙, 끝난 세션 정규화(임시 폴더, 종료 뒤 삭제), 중복 막기, cwd 대체, 실행기 호출, 결과 확인 흐름이 동작한다
- [ ] 출력은 세션마다 한 줄과 Vault마다 요약 한 줄이고, 실패가 있으면 종료 코드 1이다
- [ ] A2~A8 증거(가짜 실행기와 임시 Vault)가 `tests/test_cli_session_migrate.py`에서 통과한다
- [ ] A9: 배치 규칙 테스트와 기존 export·recapture 테스트가 고치지 않고 통과한다
- [ ] vg는 Vault 안에 쓰지 않고, 사실 대기열과 사실 작업자는 건드리지 않는다
