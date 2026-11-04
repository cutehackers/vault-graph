# 5. 역할 목록 roles.py

## id

5

## title

역할 목록 `roles.py`를 만들고, `linking._PROJECT_ROLE`과 `list` 출력이 이 목록을 쓰게 한다 (vault-builder)

## goal

알려진 역할을 파일 한 곳에서 관리한다. 그래서 새 역할을 더할 때 한 줄만 고치면 된다(spec Intent "새 역할이 생겨도 사용법이 바뀌지 않는다", §4.6, 결정8).

## files

저장소: vault-builder, worktree `$HOME/workspace/vault-builder/.worktrees/feat-jh-install-update` (branch `feat/jh/install-update`). 모든 작업과 검사는 이 worktree에서 한다. main checkout(`$HOME/workspace/vault-builder`)에서는 하지 않는다.

- `tools/vault_migration/roles.py` (새 파일)
- `tools/vault_migration/linking.py` (`_PROJECT_ROLE`, `list_links` 출력)
- `builder_tests/test_roles.py` (새 파일)

## blockers

없음

## acceptance

- A-13 (역할 표 부분)
- A-12 (표에 없는 역할을 받는 부분)
- A-30

## checks

worktree 루트에서 실행한다.

- `python3 -m unittest builder_tests.test_roles builder_tests.test_map_settings -v`
- `scripts/release_gate.sh`

## done-when

- [ ] 표의 각 항목은 이름, 한 줄 설명, `per_repo` 여부를 가진다.
- [ ] 처음 내용은 `personal`(공유), `team`(공유), `project`(per_repo)다.
- [ ] 공유 Vault를 판정하는 함수가 있다. 이 함수는 표에 없는 역할도 공유로 본다(결정7).
- [ ] `_PROJECT_ROLE`이 표의 `project` 항목을 가리킨다.
- [ ] `tools/wiki/lib/session_capture.py`는 바꾸지 않았다.
- [ ] 역할 검사는 지금처럼 "비어 있지 않은 문자열"이다.
