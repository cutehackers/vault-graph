# 5. S2c 기준값 비교 명령

## id
5

## title
기준값과 새 결과를 비교하는 명령

## goal
변경 전후를 비교해 종류별 차이와 좋아진·나빠진 문항 수를 얻는다. 의도1을 담당한다. 첫 PR 범위에 든다.

## files
- tests/benchmarks/compare_search_eval.py (신규)
- tests/test_compare_search_eval_tool.py (신규)

## blockers
4

## acceptance
A-4

## checks
- `uv run --python 3.12 pytest -q tests/test_compare_search_eval_tool.py`
- `uv run --python 3.12 ruff check src tests`
- `uv run --python 3.12 mypy src tests`

## done-when
- [ ] 기준값 파일과 새 결과를 받아 종류별 차이를 낸다.
- [ ] 좋아진 문항 N개, 나빠진 문항 M개를 낸다.
- [ ] 채택 규칙(spec 4.1.3) 판정 요약을 PR 본문에 붙일 수 있는 형태로 낸다.
