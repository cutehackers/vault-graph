# 19. lme-facts-args

## id
19

## title
LongMemEval 실행기가 B 측정이 아니면 사실 추출을 끄고 캐시 폴더를 받는다

## goal
측정과 시험이 실제 추출기를 부르지 않고, B 측정에서는 캐시를 문항 사이에 공유한다. Intent 4를 맡는다.

## units
D19, D20, A25

## files
- tests/benchmarks/longmemeval_run.py
- tests/test_longmemeval_run_session_count.py

## blockers
10, 13, 17

## checks
- tests/test_longmemeval_run_session_count.py

## done-when
- [ ] B 측정 인자가 없으면 작업 공간 Graph Home마다 `enabled: false`를 쓴다
- [ ] 그 실행에서 `claude`나 `llama-server` 호출이 없다는 시험이 있다
- [ ] 캐시 폴더 인자와 추출기 고르기 인자로 B 측정 실행이 된다
