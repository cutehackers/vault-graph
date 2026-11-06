## id
45

## title
S14b `docs/ARCHITECTURE.md`와 `docs/DECISIONS.md` 반영

## goal
M19와 새 파일 위치, 사용자가 답한 결정이 기록된다. (Intent 2, 6)

## spec
§9.1, §9.3, §4.6 모듈 설명

## acceptance
A-33(나머지), A-32(영역 테스트)

## files
- docs/ARCHITECTURE.md
- docs/DECISIONS.md

## blockers
1, 5, 36, 42

## checks
pytest tests/test_context_pack_docs_contract.py tests/test_feature_import_direction.py tests/test_module_import_cycles.py -q

## wave
15

## done-when
- [ ] ARCHITECTURE §1·§3.1·§4에 M19와 새 파일 위치가 있다
- [ ] 9.1·9.3 답과 승인된 [가정] 결정이 `Question`, `Decision`, `Reason`, `Implications` 형식으로 `docs/DECISIONS.md`에 있다
- [ ] vault-graph pytest 전체 통과, 독립 커밋

## notes
없음.
