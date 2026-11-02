## id

3

## title

[vault-builder] B1. 계약1. 발행 로직을 `tools/wiki/lib/publish.py`로 옮기고 `publish-draft --json`을 더한다

## goal

vault-graph가 텍스트 대신 정해진 JSON과 종료 코드로 발행 결과를 판단하고, 다른 Vault 명령도 발행 함수를 다시 쓸 수 있다. spec Intent 3·4를 다룬다.

## files

저장소: vault-builder (`$HOME/workspace/vault-builder`, 브랜치 `feat/jh/vault-graph-requests`)

- `tools/wiki/lib/publish.py` (새 파일, `publish_draft(root, draft_path, report_path=None) -> PublishResult`)
- `tools/wiki/cli.py`
- `tools/wiki/lib/draft.py` (`HumanLockError`)
- `tools/wiki/lib/draft_patch.py` (`PatchTargetMissing`만. frontmatter만 바꾸는 patch는 작업 5)
- `tests/test_publish_json.py` (새 파일)

## blockers

없음

## acceptance

A-11, A-21

## checks

`$HOME/workspace/vault-builder`에서 실행한다.

- `python3 -m unittest tests.test_publish_json tests.test_wiki_tools tests.test_wiki_lib_import_direction`
- `WIKI_GATE_FULL=1 bash scripts/release_gate.sh`
- `python3 -m unittest builder_tests.test_llm_wiki_router`

## done-when

- [ ] `reason` 일곱 가지(null, `lint-dirty-before`, `draft-invalid`, `human-locked`, `page-missing`, `lint-failed-after`, `io-error`)마다 필드와 종료 코드 0 또는 1을 테스트한다
- [ ] `--json`일 때 표준 출력은 `json.loads`로 읽히는 객체 하나이고, 사람이 읽는 줄은 표준 오류로 간다
- [ ] `--json` 없는 출력과 종료 코드, 기존 publish-draft 테스트가 그대로다
- [ ] 실패 시 원래 파일로 되돌리는 동작과 성공 뒤 지도를 다시 만드는 동작이 바뀌지 않았다
- [ ] `publish.py`는 `draft`, `lint`, `maps`만 가져온다

멈춤: 발행 로직을 추출하려면 `publish.py`가 `review`나 `cli`를 가져와야 하면 보고한다.
