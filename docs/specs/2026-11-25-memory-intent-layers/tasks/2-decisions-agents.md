## id

2

## title

DECISIONS에 승인된 결정을 더하고 AGENTS.md Project Boundary 첫 문장을 바꾼다

## goal

사용자가 정한 결정이 DECISIONS에 기록되고 옛 층 두 항목이 대체됨으로 표시된다. AGENTS.md는 새 의도에 맞는 첫 문장을 갖는다.

## units

D12, D5, D6, D8, D9, D18, A4

## files

- docs/DECISIONS.md
- AGENTS.md

## blockers

(none)

## checks

- 수동: `docs/DECISIONS.md`에서 `2026-11-25` 항목과 두 2026-11-06 항목의 "Replaced by" 줄을 확인한다 (A4)

## done-when

- [ ] `2026-11-25 - …` 항목이 영어 파일 형식으로 D1, D2, D5, D6, D8, D9를 담는다
- [ ] `proposed` 결정(D3, D4, D7 등)이 적혀 있지 않다
- [ ] 2026-11-06 두 항목은 본문 그대로이고 끝에 "Replaced by" 한 줄이 있다. INV-05 항목은 그대로다
- [ ] AGENTS.md는 Project Boundary 첫 문장만 D18의 영어 문장으로 바뀌고 여섯 쓰기 경로와 나머지는 그대로다
- [ ] 새 글에 `test_naming_conventions.py` 금지어가 없다
