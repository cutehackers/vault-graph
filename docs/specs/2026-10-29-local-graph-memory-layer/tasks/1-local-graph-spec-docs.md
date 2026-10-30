## id

1

## title

1차-0 SPEC v5.0을 보관하고 Local-Graph SPEC을 쓰며, 경계 문서의 원칙을 하나로 맞춘다

## goal

활성 제품 계약이 Local-Graph 하나가 되고, 모든 경계 문서가 "Vault 쓰기는 remember가 publish-draft를 실행하는 것뿐"이라는 같은 원칙을 적는다. n차 항목과 Vault 쪽 미구현 항목이 문서에 보인다. spec Intent 1과 6을 다룬다.

## files

- `docs/archive/SPEC-v5.0.md` (`git mv`로 옮기고 안내 한 줄만 추가)
- `docs/SPEC.md` (새로 씀)
- `AGENTS.md`
- `docs/TODO.md`
- `docs/ARCHITECTURE.md` (§4)
- `docs/design/specs/2026-10-15-vault-graph-modular-architecture-ko.md` (INV-01, INV-02, INV-04)
- `docs/DECISIONS.md` (결정4, 6, 7, 8, 9, 10, 11)

결정 (2026-10-30 승인): DECISIONS는 이 작업에서 결정4·6·7·8·9·10·11을 적는다. 결정6은 spec 4.1절 7번 목록에는 없지만 9절 질문8 답에 따라 넣는다. S7(INV-05 예외)은 작업 13에서 적는다.

## blockers

없음

## acceptance

A-1, A-2, A-3, A-4, A-5

## checks

- `uv run --python 3.12 --all-packages --all-extras pytest -q tests/test_context_pack_docs_contract.py tests/test_readme_onboarding_contract.py`
- `git diff --stat 28f1c96 -- src tests packages pyproject.toml` (비어 있어야 함)
- `git show 28f1c96:docs/SPEC.md | diff - <(tail -n +2 docs/archive/SPEC-v5.0.md)`
- `grep -c "Active Roadmap: Software Invariant Engine" docs/TODO.md` (0이어야 함)
- CI 검증 세 명령: `uv run --python 3.12 ruff check src tests packages`, `uv run --python 3.12 mypy src tests packages/text-embeddings/src packages/vector-search/src packages/vector-index/src`, `uv run --python 3.12 --all-packages --all-extras pytest -q tests packages/*/tests`

## done-when

- [ ] `docs/archive/SPEC-v5.0.md`의 본문이 안내 한 줄을 빼면 `28f1c96`의 `docs/SPEC.md`와 같다
- [ ] 새 `docs/SPEC.md`가 spec 4.1절 2번의 항목 1~10을 담고, "Minimum JSON shape" 제목과 JSON이 남아 있다
- [ ] `AGENTS.md` Project Boundary, `docs/TODO.md` Operating Rules, `docs/ARCHITECTURE.md` §4, VG-MOD INV-01·02·04가 같은 원칙을 적는다
- [ ] `docs/TODO.md`와 `docs/SPEC.md`에 n차-1~12와 의존1~7이 있고, 의존마다 소유자와 미구현 여부가 적혀 있다
- [ ] SPEC 단계 표에 vault-builder 요청 문서 경로가 있다
- [ ] `docs/DECISIONS.md`에 결정 7개가 Question/Decision/Reason/Implications 형식으로 있고, 결정6과 결정11은 Vault 쪽이 소유하는 정책으로 적혀 있다
- [ ] `src`, `tests`, `packages`, `pyproject.toml`에 변경이 없다
