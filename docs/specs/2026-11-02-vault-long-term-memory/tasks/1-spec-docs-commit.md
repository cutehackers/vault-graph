## id

1

## title

[vault-graph] 단계0. SPEC §0 결정12~15, DECISIONS 2026-11-02, 이 spec 폴더를 첫 커밋으로 올린다

## goal

이번 작업의 기준 문서가 구현보다 먼저 커밋된다. `docs/SPEC.md` §5에 "기존 필드는 바꾸지 않고, 선택 필드와 도구는 더할 수 있다"를 적어 위험12를 닫는다. spec Intent 8을 다룬다.

## files

- `docs/SPEC.md` (§0, §5)
- `docs/DECISIONS.md` (2026-11-02 항목)
- `docs/specs/2026-11-02-vault-long-term-memory/` (`spec.md`, `research/`, `tasks/`)

## blockers

없음

## acceptance

A-23 (이 작업의 첫 vault-graph 커밋 조건)

## checks

vault-graph worktree에서 실행한다.

- `git diff --stat HEAD -- src tests packages` (비어 있어야 함)
- `uv run --python 3.12 --all-packages --all-extras pytest -q`

## done-when

- [x] 이번 작업에서 vault-graph의 첫 커밋이다
- [x] `docs/SPEC.md` §0에 결정12~15가 있고, `docs/DECISIONS.md`에 2026-11-02 항목이 있다
- [x] `docs/SPEC.md` §5에 "기존 필드는 바꾸지 않고, 선택 필드와 도구는 더할 수 있다" 규칙이 있다
- [x] `src`, `tests`, `packages`에 변경이 없다

멈춤: `docs/SPEC.md` diff에 §0·§5 밖의 변경이 있으면 커밋하지 않고 보고한다.

기록 (2026-11-02): `docs/SPEC.md` diff에는 §0·§5 외에 목차, §1 원칙4·5, §4 한 줄 변경도 있다. 모두 이 세션 전부터 커밋 안 된 상태였고, 사용자가 인터뷰 답7에서 "그대로 채택, 첫 커밋에 포함"한 문서 변경의 일부로 보고 함께 커밋했다. 이 작업이 새로 더한 것은 §5 호환 규칙 한 줄이다. pytest: 1633 passed, 1 skipped.
