## id

20

## title

[vault-graph] G7. V5 `vg hook capture`를 만든다

## goal

세션이 압축되거나 끝날 때 vg가 수집 시점을 받아 Vault 실행기를 부르고, 수집 대상과 내용은 Vault 도구가 정한다. spec Intent 5, 결정5·S4·S10을 다룬다.

## files

저장소: vault-graph (이 worktree, 브랜치 `feat/jh/local-graph`)

- `src/vault_graph/interface/cli/hook_commands.py`
- `src/vault_graph/interface/composition/adapters/vault_capture_cli.py` (새 파일, `run_capture(hook_json, *, launcher, timeout_s) -> CaptureOutcome`)
- `tests/test_cli_hook_capture.py` (새 파일)

## blockers

8, 18

## acceptance

A-4 (단위 수준. 실제 Vault 증명은 작업 21), A-18, A-19

## checks

vault-graph worktree에서 실행한다.

- `uv run --python 3.12 --all-packages --all-extras pytest -q tests/test_cli_hook_capture.py tests/test_cli_hook_session_start.py tests/test_feature_import_direction.py tests/test_module_import_cycles.py`
- `uv run --python 3.12 --all-packages --all-extras pytest -q`

## done-when

- [x] `vg hook capture [--vault-map PATH] [--timeout S]`가 표준 입력의 훅 JSON을 `vault-map.json` 폴더의 `vault_hooks.py capture --direct`에 그대로 넘긴다
- [x] 결과(`status`, `vault`, `path`)를 표준 오류에 한 줄로 요약한다
- [x] 종료 코드는 실행기가 끝나면 0(written, no-new-turns, skipped 모두), 실행기를 못 찾거나 시간이 넘으면 3이다
- [x] Graph Home에 아무것도 쓰지 않고, 수집 뒤 색인하지 않고, role로 분기하지 않는다
- [x] 가짜 실행기로 실행해도 Vault 폴더의 파일 sha256이 바뀌지 않는다

멈춤: 수집에 Vault 선택 같은 정책 판단이 필요해지면 결정S4에 어긋나므로 보고한다.

기록 (2026-11-02): 전체 pytest 1841 passed, 1 skipped(작업 19 진행 중 시점). 실행기가 0이 아닌 코드로 끝나도 3을 돌려 실행기가 `capture --direct`로 넘어가게 한다(수집 두 번은 안전). 기본 시간 제한 20초(실행기는 vg에 25초를 준다). 실행기는 map을 `CLAUDE_CONFIG_DIR`(기본 `$HOME/.claude`)에서 읽으며, vg는 환경을 바꾸지 않는다.
