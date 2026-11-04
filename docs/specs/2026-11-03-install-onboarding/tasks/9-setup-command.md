# 9. vault-builder setup

## id

9

## title

`vault-builder setup` 하위 명령(`onboarding.py`)을 만든다. 6단계 실행, 대화 모드, 비대화 모드, `--without-vault-graph`를 포함한다 (vault-builder)

## goal

한 번의 실행으로 vg 설치, hook을 포함한 Vault 설치, 저장소 연결, MCP 등록, 색인, 검사를 끝낸다(spec Intent "명령 1개 + 재시작 1번", 역할 확장, §4.4).

## files

저장소: vault-builder, worktree `$HOME/workspace/vault-builder/.worktrees/feat-jh-install-update` (branch `feat/jh/install-update`). 모든 작업과 검사는 이 worktree에서 한다. main checkout에서는 하지 않는다.

- `tools/vault_migration/onboarding.py` (새 파일)
- `tools/vault_migration/cli.py` (`setup` parser. `--role` 도움말에 역할 목록을 보여 준다)
- `builder_tests/test_onboarding_setup.py` (새 파일. uv, vg, `git ls-remote`, Claude Code 프로세스 확인은 stub으로 바꾼다)

## blockers

- 5 (역할 목록이 필요하다)
- 6 (여러 Vault `link`가 필요하다)
- 7 (경로 없는 doctor가 필요하고, `cli.py`를 함께 쓴다)
- 8 (`cli.py`를 함께 쓴다)

## acceptance

- A-2, A-3, A-4, A-5
- A-11, A-12
- A-13 (대화 모드 질문과 도움말 부분)
- A-14
- A-18 (setup 부분)
- A-19, A-20, A-21, A-22
- A-25, A-26
- A-30, A-31, A-32

## checks

worktree 루트에서 실행한다.

- `python3 -m unittest builder_tests.test_onboarding_setup -v`
- `scripts/release_gate.sh`

## done-when

- [ ] 서명이 spec §4.4와 같다.
- [ ] `--vault`와 `--role`은 여러 번 줄 수 있다.
- [ ] `--role`이 없으면 새 Vault는 `personal`이 되고, 이미 등록된 Vault는 지금 역할을 유지한다.
- [ ] 1단계는 파일을 쓰지 않는다. 다음 중 하나라도 실패하면 아무것도 쓰지 않고 멈춘다.
  - [ ] 옵션 해석
  - [ ] Vault마다 precheck
  - [ ] `git ls-remote`
  - [ ] Claude Code 실행 확인
- [ ] vg(`uv tool install --force --python 3.12 git+<VAULT_GRAPH_REPO>`)를 Vault install보다 먼저 설치한다.
- [ ] install을 `--with-hooks`로 실행하고 `VAULT_GRAPH_BIN=<uv tool dir --bin의 vg>`를 넘긴다.
- [ ] 저장소마다 `link --repo <PATH> <공유 Vault...> <project Vault>`를 한 번 실행한다.
- [ ] 2단계의 vg로 `vg setup --agent claude --mcp`를 실행한다. 그다음 경로 없는 doctor를 실행한다.
- [ ] 기본 쓰기 Vault가 정해지지 않으면 다음처럼 처리한다.
  - [ ] 대화 모드에서는 묻는다.
  - [ ] 비대화 모드에서는 `--default-write`를 쓰거나 `vault-builder set-default-write` 안내를 출력한다.
- [ ] 대화 모드 질문 1~5와 기본값이 spec §4.4와 같다.
- [ ] 비대화 모드의 기본 경로는 `$HOME/vault`와 `$HOME/vaults/<저장소 폴더 이름>`이다.
- [ ] spec §6 표에서 setup이 맡는 줄의 exit 코드(1, 2, 3)와 출력이 같다.
- [ ] Claude Code가 실행 중이면 비대화 모드는 exit 3으로 끝나고 `$HOME/.claude.json`이 바뀌지 않는다.
- [ ] `--without-vault-graph`는 2단계와 5단계를 건너뛰고 hook은 설치한다.
- [ ] `--without-vault-graph` 뒤에 같은 명령을 이 옵션 없이 다시 실행하면 vg 경로가 기록된다.
- [ ] 같은 명령을 다시 실행하면 `vault-map.json`, `$HOME/.claude.json`, `settings.json`의 bytes가 바뀌지 않는다.
- [ ] 두 번째 Vault의 install이 실패한 뒤 원인을 없애고 같은 명령을 다시 실행하면 설치가 끝난다(A-20).
- [ ] `roles.py`에 한 줄을 더하면 대화 모드 역할 질문과 `--role` 도움말에 그 역할이 보인다는 테스트가 있다.
- [ ] `install`의 `--with-hooks` 기본값(꺼짐)은 바뀌지 않는다.
- [ ] 마지막 출력에 다음이 있다.
  - [ ] Claude Code 재시작 안내
  - [ ] `/mcp`에서 확인하는 방법
  - [ ] `vault-builder link --repo <경로>`
