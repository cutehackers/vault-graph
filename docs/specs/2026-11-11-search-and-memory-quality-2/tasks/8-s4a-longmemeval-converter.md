# 8. S4a LongMemEval 변환기와 20문항 시간 측정

## id
8

## title
LongMemEval-S 변환기와 실행기, 20문항 시간 측정

## goal
LongMemEval-S의 검색 단계를 로컬에서 돌릴 변환기가 생긴다. 의도1(외부 기준)을 담당한다. 첫 PR 범위에 든다.

## files
- tests/benchmarks/longmemeval_convert.py (신규)
- tests/benchmarks/longmemeval_run.py (신규)
- tests/test_longmemeval_convert_tool.py (신규)

## blockers
4

## acceptance
A-6 (변환기와 실행 부분)

## checks
- `uv run --python 3.12 pytest -q tests/test_longmemeval_convert_tool.py`
- 20문항 시험 실행으로 문항당 시간 측정
- `uv run --python 3.12 ruff check src tests`
- `uv run --python 3.12 mypy src tests`

## done-when
- [ ] 시작 전에 LongMemEval-V2가 코딩 에이전트에 더 맞는지 확인해 근거를 남겼다.
- [ ] 대화 기록 묶음을 `vg-session-jsonl/1`로 바꾸고 Vault 도구 `sessions capture --normalized`가 임시 Vault에 쓴다.
- [ ] 등록된 Vault를 대상으로 받으면 거절한다.
- [ ] `--mode evidence` 상위 5개가 `answer_session_ids`를 모두 포함하는지 센다.
- [x] 20문항 문항당 시간을 재서 전체 470문항 또는 고정 표본 150문항을 정했다(결정10).
