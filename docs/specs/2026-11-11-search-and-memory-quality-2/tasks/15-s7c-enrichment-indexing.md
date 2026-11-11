# 15. S7c 페이지 보강 필드 색인 (방안B)

## id
15

## title
summary와 aliases를 페이지 카드 임베딩과 키워드 표에 넣는다

## goal
보강 필드가 검색 후보에 반영된다. 의도2·3을 담당한다.

## files
- src/vault_graph/indexing/ingestion/wiki_page_chunker.py
- src/vault_graph/storage/local/sqlite_keyword_index.py
- tests/test_wiki_page_chunker.py
- tests/test_keyword_index_enrichment.py (신규)

## blockers
10

## acceptance
A-9 (색인 반영), A-10의 전제

## checks
- `uv run --python 3.12 pytest -q tests/test_wiki_page_chunker.py tests/test_keyword_index_enrichment.py tests/test_chunker_selection.py`
- `uv run --python 3.12 ruff check src tests`
- `uv run --python 3.12 mypy src tests`

## done-when
- [ ] 카드 임베딩 입력과 키워드 표 title·aliases 열에 summary와 aliases가 들어간다.
- [ ] 필드가 없는 페이지의 색인 결과는 이전과 같다.
- [ ] questions 필드는 넣지 않는다(결정11).
