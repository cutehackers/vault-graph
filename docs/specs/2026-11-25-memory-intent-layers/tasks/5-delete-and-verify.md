## id

5

## title

옛 설계 문서 네 묶음을 지우고 문서 전체의 경계를 확인한다

## goal

중복된 옛 문서가 저장소에서 사라지고, 코드·테스트가 안 바뀌었다는 것과 남길 문서가 그대로라는 것이 확인된다. 문서만 바꾼다는 이번 change의 경계(D10)를 닫는 일이다.

## units

D10, D14, D15, D16, F1, F2, F4, A1, A6, A7, A8, A9, A11

## files

- docs/superpowers/ (폴더 전체 삭제)
- docs/stenc/ (폴더 전체 삭제)
- open-docs.sh (삭제)
- docs/archive/ (폴더 전체 삭제)
- docs/html/2026-10-29-vault-memory-design.html (삭제)

## blockers

1, 2, 3, 4

## checks

- tests/test_context_pack_docs_contract.py
- tests/test_retired_search_filter.py
- tests/test_naming_conventions.py
- tests/test_readme_onboarding_contract.py
- 수동: base `9ddce0c`과 change 끝 commit의 차이 파일 목록에 `src/`, `packages/`, `tests/`, `scripts/`, `pyproject.toml`, `uv.lock`, `.github/`가 없는지 확인한다 (A1)
- 수동: `docs/superpowers`, `docs/stenc`, `open-docs.sh`, `docs/archive`, `docs/html/2026-10-29-vault-memory-design.html`이 작업 트리와 git index에 없는지 확인한다 (A6)
- 수동: README 두 개, AGENTS, `docs/` 바로 아래 `.md`(DECISIONS, PATCH_LOG 제외), `docs/design/glossary.md`에서 `superpowers/`, `stenc`, `open-docs`, `archive/`, `2026-10-29-vault-memory-design`을 찾아 0줄인지 확인한다. 예외는 vault-builder 저장소 경로를 가리키는 SPEC·TODO 줄이다 (A7)
- 수동: `docs/ARCHITECTURE.md`, `docs/DEVELOPMENT.md`, `docs/SPEC.md` §8, `docs/design/glossary.md`의 `design/` 링크 대상 파일이 모두 있는지 확인한다 (A8)
- 수동: base `9ddce0c`과 비교해 `CLAUDE.md`, `docs/ARCHITECTURE.md`, `docs/FEATURES.md`, README 두 개, `docs/design/glossary.md`에 차이가 없고 `AGENTS.md`의 차이가 Project Boundary 첫 문장 하나뿐인지 본다 (A11)

## done-when

- [ ] 네 묶음과 `open-docs.sh`, 옛 기억 설계 HTML이 작업 트리와 git index에서 없다. `docs/design/`(specs, plans, intents, reports)와 `docs/specs/`는 남아 있다
- [ ] A7 검색 결과가 0줄이다. DECISIONS, PATCH_LOG, `docs/specs/`, `docs/design/`의 이력 속 옛 경로는 고치지 않았다
- [ ] 변경 파일 목록에 제품 코드, 테스트, 설정이 없다
- [ ] 문서를 읽는 테스트 네 개가 통과한다. 실패하면 문서를 고치고 테스트는 바꾸지 않는다
- [ ] 고치지 않기로 한 문서(CLAUDE.md, ARCHITECTURE, FEATURES, README, 용어집)에 차이가 없다
