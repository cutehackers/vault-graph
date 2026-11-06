## id
32

## title
S10d 정리 꾸러미 2: 병합·폐기 후보와 composition 합치기

## goal
후보가 네 종류(brief는 #41)로 완성되고 비교 재료가 폐기 표시와 함께 나온다. (Intent 6, 8)

## spec
§4.4.4 병합·폐기 후보, §4.4.12 composition

## acceptance
A-22(병합·폐기), A-39(비교 재료), A-25(자동 폐기 없음)

## files
- src/vault_graph/context/memory/memory_candidates.py
- src/vault_graph/interface/composition/memory_candidate_sources.py (신규)
- tests/test_memory_candidates_merge_retire.py (신규)

## blockers
1, 28, 29

## checks
pytest tests/test_memory_candidates_merge_retire.py tests/test_memory_candidates_l1_session.py -q

## wave
10

## done-when
- [ ] 병합 후보(임베딩 유사 쌍)와 폐기 후보 (1)(근거 코드 경로 소멸), (2)(90일 주입만·열람 0)가 나온다
- [ ] 사용 기록을 지우면 (2)만 사라지고, 점수가 높아도 Vault 파일은 바뀌지 않는다
- [ ] 비교 재료가 5개 이하이고 폐기 페이지는 "폐기됨: <이유>" 표시와 함께 나온다
- [ ] M10이 M11을 가져오지 않는다(가져오기 방향 테스트)
- [ ] vault-graph pytest 전체 통과, 독립 커밋

## notes
병합 유사도 임계값은 S11 평가(#40)로 정하므로 여기서는 설정 가능한 값으로 둔다. `SimilarPageFinder`의 실제 구현이 `include_retired` 검색(#29)을 쓴다.
