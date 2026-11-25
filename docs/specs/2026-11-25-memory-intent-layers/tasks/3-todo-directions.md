## id

3

## title

docs/TODO.md에 Memory Intent Redesign 절을 더한다

## goal

나중 spec이 순서대로 가져갈 개선 방향이 열린 일로 남는다. 질의 설계의 경계(I5, I7, F6~F9)도 TODO가 가리키는 자리에 남는다.

## units

D13, D3, D4, D7, D19, I5, I7, F6, F7, F8, F9, A5, A12

## files

- docs/TODO.md

## blockers

(none)

## checks

- 수동: `docs/TODO.md`의 "Memory Intent Redesign" 절에서 항목 수, 순서, 링크를 이 spec §4.3, §6과 대조한다 (A5)
- 수동: `docs/TODO.md`의 3e 항목에 세션 시작 회상의 추출기 줄을 매 세션 낸다고 적혀 있는지 확인한다 (A12)

## done-when

- [ ] "Memory Intent Redesign (spec 2026-11-25)" 절에 3a, 3b~3e, 결정5, 4a~4e, 질의 설계가 D10 순서의 체크박스로 있다
- [ ] 항목이 이 spec §4.3과 §6(F6~F9)을 링크하고, 질의 설계 항목이 I5(층별 목록)와 I7(파생 데이터)을 가리킨다
- [ ] 3e 항목에 회상 줄을 매 세션 낸다(약 15토큰)고 적혀 있다
- [ ] n차-11(UserPromptSubmit 회상)에 4d로 옮겼다고 적혀 있다
- [ ] `archive/` 링크가 "git history의 `docs/archive/…`(커밋 `9ddce0c`)" 표기로 바뀌었다. 다른 문장은 고치지 않았다
- [ ] 새 글에 `test_naming_conventions.py` 금지어가 없다
