## id

4

## title

[vault-builder] B2a. 계약2. 기억 frontmatter 선택 필드와 status `retired`를 더한다

## goal

Vault가 고정 기억, 기억 종류, 대체 없는 폐기를 lint로 검증하고, 모든 Vault 도구가 `retired`를 "현재 아님"으로 다룬다. spec Intent 3·6을 다룬다.

## files

저장소: vault-builder (`$HOME/workspace/vault-builder`, 브랜치 `feat/jh/vault-graph-requests`)

- `tools/wiki/lib/memory_fields.py` (새 파일, `validate_memory_fields(page) -> list[Issue]`)
- `tools/wiki/lib/schema.py` (`ALLOWED_STATUS`에 `retired`)
- `tools/wiki/lib/lint.py` (`lint_repo`에서 호출)
- 위험4 검색으로 찾은 status 목록 위치. 예상 위치는 `tools/wiki/lib/`의 검색, 지도, 지표, `memory_scan`과 `tools/vault_migration/assets/llm-wiki-router/llm_wiki_router.py`
- `tests/test_memory_fields.py` (새 파일)

## blockers

없음

## acceptance

A-12, A-21

## checks

`$HOME/workspace/vault-builder`에서 실행한다.

- `python3 -m unittest tests.test_memory_fields tests.test_wiki_tools tests.test_wiki_lib_import_direction`
- `grep -rn "deprecated" tools` (새로 찾은 위치마다 `retired`가 같은 의미로 있는지 확인)
- `WIKI_GATE_FULL=1 bash scripts/release_gate.sh`
- `python3 -m unittest builder_tests.test_llm_wiki_router`

## done-when

- [x] spec 계약2의 lint 규칙 1~5가 있다
- [x] lint가 `pin: "yes"`, 허용 밖 `memory_kind`, `memory_schema` 없는 `pin`, `retired_reason` 없는 `retired`에서 오류를 낸다
- [x] 새 필드가 없는 기존 페이지로 만든 Vault의 lint가 그대로 통과한다
- [x] `retired`는 `superseded_by` 없이 유효하고, `deprecated` + `superseded_by` 규칙은 그대로다
- [x] `deprecated`를 나열하는 모든 위치에 `retired`를 "현재 아님"으로 더했다
- [x] `memory_fields.py`는 `schema`와 `frontmatter`만 가져온다

멈춤: status 위치가 작업 3의 파일(`cli.py`, `draft.py`, `draft_patch.py`, `publish.py`)에 있으면 같은 단계에서 같은 파일을 쓰게 되므로 보고한다.

기록 (2026-11-02, vault-builder c24d4a5): `tests.test_memory_fields` 24개 통과, router 70개 통과. `test_wiki_tools` 실패는 설치 자체 검사(v3 해시)뿐이며 작업 10까지 허용. 작업 10이 챙길 것: `memory_fields.py`와 `publish.py`를 v4 관리 파일에 넣는다(`lint.py`가 가져옴). 작업 17·21이 챙길 것: 폐기 페이지로 가는 링크도 `deprecated_linked_pages`에 들어가 metrics 정책(허용 0)에 걸린다.
