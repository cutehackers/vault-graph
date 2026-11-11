# 7. S3b 층1 질문 세트와 기준 숫자 [사람 필요]

## id
7

## title
층1 질문 세트(저장소 밖)와 기준 숫자(저장소 안)

## goal
실제 Vault 기준 주 지표 질문 세트와 기준 숫자를 만든다. 의도1을 담당한다. 사람이 질문 생성 에이전트 실행, 검수, Vault 선택을 맡는다.

## files
- tests/fixtures/eval_layer1_baseline.json (신규, 숫자만. 질문 원문과 문항별 결과는 저장소 밖에 둔다)
- tests/test_eval_layer1_baseline.py (신규)

## blockers
4

## acceptance
A-5 (층1 부분)

## checks
- `uv run --python 3.12 pytest -q tests/test_eval_layer1_baseline.py`
- 평가 실행기를 층1에 돌려 종류별 문항 수 확인
- 저장소 안에 질문 원문이 없는지 grep으로 확인
- `uv run --python 3.12 ruff check src tests`

## done-when
- [ ] 질문은 검색 도구를 쓰지 않는 별도 에이전트가 만들었고 사람이 검수했다(2026-11-07 결정).
- [ ] 종류마다 30문항 이상이고 개발용·시험용으로 나뉘어 있다.
- [ ] 저장소에는 숫자만 있고 질문 원문이 없다.
- [ ] 기준값을 재서 spec 2.1 목표 숫자를 확정할 근거가 나왔다(결정8).
