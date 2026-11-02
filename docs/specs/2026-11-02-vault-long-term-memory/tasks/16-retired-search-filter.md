## id

16

## title

[vault-graph] 결정S14. 기본 검색에서 `retired` 페이지를 빼고 INV-05 예외를 기록한다 (G3c)

## goal

폐기한 기억이 작업 중 검색에 나와 에이전트를 틀리게 하지 않는다. spec Intent 3, 결정S14를 다룬다.

## files

저장소: vault-graph (이 worktree, 브랜치 `feat/jh/local-graph`)

- `src/vault_graph/retrieval/search/` 안의 필터 위치 (위험5 확인 뒤 정함)
- `docs/DECISIONS.md` (INV-05 예외 항목)
- `tests/test_retired_search_filter.py` (새 파일)

## blockers

1, 4

## acceptance

A-10

## checks

vault-graph worktree에서 실행한다.

- `uv run --python 3.12 --all-packages --all-extras pytest -q tests/test_retired_search_filter.py tests/test_feature_import_direction.py`
- `uv run --python 3.12 --all-packages --all-extras pytest -q`

## done-when

- [ ] 시작할 때 M05 검색 단계에서 메타데이터 읽기 포트로 문서 frontmatter에 닿는지 확인했다(위험5)
- [ ] 결합 뒤 status `retired` 결과가 기본 검색 결과에서 빠진다
- [ ] 같은 질의에서 `deprecated` 페이지는 지금처럼 나온다
- [ ] `docs/DECISIONS.md`에 INV-05 예외 항목이 있다

멈춤: 위험5가 틀리면(M05에서 frontmatter에 닿지 않으면) 멈추고 보고한다. 필터를 구성 지점으로 옮기는 일은 이 작업에서 하지 않는다. 옮기면 작업 15·17의 파일과 겹친다. 그 경우의 후속 작업은 보고 뒤에 더한다(2026-11-02 분해 승인 답).
