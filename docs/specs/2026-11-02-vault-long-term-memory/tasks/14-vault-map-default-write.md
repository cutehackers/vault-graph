## id

14

## title

[vault-graph] G3a. V6. `vault-map.json`의 `default_write_vault`를 읽고 `vg status`에 보인다

## goal

vault-graph가 프로젝트의 기본 저장 Vault를 알고, 필드가 잘못되어도 map 전체를 버리지 않는다. spec Intent 3, 결정12·A1을 다룬다.

## files

저장소: vault-graph (이 worktree, 브랜치 `feat/jh/local-graph`)

- `src/vault_graph/operation/integration/vault_map.py`
- `src/vault_graph/project/context/project_binding_reader.py` (`MappedProjectMatch.default_write_vault`)
- `src/vault_graph/interface/cli/main.py` (`status`만)
- `tests/test_vault_map.py`
- `tests/test_cli_vault_map_setup_status.py`

## blockers

1, 7

## acceptance

A-22 (`default_write_vault`가 없는 version 2 map 호환)

## checks

vault-graph worktree에서 실행한다.

- `uv run --python 3.12 --all-packages --all-extras pytest -q tests/test_vault_map.py tests/test_cli_vault_map_setup_status.py tests/test_feature_import_direction.py`
- `uv run --python 3.12 --all-packages --all-extras pytest -q`

## done-when

- [ ] `default_write_vault`가 문자열이 아니거나 프로젝트 `vaults` 밖이면 그 필드만 무시하고 경고한다
- [ ] `MappedProjectMatch.default_write_vault`에 해당 `MappedVault`가 들어간다
- [ ] `vg status`가 프로젝트별 기본 저장 Vault와 무시한 필드 경고를 보인다
- [ ] 필드 없는 map에서 기존 테스트가 그대로 통과한다

멈춤: M12 reader가 M17을 가져와야 하면 보고한다.
