## id
23

## title
S5d 교환 메타 키워드(`keyword_metadata`)와 부모 단위 결과 묶기

## goal
파일·명령·오류로 교환을 찾고, 결과가 교환 하나에 한 건으로 나온다. (Intent 3, 4)

## spec
§4.2.6-6·8, §4.2.9, 위험A5

## acceptance
A-6, A-7

## files
- src/vault_graph/storage/local/sqlite_keyword_index.py
- src/vault_graph/retrieval/search/evidence_result_assembly.py
- tests/test_keyword_metadata_search.py (신규)
- tests/test_parent_key_result_grouping.py (신규)

## blockers
1, 19

## checks
pytest tests/test_keyword_metadata_search.py tests/test_parent_key_result_grouping.py tests/test_sqlite_keyword_index.py tests/test_keyword_index_contract.py -q

## wave
7

## done-when
- [ ] 고친 파일 경로로 `vg search`하면 교환이 상위 5개에 있고, 그 경로가 `text`와 임베딩 입력에 없다
- [ ] `vg search "Bash"`에 도구 이름만 있는 조각이 없다
- [ ] 한 교환의 창 셋이 모두 맞아도 결과는 한 번이고 위치가 교환 전체 줄 범위이며, MCP 리소스로 열면 사람 턴과 답이 함께 나온다
- [ ] 일반 문서 검색 결과는 `abc77e7`과 같다
- [ ] vault-graph pytest 전체 통과, 독립 커밋

## notes
시작 때 키워드 행 쓰기 코드를 읽어 FTS 열 추가 없이 가능한지 확인한다(위험A5). 행 쓰기가 다른 파일이면 그 파일을 이 task의 files에 추가한다. 같은 wave의 #21, #22와 파일이 겹치지 않는다.
