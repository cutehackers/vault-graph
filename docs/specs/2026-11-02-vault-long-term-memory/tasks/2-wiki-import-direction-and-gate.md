## id

2

## title

[vault-builder] B0. `tools/wiki` 가져오기 방향 검사를 만들고, 새 테스트 파일이 release gate에서 실행되게 한다

## goal

spec §4.4의 모듈 방향을 첫 B 작업부터 기계로 검사한다(Intent 7). 뒤 작업들이 `scripts/release_gate.sh`를 고치지 않아도 새 테스트가 gate에서 실행된다.

## files

저장소: vault-builder (`$HOME/workspace/vault-builder`, 브랜치 `feat/jh/vault-graph-requests`)

- `tests/test_wiki_lib_import_direction.py` (새 파일)
- `scripts/release_gate.sh`

## blockers

없음

## acceptance

A-21, A-24

## checks

`$HOME/workspace/vault-builder`에서 실행한다.

- `python3 -m unittest tests.test_wiki_lib_import_direction`
- `WIKI_GATE_FULL=1 bash scripts/release_gate.sh`
- `python3 -m unittest builder_tests.test_llm_wiki_router`

## done-when

- [ ] 규칙 표에 spec §4.4의 모든 모듈과 금지 방향이 있다(`review.py`가 `memory_proposal`을, `publish.py`가 `review`와 `memory_proposal`을, `hooks.py`와 `map_settings.py`가 서로를 가져오지 않음 포함)
- [ ] 아직 없는 파일의 규칙은 건너뛰고, 건너뛴 규칙 이름을 출력한다
- [ ] gate가 `tests/test_*.py` 전부와 `builder_tests/test_map_settings.py`, `builder_tests/test_hooks_install.py`, `builder_tests/test_vault_hooks_launcher.py`를 파일이 있으면 실행한다
- [ ] `release_gate.sh`는 `tools/vault_migration/contracts/v3.json`이 관리하는 Vault 파일이므로, 이 변경을 작업 10의 v4 계약에 넣을 항목으로 커밋 메시지에 적었다

멈춤: gate 구조상 `tests/`와 `builder_tests/`를 함께 실행할 수 없으면 보고한다.
