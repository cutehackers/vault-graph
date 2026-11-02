## id

7

## title

[vault-builder] B4. 계약5. `default_write_vault`, `set-default-write`, `set-role`, 계약 문서 `vault-map-v2.md`를 만든다

## goal

소유자가 `vault-map.json`을 손으로 고치지 않고 Vault 종류와 프로젝트의 기본 저장 Vault를 정한다. spec Intent 2·3을 다룬다.

## files

저장소: vault-builder (`$HOME/workspace/vault-builder`, 브랜치 `feat/jh/vault-graph-requests`)

- `tools/vault_migration/map_settings.py` (새 파일)
- `tools/vault_migration/cli.py`
- `tools/vault_migration/installing.py`
- `tools/vault_migration/linking.py`
- `docs/contracts/vault-map-v2.md` (새 파일)
- `builder_tests/test_map_settings.py` (새 파일)
- `builder_tests/test_llm_wiki_router.py` (새 필드가 있는 map 사례)

## blockers

없음

## acceptance

A-15, A-21, A-22 (router 부분)

## checks

`$HOME/workspace/vault-builder`에서 실행한다.

- `python3 -m unittest builder_tests.test_map_settings builder_tests.test_llm_wiki_router builder_tests.test_vault_migration`
- `WIKI_GATE_FULL=1 bash scripts/release_gate.sh`
- `python3 -m unittest builder_tests.test_llm_wiki_router`

## done-when

- [ ] `set-role`과 `set-default-write`가 다른 필드를 보존하고, 임시 파일을 쓴 뒤 이름을 바꾸는 방식으로 쓴다
- [ ] install·link 뒤 `default_write_vault`가 남는다
- [ ] 기본 저장 Vault를 unlink하면 `default_write_vault`가 지워진다
- [ ] router 테스트가 새 필드가 있는 map으로 통과한다
- [ ] `docs/contracts/vault-map-v2.md`에 필드, 선택 필드, 프로젝트 찾기 규칙의 소유자(router `find_project`), "형식을 깨면 version을 올린다" 규칙이 있다
- [ ] `map_settings.py`는 `hooks.py`를 가져오지 않는다

멈춤: router 형식 검사가 새 필드를 거부하면 spec V6의 전제와 어긋나므로 router 계약을 바꾸지 않고 보고한다.
