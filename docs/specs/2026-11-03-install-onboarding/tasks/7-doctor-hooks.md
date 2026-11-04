# 7. doctor 확장

## id

7

## title

`doctor [PATH]`에 경로 생략, hook과 vg 검사, `vault-builder` 명령 파일 검사를 더하고, install의 doctor 안내를 `vault-builder doctor`로 바꾼다 (vault-builder)

## goal

명령 하나로 Vault, hook, vg 경로, MCP 항목을 모두 검사하고, 문제마다 고치는 명령을 안내받는다(spec 발견8, §4.7, §4.3 항목 4).

## files

저장소: vault-builder, worktree `$HOME/workspace/vault-builder/.worktrees/feat-jh-install-update` (branch `feat/jh/install-update`). 모든 작업과 검사는 이 worktree에서 한다. main checkout에서는 하지 않는다.

- `tools/vault_migration/uninstalling.py` (`doctor`와 `_doctor_*` 함수)
- `tools/vault_migration/cli.py` (`doctor` parser)
- `tools/vault_migration/builder_command.py` (새 파일. `vault-builder` 명령 파일의 표시 줄을 정의하고, 기록된 checkout 경로를 읽는다)
- `tools/vault_migration/installing.py` (1169행 doctor 안내)
- `builder_tests/test_doctor_hooks.py` (새 파일)
- `builder_tests/test_vault_migration.py` (기존 기대값이 실패할 때만 고친다)

## blockers

- 6 (`cli.py`, `test_vault_migration.py`를 함께 쓴다)

## acceptance

- A-6
- A-15
- A-16 (doctor 부분)
- A-31 (doctor 부분)
- A-33 (doctor 검사 부분)
- A-30

## checks

worktree 루트에서 실행한다.

- `python3 -m unittest builder_tests.test_doctor_hooks builder_tests.test_vault_migration -v`
- `scripts/release_gate.sh`

## done-when

- [ ] 경로를 생략하면 `vault-map.json`의 모든 Vault를 검사한다. 공유 항목은 한 번만 검사한다.
- [ ] spec §4.7의 1~5번 항목을 검사한다.
  - [ ] SessionStart, PreCompact, SessionEnd launcher 항목이 하나씩 있는지 확인한다.
  - [ ] launcher 파일이 있고 builder 원본과 내용이 같은지 확인한다.
  - [ ] `vault-hooks.json`의 `vg`가 절대 경로이고 실행 파일인지 확인한다.
  - [ ] `vg --help`가 10초 안에 exit 0으로 끝나는지 확인한다.
  - [ ] `mcpServers.vault-graph`가 있는지 확인한다. 없으면 문제가 아니라 안내로 출력한다.
- [ ] 문제 줄마다 끝에 고치는 명령이 붙는다. 대부분 `vault-builder setup`이다.
- [ ] doctor는 어떤 파일도 쓰지 않는다.
- [ ] `vault-builder` 명령 파일이 있고 기록된 checkout을 가리키는지 확인한다.
- [ ] vg 없이 설치한 환경(`--without-vault-graph`)에서는 exit 0이다.
- [ ] `installing.py:1169`의 안내가 `vault-builder doctor <경로>`다.
- [ ] 문구 변경 때문에 실패한 테스트의 기대값을 고쳤다.
