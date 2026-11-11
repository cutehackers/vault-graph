# 4. S2b 평가 실행기

## id
4

## title
한 프로세스에서 질문 세트를 돌려 종류별 점수와 손실 분류표를 내는 평가 실행기

## goal
명령 한 번으로 질문 세트 전체를 한 프로세스에서 돌려 종류별 점수와 손실 분류표를 얻는다. 의도1(평가를 믿을 수 있게 만든다)을 담당한다. 첫 PR 범위에 든다.

## files
- tests/benchmarks/evaluate_search.py (신규)
- tests/benchmarks/eval_scoring.py (신규)
- tests/benchmarks/eval_dataset.py (신규, 질문 세트 형식과 로더)
- tests/test_evaluate_search_tool.py (신규)

## blockers
3

## acceptance
A-3

## checks
- `uv run --python 3.12 pytest -q tests/test_evaluate_search_tool.py tests/test_measure_session_recall_tool.py tests/test_measure_memory_recall_tool.py`
- 합성 미니 Vault로 한 번 실행해 출력 확인
- `uv run --python 3.12 ruff check src tests`
- `uv run --python 3.12 mypy src tests`

## done-when
- [ ] 종류별 recall@5, recall@10, MRR, 적중/순위 손실/후보 손실 분류표, 검색 시간 p50·p95를 낸다.
- [ ] 새 Graph Home이나 복사본에서만 돌고 사용 기록을 남기지 않는다.
- [ ] 층1 결과를 저장소 안 경로에 쓰려 하면 거절한다(`_require_outside_repository` 규칙 유지).
- [ ] 기존 두 측정 도구의 채점 규칙을 그대로 쓴다.
- [ ] 개발용·시험용 분할 필드를 읽는다.
