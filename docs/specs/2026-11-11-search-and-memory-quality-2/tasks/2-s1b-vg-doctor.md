# 2. S1b `vg doctor` 명령

## id
2

## title
`vg doctor` 명령을 추가한다

## goal
사용자가 `vg doctor` 한 번으로 문제와 고치는 명령을 본다. 의도4를 담당한다. 첫 PR 범위에 든다.

## files
- src/vault_graph/operation/diagnostics/doctor_service.py (신규)
- src/vault_graph/interface/cli/doctor_commands.py (신규)
- src/vault_graph/interface/cli/main.py
- tests/test_cli_doctor.py (신규)

## blockers
없음

## acceptance
A-2

## checks
- `uv run --python 3.12 pytest -q tests/test_cli_doctor.py tests/test_cli_setup_hook_status.py`
- `uv run --python 3.12 ruff check src tests`
- `uv run --python 3.12 mypy src tests`

## done-when
- [ ] 실패 기록, 색인 없음, 모델 파일 없음, MCP 미등록을 각각 감지하고 고치는 명령 한 줄을 낸다.
- [ ] 실행 전후 Vault와 Graph Home 파일 해시가 같다는 테스트가 있다.
