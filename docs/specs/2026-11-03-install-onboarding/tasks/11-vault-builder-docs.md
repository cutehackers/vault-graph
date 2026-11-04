# 11. vault-builder 문서

## id

11

## title

vault-builder README, README-kr, usage.md를 새 설치 흐름과 `vault-builder` 명령에 맞춰 고친다 (vault-builder)

## goal

vault-builder 첫 문서는 vault-graph README와 같은 설치 명령 한 줄을 안내하고, 나중 작업은 `vault-builder ...` 명령으로 설명한다(spec Intent 첫 항목, §4.10, 발견1, 발견9).

## files

저장소: vault-builder, worktree `$HOME/workspace/vault-builder/.worktrees/feat-jh-install-update` (branch `feat/jh/install-update`). 모든 작업과 검사는 이 worktree에서 한다. main checkout에서는 하지 않는다.

- `README.md`
- `README-kr.md`
- `docs/usage.md` (§1, §16, §17.1~17.3, §17.5 표, §17.6, §19)
- `tests/test_wiki_tools.py` (6825-6870행. usage.md의 `cli.py link` 문구를 확인하는 테스트)

## blockers

- 6, 7, 8, 9, 10 (문서가 설명하는 명령과 문구가 먼저 있어야 한다)

## acceptance

- A-29 (vault-builder 부분)
- A-30

## checks

worktree 루트에서 실행한다.

- `python3 -m unittest tests.test_wiki_tools -v`
- `scripts/release_gate.sh`

## done-when

- [ ] README와 README-kr의 첫 절이 "설치"다. 이 절에 다음이 있다.
  - [ ] 설치 명령 `curl -fsSL https://raw.githubusercontent.com/cutehackers/vault-builder/main/scripts/install.sh | bash` 한 줄
  - [ ] Claude Code 재시작과 `/mcp` 확인 방법
  - [ ] 다음 저장소 연결 명령
  - [ ] vault-graph 저장소 권한이 없을 때 쓰는 `--without-vault-graph`
- [ ] `bootstrap.sh` 안내를 "Vault 폴더만 만들기" 절로 옮겼다.
- [ ] usage.md §1이 같은 설치 명령으로 시작한다.
- [ ] §16, §17의 예시가 `vault-builder ...`다.
- [ ] builder checkout에서 직접 실행하는 방법은 한 줄로 남겼다.
- [ ] §17.1의 역할 설명을 "비어 있지 않은 문자열, 알려진 역할은 §17.2 표"로 고쳤다.
- [ ] §17.2 표가 `roles.py` 내용과 같다.
- [ ] §17.3에 여러 Vault `link`와 이름 없는 `link`를 적었다.
- [ ] §17.5 "연결되지 않은 저장소" 행이 task 6의 recall 안내와 같다.
- [ ] §17.6에 `uninstall --all`, 새 doctor 항목, `setup`이 hook을 기본으로 설치한다는 점을 적었다.
- [ ] §19 명령 요약을 새 명령에 맞췄다.
- [ ] `tests/test_wiki_tools.py`의 문구 기대값을 새 문서에 맞췄고, 테스트가 통과한다.
