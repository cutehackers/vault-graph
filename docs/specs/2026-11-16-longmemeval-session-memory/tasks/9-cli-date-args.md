# 9. cli-date-args

## id
9

## title
`vg search`에 `--since`·`--until`·`--when`을 더한다

## goal
CLI도 날짜로 좁힐 수 있다. Intent 2를 맡는다.

## units
D10, D13, F5, A8

## files
- src/vault_graph/interface/cli/main.py
- tests/test_cli_search.py

## blockers
5, 7

## checks
- tests/test_cli_search.py

## done-when
- [ ] `--since`, `--until`이 한쪽만 줘도 동작한다
- [ ] `--when`은 5번 task 해석기로 범위가 된다
- [ ] 형식 오류, `since` > `until`, 못 푸는 `--when`, `--when`과 `--since`·`--until` 동시 사용은 종료 코드 2와 이유 한 줄이다
- [ ] 범위 없이 검색하는 경로가 없다
