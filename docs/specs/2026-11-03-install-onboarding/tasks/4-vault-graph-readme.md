# 4. vault-graph README

## id

4

## title

vault-graph README의 Install과 Quick Start를 고친다 (vault-graph)

## goal

vault-graph README만 연 사용자도 vault-builder 설치 명령 한 줄로 설치를 시작한다(spec Intent 첫 항목, 발견5, 발견7).

## files

저장소: vault-graph, worktree `$HOME/workspace/vault-graph/.worktrees/feat-jh-install-update`

- `README.md`
- `tests/test_readme_onboarding_contract.py` (기존 계약 테스트가 바뀐 문구 때문에 실패할 때만 고친다)

## blockers

없음

## acceptance

- A-28
- A-29 (vault-graph 부분)
- A-30

## checks

- `uv run --python 3.12 pytest -q tests/test_readme_onboarding_contract.py`
- `uv run --python 3.12 --all-packages --all-extras pytest -q tests packages/*/tests`

## done-when

- [ ] "Install"의 첫 안내가 `curl -fsSL https://raw.githubusercontent.com/cutehackers/vault-builder/main/scripts/install.sh | bash`다. 이 경로는 task 10이 만드는 파일과 같다.
- [ ] README에 이 URL은 vault-builder PR이 `main`에 merge된 뒤에만 동작한다고 적었다. PR 설명에도 같은 내용을 적는다.
- [ ] vg만 설치하는 방법이 `uv tool install git+https://github.com/cutehackers/vault-graph.git`다(spec 결정3, 2026-11-04 HTTPS로 바꿈). 개인 host 별칭 `me.github.com`은 남아 있지 않다.
- [ ] "Quick Start"의 첫 예시가 `--agent claude`다.
- [ ] 개발용 editable 설치(`uv tool install -e .`)를 아래 절로 옮겼다.
