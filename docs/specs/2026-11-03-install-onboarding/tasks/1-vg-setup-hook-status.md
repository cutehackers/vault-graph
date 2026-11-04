# 1. vg setup이 hook 상태를 보고한다

## id

1

## title

`vg setup`이 마지막에 hook 상태를 `warning:` 한 줄로 보고한다 (vault-graph)

## goal

사용자가 `vg setup`만 실행해도 hook이 vg를 제대로 쓰는지 알고, 고치는 명령(`vault-builder setup`)을 안내받는다(spec 발견2, 발견8, 결정12).

## files

저장소: vault-graph, worktree `$HOME/workspace/vault-graph/.worktrees/feat-jh-install-update`

- `src/vault_graph/operation/integration/hook_status.py` (새 파일)
- `src/vault_graph/interface/cli/main.py` (`setup`, 412-465행 부근)
- `tests/test_cli_setup_hook_status.py` (새 파일)

## blockers

없음

## acceptance

- A-16 (vg 부분)
- A-17
- A-26 (`vg setup`의 `--agent` 기본값 `codex` 유지)
- A-30

## checks

- `uv run --python 3.12 pytest -q tests/test_cli_setup_hook_status.py tests/test_cli_setup.py`
- `uv run --python 3.12 ruff check src tests packages`
- `uv run --python 3.12 mypy src tests packages/text-embeddings/src packages/vector-search/src packages/vector-index/src`
- `uv run --python 3.12 --all-packages --all-extras pytest -q tests packages/*/tests`

## done-when

- [ ] `<설정 폴더>`를 `vault_map_path`와 같은 규칙(`CLAUDE_CONFIG_DIR`, 없으면 `$HOME/.claude`)으로 구한다.
- [ ] 다음 세 경우가 각각 `vault-builder setup` 안내가 붙은 `warning:` 한 줄을 출력한다.
  - [ ] 파일이 없다: "hook이 설치되지 않았다"
  - [ ] `vg` 값이 없거나 실행 파일이 아니다: "hook이 vg를 찾지 못한다"
  - [ ] 실행 중인 vg와 경로가 다르다: "hook이 다른 vg를 쓴다"
- [ ] 정상이면 경고가 없다.
- [ ] JSON 오류도 경고로만 처리한다. 색인과 MCP 등록은 계속하고 exit 값은 바뀌지 않는다.
- [ ] 실행 전후로 `vault-hooks.json`과 `settings.json`의 hash가 같다는 테스트가 있다.
- [ ] `--agent` 기본값이 `codex` 그대로다.
