# 9. S4b LongMemEval 기준값 파일 [사람 필요]

## id
9

## title
층3(LongMemEval) 기준 점수 파일

## goal
층3 기준 점수를 저장소에 고정해 이후 변경을 비교할 수 있다. 의도1을 담당한다. 사람이 데이터 내려받기와 전체 실행 확인을 맡는다.

## files
- tests/fixtures/longmemeval_baseline.json (신규)
- tests/test_longmemeval_baseline.py (신규)

## blockers
8

## acceptance
A-6

## checks
- `uv run --python 3.12 pytest -q tests/test_longmemeval_baseline.py`
- 비교 명령으로 기준값 자기 자신과 비교하면 차이 0
- `uv run --python 3.12 ruff check src tests`

## done-when
- [x] 데이터 내려받기와 전체(또는 표본) 실행을 사람이 확인했다.
- [x] 기준값 파일에 데이터 버전, 문항 수, 설정, 커밋이 있다.
- [x] 목표9 기준 숫자가 기록됐다.

## 결과 (2026-11-12)
- 고정 표본 150문항, 커밋 `aca3188`, 실패 0. recall_all@5 0.78, recall_any@5 0.99.
- 놓친 33문항은 모두 temporal-reasoning(0.68)과 multi-session(0.53)이다. 다른 네 종류는 1.00이다.
- 문항당 23.8초(색인 17.0초). 470문항은 약 3.1시간이라 결정10에 따라 150문항으로 정했다.
- 데이터 출처와 sha256, 문항 수, 설정, 커밋을 사용자가 확인했다.
