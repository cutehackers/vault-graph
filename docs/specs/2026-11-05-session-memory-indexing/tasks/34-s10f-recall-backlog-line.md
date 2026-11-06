## id
34

## title
S10f 정리 대기 줄 `recall_backlog.py`

## goal
세션 시작에 밀린 정리 양이 한 줄로 보인다. 훅 안에서는 정리하지 않는다. (Intent 6)

## spec
§4.4.6 정리 대기 줄, §4.4.4 시작 방법

## acceptance
A-26(정리 대기 줄)

## files
- src/vault_graph/context/pack/recall_backlog.py (신규)
- src/vault_graph/context/pack/recall.py
- tests/test_recall_backlog.py (신규)

## blockers
1, 18, 28

## checks
pytest tests/test_recall_backlog.py tests/test_recall_budget.py -q

## wave
10

## done-when
- [ ] 후보가 있을 때만 줄이 있고 수가 `list_memory_candidates`와 같다
- [ ] 둘 다 0이면 줄이 없고, 시간 한도를 넘으면 줄을 빼고 경고 한 줄이다
- [ ] vault-graph pytest 전체 통과, 독립 커밋

## notes
세는 규칙은 L1 노트와 세션 교환 두 종류만이다.
