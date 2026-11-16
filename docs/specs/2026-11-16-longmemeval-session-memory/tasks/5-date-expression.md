# 5. date-expression

## id
5

## title
날짜 인자 검증과 `--when` 고정 규칙 해석기를 만든다

## goal
영어·한국어 날짜 표현을 오늘 기준 범위로 푸는 순수 함수를 둔다. CLI와 측정 도구가 같이 쓰고 모델은 부르지 않는다. Intent 2(날짜로 좁히기)를 맡는다.

## units
D13, D14, F5, A8, A10

## files
- src/vault_graph/retrieval/search/date_expression.py
- tests/test_date_expression.py

## blockers
1, 2, 3

## checks
- tests/test_date_expression.py

## done-when
- [ ] `resolve_date_expression(text, today)`가 영어 다섯 종류와 한국어 "지난주", "5월에", "N일 전", "지난달"을 푼다
- [ ] `YYYY-MM-DD` 인자 검증과 `since` > `until` 검사가 있다
- [ ] 질의 본문은 읽지 않고, 풀지 못하면 오류를 낸다
- [ ] 해석 중 하위 프로세스와 네트워크 호출이 없다는 시험이 있다
- [ ] 파일이 `retrieval/search/`(M05)에 있고 `tests/test_feature_import_direction.py`의 방향 표를 어기지 않는다
