## id

9

## title

[vault-builder] B5b. 계약6의 install `--with-hooks`와 uninstall 정리(`hooks.py`)를 만든다

## goal

사용자가 선택 항목 하나로 SessionStart, PreCompact, SessionEnd 훅을 설치하고 지울 수 있고, 다른 프로그램의 훅은 보존된다. spec Intent 5를 다룬다.

## files

저장소: vault-builder (`$HOME/workspace/vault-builder`, 브랜치 `feat/jh/vault-graph-requests`)

- `tools/vault_migration/hooks.py` (새 파일)
- `tools/vault_migration/cli.py`
- `tools/vault_migration/installing.py` (실행기 복사, `vault-hooks.json` 기록)
- `tools/vault_migration/uninstalling.py`
- `builder_tests/test_hooks_install.py` (새 파일)

## blockers

7, 8

## acceptance

A-16, A-21

## checks

`$HOME/workspace/vault-builder`에서 실행한다.

- `python3 -m unittest builder_tests.test_hooks_install builder_tests.test_vault_migration`
- `WIKI_GATE_FULL=1 bash scripts/release_gate.sh`
- `python3 -m unittest builder_tests.test_llm_wiki_router`

## done-when

- [x] `install --with-hooks`가 세 훅 항목을 더하고, 두 번째 실행은 `settings.json` 바이트를 바꾸지 않는다
- [x] 미리 넣어 둔 다른 훅 항목이 남는다
- [x] uninstall 뒤 실행기 경로를 담은 항목만 사라진다
- [x] `--with-hooks` 없는 install은 `settings.json`을 읽지도 쓰지도 않는다
- [x] `settings.json`이 JSON이 아니면 install이 아무것도 쓰지 않고 멈춘다
- [x] install이 `$HOME/.claude/vault-builder/vault-hooks.json`에 vg 절대 경로를 기록한다
- [x] PreCompact·SessionEnd 항목의 `timeout`이 60초다
- [x] 테스트는 임시 HOME만 쓴다
- [x] `hooks.py`와 `map_settings.py`는 서로를 가져오지 않는다

멈춤: 테스트나 실행이 실제 `$HOME/.claude/settings.json`에 닿게 되면 보고한다.

기록 (2026-11-02, vault-builder `git log --grep "B5b"`): `WIKI_GATE_FULL=1 bash scripts/release_gate.sh` 종료 코드 0, 훅 방향 규칙이 이제 건너뛰지 않고 실행된다. 테스트는 임시 HOME만 쓰며 실제 `$HOME/.claude`에 닿는 경로가 없었다. 기존 가드 테스트 이름을 `test_only_hooks_module_names_settings_json`으로 바꿨다(검사 내용 같음). 훅 파일은 manifest에 기록하지 않고, 마지막 Vault를 지울 때 실행기 경로로 찾아 지운다.
