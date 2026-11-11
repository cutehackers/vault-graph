# 18. S8b 기억 품질 지표7·지표8

## id
18

## title
기억 품질 측정 도구에 지표7과 지표8을 더한다

## goal
summary 보유 비율과 `fetched` 사건이 있는 세션 비율이 측정 도구에 나온다. 의도3을 담당한다.

## files
- tests/benchmarks/measure_memory_recall.py
- tests/test_measure_memory_recall_tool.py

## blockers
13, 15

## acceptance
A-11 (지표 부분)

## checks
- `uv run --python 3.12 pytest -q tests/test_measure_memory_recall_tool.py`
- `uv run --python 3.12 ruff check src tests`
- `uv run --python 3.12 mypy src tests`

## done-when
- [ ] 지표7(summary 있는 기억 페이지 비율)과 지표8(`fetched` 사건이 있는 세션 비율)을 낸다.
- [ ] 기존 지표1~6 출력은 그대로다.
