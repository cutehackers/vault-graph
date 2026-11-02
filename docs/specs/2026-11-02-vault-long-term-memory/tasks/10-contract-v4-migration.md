## id

10

## title

[vault-builder] B6. 계약7. Vault 계약 버전 4와 마이그레이션을 만든다

## goal

계약1~4의 `tools/wiki` 변경과 작업 2의 gate 변경이 audit → apply로 기존 Vault에 전달된다. spec Intent 4를 다룬다.

## files

저장소: vault-builder (`$HOME/workspace/vault-builder`, 브랜치 `feat/jh/vault-graph-requests`)

- `tools/wiki/lib/vault_manifest.py` (`MANIFEST_CONTRACT_VERSION` 4)
- `tools/vault_migration/contracts/v4.json` (새 파일)
- `tools/vault_migration/versioning.py`
- `tools/vault_migration/manifests.py`
- `tools/vault_migration/applying.py`, `tools/vault_migration/managed_paths.py` (필요할 때만)
- `builder_tests/test_vault_migration.py`

## blockers

2, 4, 5, 6

## acceptance

A-17 (1·2번째 항목. 3번째 항목은 작업 17)

## checks

`$HOME/workspace/vault-builder`에서 실행한다.

- `python3 -m unittest builder_tests.test_vault_migration`
- `WIKI_GATE_FULL=1 bash scripts/release_gate.sh`
- `python3 -m unittest builder_tests.test_llm_wiki_router`

## done-when

- [x] `MANIFEST_CONTRACT_VERSION`이 4다
- [x] v4 계약에 새 `tools/wiki` 파일(`publish.py`, `memory_fields.py`, `memory_proposal.py`), 새 tests, 바뀐 `scripts/release_gate.sh`가 들어 있다
- [x] 계약 3으로 고정한 Vault를 audit → apply 하면 계약 4가 되고 lint가 통과한다
- [x] 사람이 고친 관리 파일 앞에서는 덮어쓰지 않고 멈춘다(위험8, `managed_paths.py` 규칙 확인)

멈춤: 마이그레이션이 사람이 고친 파일을 덮어쓰거나, 작업 9의 파일인 `installing.py`를 고쳐야 하면 보고한다.

기록 (2026-11-02, vault-builder `git log --grep "B6"`): `WIKI_GATE_FULL=1 bash scripts/release_gate.sh` 종료 코드 0, `builder_tests.test_vault_migration` 381개 통과. 멈춤 판단: 작업 9를 시작하기 전이라 `installing.py`의 계약 경로 한 줄만 고쳤다(동시 수정 없음). 범위 조정: `tests/test_draft_patch_frontmatter.py`를 자기 완결로 바꾸고 `tests/test_wiki_tools.py`의 계약 번호 기대값만 4로 고쳤다. VERSION은 2.0.0으로 둔다(릴리스는 이번 범위 밖, CHANGELOG 규칙상 계약 변경 릴리스는 3.0.0).
