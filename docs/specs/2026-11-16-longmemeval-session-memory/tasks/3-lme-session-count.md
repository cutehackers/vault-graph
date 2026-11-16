# 3. lme-session-count

## id
3

## title
LongMemEval 실행기가 상위 5개의 서로 다른 세션 수를 적는다

## goal
접기 효과를 문항별·유형별 세션 수로 볼 수 있다. 기존 `recall_*_at_5` 채점은 그대로다. Intent 4(부분마다 측정)를 맡는다.

## units
D7, A5

## files
- tests/benchmarks/longmemeval_run.py
- tests/test_longmemeval_run_session_count.py

## blockers
없음

## checks
- tests/test_longmemeval_run_session_count.py

## done-when
- [ ] `results.jsonl`에 문항별 서로 다른 세션 수가 있다
- [ ] `summary.json`에 유형별 평균이 있다
- [ ] 같은 입력의 `recall_all_at_5`, `recall_any_at_5`가 변경 전과 같다는 시험이 있다
