# 4. measure-a

## id
4

## title
A 측정 보고서를 쓰고 세 관문을 확인한다

## goal
A를 들일지 기준선과 나란히 놓고 판단한다. D1의 부분별 측정을 A에서 시작한다. 측정은 A의 마지막 코드 커밋에서 돌리고 recall 값만 쓴다(시간 값은 쓰지 않는다). C 코드 task와 병행한다.

## units
D1, D24, A21

## files
- docs/design/reports/2026-11-longmemeval-session-memory.md

## blockers
1, 2, 3

## checks
- 수동: `longmemeval_run --limit 150`, `evaluate_search --split dev`, `evaluate_search --split test`, `evaluate_search --vault-id eval2`를 A의 마지막 코드 커밋에서 돌려 `research/baseline.md`와 비교한다

## done-when
- [ ] 측정한 커밋 해시를 보고서에 적었다
- [ ] 보고서에 LongMemEval 유형별 `recall_all_at_5`·`recall_any_at_5`와 세션 수가 기준선(재정렬 꺼짐, 켜짐도 적음)과 나란히 있다
- [ ] 층1 세션 recall@5가 dev·test 모두 기준선 이상이다
- [ ] 층2 recall@5가 0.95 이상이다
- [ ] 못 넘은 항목은 사유와 함께 적고, 들이지 않은 경우 D6 기본값을 되돌린다
- [ ] R1(붙은 근거까지 채점하는지)과 R8(실패 분류)을 확인해 적는다
- [ ] 시간 값은 보고서에 쓰지 않았다
