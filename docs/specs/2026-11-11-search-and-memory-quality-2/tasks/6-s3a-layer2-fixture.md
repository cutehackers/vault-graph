# 6. S3a 층2 가상 Vault와 질문 세트 [사람 필요]

## id
6

## title
층2 가상 Vault와 질문 세트 (질문은 검색 도구 없는 별도 에이전트가 만든다)

## goal
누구나 저장소에서 같은 숫자를 다시 낼 수 있다. 의도1을 담당한다. 사람이 질문 생성 에이전트 실행과 검수를 맡는다.

## files
- tests/fixtures/eval_layer2/ 아래 가상 Vault 파일과 질문 JSON (신규)
- tests/fixtures/eval_layer2_baseline.json (신규)
- tests/test_eval_layer2_fixture.py (신규)

## blockers
4

## acceptance
A-5 (층2 부분)

## checks
- `uv run --python 3.12 pytest -q tests/test_eval_layer2_fixture.py`
- 평가 실행기를 층2에 돌려 종류별 문항 수 확인
- `uv run --python 3.12 ruff check src tests`

## done-when
- [ ] 한국어·영어 코딩 기억으로 새로 지어낸 가상 Vault다(결정9). 실제 Vault를 가공하지 않았다.
- [ ] 질문은 검색 도구를 쓰지 않는 별도 에이전트가 만들었고 사람이 검수했다.
- [ ] 종류(제목, 의역, 결정, 방법, 세션, 답 없음)마다 30문항 이상이다.
- [ ] 개발용·시험용으로 반씩 나뉘어 있다.
- [ ] 기준 점수 파일이 있다.
