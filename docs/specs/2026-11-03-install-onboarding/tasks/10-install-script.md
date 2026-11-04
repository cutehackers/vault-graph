# 10. 설치 명령 scripts/install.sh

## id

10

## title

설치 명령 `scripts/install.sh`를 만든다. 도구 확인, uv 처리, builder checkout, `vault-builder` 명령 파일 관리, `--uninstall`을 포함한다 (vault-builder)

## goal

README의 셸 명령 한 줄로 설치를 끝내고, `--uninstall` 한 줄로 전부 지운다(spec Intent "명령 1개", §4.3, §4.8, 결정2, 결정4, 결정10).

## files

저장소: vault-builder, worktree `$HOME/workspace/vault-builder/.worktrees/feat-jh-install-update` (branch `feat/jh/install-update`). 모든 작업과 검사는 이 worktree에서 한다. main checkout에서는 하지 않는다.

- `scripts/install.sh` (새 파일. README URL `https://raw.githubusercontent.com/cutehackers/vault-builder/main/scripts/install.sh`가 이 파일을 가리킨다)
- `builder_tests/test_install_script.py` (새 파일. 임시 `HOME`과 stub 도구를 쓴다)

## blockers

- 8 (`uninstall --all`이 필요하다)
- 9 (`setup`이 필요하다)
- vault-graph task 2 (`--uninstall`이 `vg mcp unregister`를 호출한다)

## acceptance

- A-1
- A-7
- A-18 (전체 흐름)
- A-19 (셸 경로)
- A-23
- A-27
- A-33
- A-30

## checks

worktree 루트에서 실행한다.

- `bash -n scripts/install.sh`
- `python3 -m unittest builder_tests.test_install_script -v`
- `scripts/release_gate.sh`

## done-when

- [ ] `git`, `curl`, Python 3.10 이상을 확인한다.
- [ ] `choose_python` 규칙이 `bootstrap.sh`와 같다.
- [ ] 필요한 도구가 하나라도 없으면 아무것도 쓰지 않고 exit 1로 멈춘다.
- [ ] uv가 없을 때 결정4대로 동작한다.
  - [ ] 대화 모드에서는 설치할지 묻는다.
  - [ ] 비대화 모드에서는 설치 명령 한 줄을 출력하고 exit 1로 멈춘다.
  - [ ] `--install-uv`를 주면 묻지 않고 설치한다.
- [ ] 질문은 `/dev/tty`에서 읽는다. `/dev/tty`가 없으면 비대화 모드로 실행한다.
- [ ] 환경 변수 `VAULT_BUILDER_REPO`, `VAULT_BUILDER_REF`, `VAULT_BUILDER_HOME`을 지원한다.
- [ ] 기본 checkout 위치는 `$HOME/.local/share/vault-builder`다.
- [ ] checkout 위치에 git checkout이 아닌 폴더가 있으면 exit 1로 멈춘다.
- [ ] `git pull --ff-only`가 실패하면 경고 한 줄을 출력하고 지금 checkout으로 계속한다.
- [ ] `$HOME/.local/bin/vault-builder`에 표시 줄과 checkout 경로를 적는다. 이 형식은 task 7의 `builder_command.py`가 정한 형식과 같다.
- [ ] 다시 실행할 때 다음처럼 동작한다.
  - [ ] 내용이 같으면 그대로 둔다.
  - [ ] 표시 줄이 있는 이전 내용이면 교체한다.
  - [ ] 표시 줄이 없는 파일이 있으면 그 파일을 바꾸지 않고 exit 1로 멈춘다.
- [ ] `$HOME/.local/bin`이 `PATH`에 없으면 마지막에 `export PATH=...` 한 줄을 안내한다.
- [ ] `--uninstall`은 다음 순서로 실행한다.
  - [ ] Claude Code가 종료됐는지 확인한다.
  - [ ] `vault-builder uninstall --all`을 실행한다. 실패하면 멈추고 vg 단계는 실행하지 않는다.
  - [ ] `vg mcp unregister --agent claude`를 실행한다.
  - [ ] `uv tool uninstall vault-graph`를 실행한다.
  - [ ] 명령 파일과 checkout이 남아 있으면 지운다.
  - [ ] 남긴 Vault 경로와 `$HOME/.vault-graph` 경로를 출력한다.
- [ ] 통합 테스트가 있다. 빈 `HOME`에서 `--repo <앱> --yes`를 `/dev/tty` 없이 실행하면 A-2~A-6이 성립한다.
