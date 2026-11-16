# 22. measure-b

## id
22

## title
B를 시범 20문항으로 두 추출기와 비교하고 보고서를 쓴다

## goal
사실 키를 들일지, 기본 추출기를 로컬로 바꿀지 판단한다. 측정은 B의 마지막 코드 커밋에서 돌린다. recall은 언제 재도 되지만, 추출기별 호출 수와 시간은 기계가 한가할 때(다른 측정이 돌지 않을 때)만 잰다.

## units
D1, D18, D23, D24, A21, A22

## files
- docs/design/reports/2026-11-longmemeval-session-memory.md

## blockers
11, 12, 21

## checks
- 수동: B의 마지막 코드 커밋에서 정한 문항으로 `longmemeval_run`을 사실 추출 꺼짐, Claude, `llama-server`로 돌려 유형별 recall을 본다
- 수동: `longmemeval_run --limit 150`, `evaluate_search --split dev`·`--split test`, `evaluate_search --vault-id eval2`로 11번 task 값과 비교한다

## done-when
- [ ] 측정한 커밋 해시를 보고서에 적었다
- [ ] 시범 20문항(multi-session·temporal-reasoning)을 먼저 재고, 효과가 보이면 150문항 안의 두 유형 전체로 넓힌다
- [ ] 보고서에 문항 범위, 추출기별 호출 수·시간(한가할 때 잰 값), 유형별 `recall_all_at_5`, 기본 추출기 판단 근거가 있다
- [ ] 로컬 `recall_all_at_5`가 Claude보다 0.02 이하로 낮을 때만 기본값을 로컬로 바꾼다
- [ ] B 부분의 층1(dev·test)과 층2가 기준선 이상, 0.95 이상이다. 못 넘으면 사유를 적는다
- [ ] R6(21번 메모), R7, R9를 적는다
