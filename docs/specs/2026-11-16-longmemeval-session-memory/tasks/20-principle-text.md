# 20. principle-text

## id
20

## title
원칙 문장을 세션 사실 첨부만 허용하도록 고친다

## goal
사실 추출 코드가 들어오기 전에 원칙 문서가 먼저 승인된 문장으로 바뀐다.

## units
D22, A20

## files
- docs/SPEC.md
- AGENTS.md
- docs/DECISIONS.md
- docs/PATCH_LOG.md

## blockers
없음

## checks
- 수동: `docs/SPEC.md` §1 원칙1·4와 §9.2 B-2, `AGENTS.md` Project Boundary를 승인된 D22 문장과 비교한다

## done-when
- [ ] SPEC 원칙1, 원칙4, §9.2 B-2 (5)와 AGENTS.md Project Boundary·machine-made content가 D22 문장과 같다
- [ ] 요약·목록·점수 금지 문장은 남아 있다
- [ ] `docs/DECISIONS.md`와 `docs/PATCH_LOG.md`에 항목이 있다
