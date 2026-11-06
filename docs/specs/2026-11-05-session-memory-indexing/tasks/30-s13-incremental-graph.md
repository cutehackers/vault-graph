## id
30

## title
S13 바뀐 문서 단위 그래프 갱신

## goal
문서 5개가 바뀌어도 엔티티 25,998개를 다시 쓰지 않는다. (Intent 5)

## spec
§4.3.3 셋째, 위험B7

## acceptance
A-19(코드 부분)

## files
- src/vault_graph/indexing/graph_indexer.py
- src/vault_graph/storage/local/sqlite_graph_store.py
- tests/test_graph_incremental_equivalence.py (신규)

## blockers
1, 3, 4, 24 (24는 승인된 결정2로 추가한 blocker)

## checks
pytest tests/test_graph_incremental_equivalence.py tests/test_graph_indexer.py tests/test_graph_projection.py -q

## wave
9

## done-when
- [ ] 링크를 거는 문서, 받는 문서, `supersedes`로 family가 바뀌는 문서 각각에서 증분 결과의 엔티티·관계·근거 행 집합이 full run과 같다
- [ ] 같지 않으면 합치지 않는다는 조건이 테스트로 막혀 있다
- [ ] vault-graph pytest 전체 통과, 독립 커밋

## notes
spec의 선행은 S3뿐이나 §4.3.3이 "마지막 코드 묶음"으로 두고 S5(조각 id 변경)가 끝난 뒤 full run과 비교해야 의미가 있어 #24를 더했다.
