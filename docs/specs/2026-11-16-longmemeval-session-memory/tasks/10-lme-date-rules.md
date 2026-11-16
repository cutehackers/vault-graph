# 10. lme-date-rules

## id
10

## title
LongMemEval 변환기가 질문 날짜를 읽고 실행기가 `--date-rules`로 범위를 넘긴다

## goal
C의 효과를 CLI 경로로 잴 수 있다. Intent 4를 맡는다.

## units
D15, A11

## files
- tests/benchmarks/longmemeval_convert.py
- tests/benchmarks/longmemeval_run.py
- tests/test_longmemeval_convert_tool.py
- tests/test_longmemeval_run_session_count.py

## blockers
3, 5, 9

## checks
- tests/test_longmemeval_convert_tool.py
- tests/test_longmemeval_run_session_count.py

## done-when
- [ ] `LmeQuestion`이 `question_date`를 읽는다
- [ ] `--date-rules`면 풀리는 질문에만 `--since`·`--until`이 붙는다
- [ ] 인자가 없으면 명령이 변경 전과 같다
- [ ] R4 때문에 측정 명령이 `TZ=UTC`로 도는 것을 실행기 문서나 시험에 적는다
