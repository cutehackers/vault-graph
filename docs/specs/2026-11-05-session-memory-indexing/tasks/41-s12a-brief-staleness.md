## id
41

## title
S12a brief 갱신 규칙: `brief_staleness`, brief 갱신 후보, 구획D 안내 줄

## goal
프로젝트 brief를 언제 갱신할지 vg가 결정적으로 알려 준다. brief 본문은 쓰지 않는다. (Intent 6)

## spec
§4.4.7, §4.4.4 brief 후보

## acceptance
A-35, A-27(brief 본문 비생성 검색)

## files
- src/vault_graph/context/memory/brief.py (신규)
- src/vault_graph/context/memory/memory_candidates.py
- src/vault_graph/context/pack/recall_backlog.py
- src/vault_graph/context/pack/recall.py
- tests/test_brief_staleness.py (신규)
- tests/test_brief_candidate_recall.py (신규)

## blockers
1, 40, 요청S9(외부, E2E는 #43)

## checks
pytest tests/test_brief_staleness.py tests/test_brief_candidate_recall.py -q

## wave
14

## done-when
- [ ] 표 테스트(brief 없음 4개·5개, brief 뒤 4개·5개, 대체·폐기·다른 프로젝트 결정 미포함)가 통과한다
- [ ] 구획D 줄이 한 번 나오고 후보 키가 `brief:<project>:<해시>`이며, 새 결정이 하나 생기면 키가 바뀐다
- [ ] vg가 brief를 쓰는 코드 경로가 없다
- [ ] vault-graph pytest 전체 통과, 독립 커밋

## notes
요청S9 없이 가짜 Vault로 단위 테스트할 수 있다. 기준값 5는 [가정]이다(위험D9).
