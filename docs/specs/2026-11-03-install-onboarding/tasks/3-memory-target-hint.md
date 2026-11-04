# 3. memory_target 안내 문구

## id

3

## title

`memory_target`의 `set-default-write` 안내를 `vault-builder set-default-write ...`로 바꾼다 (vault-graph)

## goal

기본 쓰기 Vault가 없을 때 vg가 어느 폴더에서나 실행되는 명령을 안내한다(spec 발견9, §4.7).

## files

저장소: vault-graph, worktree `$HOME/workspace/vault-graph/.worktrees/feat-jh-install-update`

- `src/vault_graph/operation/memory/memory_target.py` (61-67행)
- `tests/test_memory_target.py` (77행 기대값)

## blockers

없음

## acceptance

- A-30 (§4.7 안내 문구 변경)

## checks

- `uv run --python 3.12 pytest -q tests/test_memory_target.py`
- `uv run --python 3.12 ruff check src tests packages`
- `uv run --python 3.12 mypy src tests packages/text-embeddings/src packages/vector-search/src packages/vector-index/src`

## done-when

- [ ] 안내 형식이 `vault-builder set-default-write --project <id> --vault <...>`다.
- [ ] 테스트 기대값을 새 문구로 고쳤고, 테스트가 통과한다.
