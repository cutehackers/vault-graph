# 2. vg mcp unregister

## id

2

## title

`vg mcp unregister --agent claude [--config-path PATH] [--dry-run]`을 추가한다 (vault-graph)

## goal

사용자가 vault-graph의 MCP 등록을 명령 하나로 지운다. 이 명령은 제거 절차의 vg 단계다(spec 발견10, §4.8).

## files

저장소: vault-graph, worktree `$HOME/workspace/vault-graph/.worktrees/feat-jh-install-update`

- `src/vault_graph/operation/integration/mcp/mcp_config_registration.py`
- `src/vault_graph/interface/cli/main.py` (`mcp_app`)
- `tests/test_mcp_config_unregister.py` (새 파일)

## blockers

- 1 (`main.py`를 함께 쓴다)

## acceptance

- A-24
- A-30

## checks

- `uv run --python 3.12 pytest -q tests/test_mcp_config_unregister.py tests/test_mcp_config_registration_claude.py tests/test_cli_mcp_config.py`
- `uv run --python 3.12 ruff check src tests packages`
- `uv run --python 3.12 mypy src tests packages/text-embeddings/src packages/vector-search/src packages/vector-index/src`
- `uv run --python 3.12 --all-packages --all-extras pytest -q tests packages/*/tests`

## done-when

- [ ] `mcpServers.vault-graph`만 지우고 다른 key는 그대로 둔다.
- [ ] 지울 때 백업 파일을 남긴다.
- [ ] 파일 규칙은 `register`와 같다(`mcp_config_registration.py:151-154`).
- [ ] `--dry-run`은 파일을 쓰지 않는다.
- [ ] 항목이 없으면 아무것도 쓰지 않는다. 출력은 `changed: False`이고 exit 0이다.
