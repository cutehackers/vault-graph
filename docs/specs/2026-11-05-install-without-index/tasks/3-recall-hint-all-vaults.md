# 작업 3: 회상 안내를 `vg index --all-vaults`로 변경

## id

3

## title

세션 시작 회상 안내를 `vg index --all-vaults`로 바꾸고 무색인 동작을 테스트한다

## goal

색인 전 세션 시작이 올바른 색인 명령을 안내하고, 백그라운드 색인도 시작하지 않는다는 점이 테스트로 고정된다. Intent 3과 4를 받친다.

## files

- `src/vault_graph/context/pack/recall.py`
- `tests/test_cli_hook_session_start.py`

## blockers

없음

## acceptance

A-7

## checks

- `uv run --python 3.12 pytest -q tests/test_cli_hook_session_start.py tests/test_session_recall.py tests/test_context_pack_warnings.py tests/test_context_pack_renderer.py`
- `uv run --python 3.12 ruff check src/vault_graph/context/pack/recall.py tests/test_cli_hook_session_start.py`

## done-when

- [ ] `recall.py:172`와 `:175`의 "Run `vg index`."가 "Run `vg index --all-vaults`."로 바뀌었다.
- [ ] 색인되지 않은 Vault만 연결된 폴더에서 `vg hook session-start`가 종료 코드 3으로 끝나고, stderr에 `vg index --all-vaults`가 있다.
- [ ] 일부만 색인된 경우의 경고 줄에도 `vg index --all-vaults`가 있다.
- [ ] 두 경우 모두 `logs/session-start-index.pid`가 생기지 않는다.
- [ ] 회상 문구를 확인하던 기존 테스트가 있으면 새 문구에 맞게 고쳤다.
- [ ] MCP 도구 문구(spec §9 질문2 옵션1)는 건드리지 않았다.
