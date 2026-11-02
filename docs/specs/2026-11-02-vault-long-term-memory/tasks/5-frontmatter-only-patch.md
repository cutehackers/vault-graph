## id

5

## title

[vault-builder] B2b. 계약3. frontmatter만 바꾸는 `patch-page`를 받는다

## goal

폐기가 본문을 다시 보내지 않고, 적용 시점의 현재 파일 위에서 frontmatter만 바꾼다. spec Intent 3을 다룬다.

## files

저장소: vault-builder (`$HOME/workspace/vault-builder`, 브랜치 `feat/jh/vault-graph-requests`)

- `tools/wiki/lib/draft_patch.py`
- `tests/test_draft_patch_frontmatter.py` (새 파일)

## blockers

3

## acceptance

A-13

## checks

`$HOME/workspace/vault-builder`에서 실행한다.

- `python3 -m unittest tests.test_draft_patch_frontmatter tests.test_publish_json tests.test_wiki_tools`
- `WIKI_GATE_FULL=1 bash scripts/release_gate.sh`
- `python3 -m unittest builder_tests.test_llm_wiki_router`

## done-when

- [x] `frontmatter`에 키가 하나 이상 있으면 `edits`가 없거나 빈 목록이어도 patch가 적용된다
- [x] `edits`와 `frontmatter`가 모두 비면 지금처럼 거부된다
- [x] 사람이 잠근 페이지에는 frontmatter만 바꾸는 patch도 거부된다
- [x] 기존 patch 테스트가 그대로 통과한다

멈춤: frontmatter만 바꾸는 patch가 사람 잠금 검사를 우회하는 구조라면 보고한다.

기록 (2026-11-02, vault-builder `git log --grep "B2b"`): 테스트 8개 포함 집중 테스트 52개 통과. `edits` 키가 없는 draft를 받으려고 `draft.py` `_validate_single_draft_shape` 한 줄도 고쳤다(범위 조정). `test_wiki_tools` 실패는 설치 자체 검사(v3 해시)뿐.
