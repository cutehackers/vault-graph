# 작업 6. longmemeval_run에 재정렬 preset 인자 추가

## id

6

## title

`longmemeval_run`에 재정렬 preset 인자 추가

## goal

LongMemEval을 재정렬 켜짐과 꺼짐으로 돌려 비교할 수 있다. 인자가 없으면 지금과 같다(Intent 1, 3).

## units

D15, A13

## files

- `tests/benchmarks/longmemeval_run.py`
- `tests/test_longmemeval_run_reranker.py`

## blockers

1, 3

## checks

- `tests/test_longmemeval_run_reranker.py`

## done-when

- [ ] `longmemeval_run`에 preset 선택 인자가 생기고, 주면 문항마다 만든 Graph Home에 `configs/reranker.json`이 생긴다.
- [ ] 인자가 없으면 `configs/reranker.json`이 생기지 않고 기존 동작과 같다.
- [ ] `evaluate_search`와 `compare_search_eval`은 바뀌지 않았다. 층1·층2는 측정용 Graph Home 설정만 바꿔 비교한다.
