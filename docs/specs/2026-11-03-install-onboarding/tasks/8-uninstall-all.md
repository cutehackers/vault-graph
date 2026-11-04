# 8. uninstall --all

## id

8

## title

`uninstall --all`을 추가한다. 마지막 단계에서 표시 줄이 있는 `vault-builder` 명령 파일과 builder checkout을 지운다 (vault-builder)

## goal

vault-builder가 설치한 것 전부를 명령 하나로 지운다. Vault 내용은 남긴다(spec §4.8, §4.3 항목 3).

## files

저장소: vault-builder, worktree `$HOME/workspace/vault-builder/.worktrees/feat-jh-install-update` (branch `feat/jh/install-update`). 모든 작업과 검사는 이 worktree에서 한다. main checkout에서는 하지 않는다.

- `tools/vault_migration/uninstalling.py`
- `tools/vault_migration/cli.py` (`uninstall` parser)
- `tools/vault_migration/builder_command.py`
- `builder_tests/test_uninstall_all.py` (새 파일)
- `builder_tests/test_vault_migration.py` (기존 기대값이 실패할 때만 고친다)

## blockers

- 7 (`uninstalling.py`, `cli.py`, `builder_command.py`를 함께 쓴다)

## acceptance

- A-23 (vault-builder 부분)
- A-33 (제거 부분)
- A-30

## checks

worktree 루트에서 실행한다.

- `python3 -m unittest builder_tests.test_uninstall_all builder_tests.test_vault_migration -v`
- `scripts/release_gate.sh`

## done-when

- [ ] `vault-map.json`의 Vault마다 지금의 `uninstall`을 실행한다.
- [ ] 공유 파일과 hook은 마지막 Vault를 처리할 때 지워진다.
- [ ] 한 Vault의 uninstall이 실패하면 그 자리에서 exit 1로 멈춘다. 출력에는 실패한 Vault와 오류 원문이 있다.
- [ ] Vault 폴더의 `raw/`와 `wiki/`는 남는다.
- [ ] 표시 줄이 있는 `$HOME/.local/bin/vault-builder`만 지운다.
- [ ] 표시 줄이 없는 같은 이름의 파일은 남긴다.
- [ ] builder checkout을 지운다.
- [ ] `VAULT_BUILDER_HOME`으로 사용자가 고른 checkout은 지우지 않는다.
