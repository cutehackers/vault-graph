## id

16

## title

보완9 ARCHITECTURE와 VG-MOD에 재검증·보완 결과를 기록한다

## goal

문서의 의존 규칙과 `tests/test_feature_import_direction.py`의 허용 방향 표가 같아지고, 보완 결과를 문서에서 확인할 수 있다 (보완 계획 결정2 포함).

## files

- `docs/ARCHITECTURE.md` (의존 규칙)
- `docs/design/specs/2026-10-15-vault-graph-modular-architecture-ko.md` (완료 기록)
- `docs/design/plans/2026-10-15-vault-graph-modularization-plan-ko.md` (후속 보완 링크만 추가)

## blockers

15

## acceptance

A-20, A-21, A-22 (작업 전체의 최종 확인)

## checks

- `uv run --python 3.12 --all-packages --all-extras pytest -q tests/test_feature_import_direction.py`
- `grep -rnE "^\s*(import|from) (openai|anthropic)" src` (0건)
- `git diff --stat 28f1c96 -- pyproject.toml`에 LLM 클라이언트 의존성 추가가 없음
- CI 검증 세 명령 (작업 1의 checks와 같음)

## done-when

- [ ] 문서의 허용 방향 표와 `tests/test_feature_import_direction.py`의 표가 같다
- [ ] 테스트의 예외 목록이 비어 있다. 남는 항목이 있으면 VG-MOD에 규칙 예외로 적혀 있다
- [ ] 선행 문서의 "Complete" 표기는 그대로이고 후속 보완 링크만 추가됐다
- [ ] 이 작업 전체에서 Vault와 vault-builder 저장소의 파일이 바뀌지 않았다
