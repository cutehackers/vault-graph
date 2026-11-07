# 작업 4: README 수정과 전체 게이트

## id

4

## title

README 설치 절, Quick Start, 모델 내려받기 설명을 고치고 전체 게이트를 돌린다

## goal

사용자가 README만 보고 설치와 색인이 분리되었음을 알고 `vg index --all-vaults`를 실행할 수 있다. Intent 3을 만족하고 전체 변경을 확인한다.

## files

- `README.md`

## blockers

1, 2, 3

## acceptance

A-9, A-10 (A-2의 `vg --help` 명령 목록 동일 확인 포함)

## checks

- `grep -n -i "runs the first index\|indexes every" README.md` (결과가 없어야 한다)
- `uv run --python 3.12 ruff check src tests && uv run --python 3.12 mypy src tests && uv run --python 3.12 pytest -q tests packages/*/tests`

## done-when

- [ ] `README.md:31-49`가 설치 명령은 색인하지 않는다고 적는다.
- [ ] 같은 절의 새 단락에 `vg index --all-vaults` 명령, 첫 실행이 모델을 내려받는다는 것, 세션 원문이 많으면 수십 분 걸릴 수 있다는 것, 47분 측정과 그 조건(Vault 6개, 세션 원문 비율)이 들어 있다.
- [ ] 기존 "약 14분" 문장을 지우거나 새 단락으로 옮겼다.
- [ ] `README.md:88-98`이 `--no-index`를 한 줄로 설명한다.
- [ ] `README.md:202`가 "`vg setup --no-index`는 모델을 내려받지 않는다"를 더한다.
- [ ] 설치 명령이 색인한다는 문장이 README에 남지 않는다.
- [ ] `vg --help` 명령 목록이 변경 전과 같다.
- [ ] 위 전체 게이트(ruff, mypy, pytest)가 통과한다.
