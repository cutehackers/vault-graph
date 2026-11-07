# 작업 2: `install.sh`를 `--no-index`로 바꾸고 색인 안내를 출력

## id

2

## title

`install.sh`가 `--no-index`로 setup하고, 옛 `vg`를 막고, 색인 안내를 출력한다

## goal

설치 명령이 색인 없이 빨리 끝나고, 사용자가 설치 출력만 보고 `vg index --all-vaults`를 찾아 실행할 수 있다. Intent 1, 3, 5를 만족한다.

## files

- `scripts/install.sh`
- `tests/test_install_script.py`

## blockers

없음. 테스트는 가짜 `vg`를 쓰므로 작업 1 코드에 의존하지 않는다.

## acceptance

A-1, A-2(`vg --help` 명령 목록 동일 확인은 작업 4), A-3, A-6(설치 `--dry-run` 안내), A-11

## checks

- `uv run --python 3.12 pytest -q tests/test_install_script.py`
- `bash -n scripts/install.sh`
- `uv run --python 3.12 ruff check tests/test_install_script.py`

## done-when

- [ ] 5단계가 `"${VG}" setup --agent claude --mcp --no-index`이고, 앞 안내에서 색인과 모델 내려받기 문장을 뺐다.
- [ ] 머리 주석 5번과 dry run 안내가 같은 명령으로 바뀌었다.
- [ ] `vg setup` 전에 `setup --help`에 `--no-index`가 있는지 확인한다. 없으면 `vg setup`을 부르지 않고 0이 아닌 코드로 멈추며, 출력에 설치된 `vg` 경로, 옛 버전이라는 설명, `VAULT_GRAPH_REF` 안내, 직접 `vg setup`을 돌리면 색인까지 한다는 설명이 들어간다.
- [ ] 성공 출력의 맨 끝 순서가 재시작과 `/mcp` 안내, 색인을 하지 않았다는 문장, 색인 명령 한 줄, 모델 약 135 MB와 수십 분 걸릴 수 있다는 문장이다.
- [ ] 색인 명령 줄이 PATH에 있으면 `vg index --all-vaults`이고, 없으면 `${VG}` 전체 경로로 시작한다. 두 경우 모두 테스트한다.
- [ ] 테스트에서 가짜 `vg` 호출 기록의 마지막 항목이 `setup --agent claude --mcp --no-index`이고, `index`로 시작하는 호출이 없다.
- [ ] 옛 `vg`(도움말에 옵션 없음) 테스트가 `vg setup` 미호출과 0이 아닌 종료 코드를 확인한다.
- [ ] 설치 `--dry-run` 출력에 `--no-index`가 들어 있다.
