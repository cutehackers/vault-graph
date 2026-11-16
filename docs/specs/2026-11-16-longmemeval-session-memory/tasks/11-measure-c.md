# 11. measure-c

## id
11

## title
C 측정 보고서를 쓰고 세 관문을 확인한다

## goal
날짜 범위를 들일지 A 측정 값을 기준선으로 판단한다. 측정은 C의 마지막 코드 커밋에서 돌리고 recall 값만 쓴다(시간 값은 쓰지 않는다). B 코드 task와 병행한다.

## units
D1, D24, A21

## files
- docs/design/reports/2026-11-longmemeval-session-memory.md

## blockers
4, 7, 8, 9, 10

## checks
- 수동: C의 마지막 코드 커밋에서 `TZ=UTC longmemeval_run --limit 150 --date-rules`, `evaluate_search --split dev`, `evaluate_search --split test`, `evaluate_search --vault-id eval2`를 돌려 4번 task 값과 비교한다

## done-when
- [ ] 측정한 커밋 해시를 보고서에 적었다
- [ ] 보고서에 C 유형별 값, 세션 수, 층1(dev·test), 층2가 앞 단계 값과 나란히 있다
- [ ] 층1이 dev·test 모두 기준선 이상, 층2가 0.95 이상이다
- [ ] 못 넘으면 사유를 적는다
- [ ] R5(표본에서 효과가 작음)를 적는다
- [ ] 시간 값은 보고서에 쓰지 않았다
