## id
18

## title
S9b 회상 구획L3와 예산 분할

## goal
brief와 L3 목록이 회상 앞에 들어가고, 구획L3가 실패하면 그 구획만 빠진다. (Intent 7, 8)

## spec
§4.4.6 표, §6 구획L3 행

## acceptance
A-25(회상 출력), A-26, A-27(S9), A-29(S9)

## files
- src/vault_graph/context/pack/recall.py
- tests/test_recall_l3_section.py (신규)
- tests/test_recall_budget.py (신규)

## blockers
1, 15

## checks
pytest tests/test_recall_l3_section.py tests/test_recall_budget.py tests/test_recall_pins.py tests/test_session_recall.py -q

## wave
5

## done-when
- [ ] 회상이 1,500토큰과 9,000자 이하, 구획A ≤ 400, 구획L3 ≤ 500, 구획C·D ≤ 180이다
- [ ] 구획L3를 못 만들면 구획B가 그만큼 길어지고 나머지는 같다
- [ ] 사용 기록을 지운 상태와 있는 상태의 구획A·L3·B가 같다
- [ ] vg 경로와 `recall.sh` 경로의 첫 줄 확인 기록을 PR에 남긴다(A-29)
- [ ] vault-graph pytest 전체 통과, 독립 커밋

## notes
`recall.py`는 #10, #18, #34, #41이 wave를 나누어 수정한다.
