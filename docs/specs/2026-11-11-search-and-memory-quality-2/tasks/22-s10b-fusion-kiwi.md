# 22. S10b 합치는 방식과 한국어 형태소 (방안D, 조건부) [사람 필요]

## id
22

## title
Kiwi 형태소 열과 점수 결합 방식을 재고 이득이 있을 때만 넣는다

## goal
측정으로 이득이 확인된 변경만 검색에 넣는다. 의도2를 담당한다. 사람이 채택 여부를 승인한다.

## files
- src/vault_graph/retrieval/search/candidate_ranking.py
- src/vault_graph/retrieval/search/retrieval_service.py
- src/vault_graph/storage/local/sqlite_keyword_index.py
- tests/test_fusion_variants.py (신규)
- docs/design/reports/2026-11-fusion-kiwi-measurement.md (신규)

## blockers
10, 21

## acceptance
A-13

## checks
- 평가 실행기와 비교 명령으로 층1 시험용과 층3 확인
- `uv run --python 3.12 pytest -q tests/test_fusion_variants.py tests/test_retrieval_service_search.py`
- `uv run --python 3.12 ruff check src tests`
- `uv run --python 3.12 mypy src tests`

## done-when
- [ ] 조사 문서 `2026-11-05-session-memory-indexing/research/search-quality-external.md`의 권고7(Kiwi), 권고8(점수 결합)을 평가 도구로 쟀다.
- [ ] 좋아진 문항이 나빠진 문항보다 많고 어느 종류도 떨어지지 않을 때만 넣는다. 아니면 닫고 결과만 보고서에 남긴다.
- [ ] 목표8을 만족한다.
