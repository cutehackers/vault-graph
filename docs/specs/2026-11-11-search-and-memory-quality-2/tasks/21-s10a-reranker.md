# 21. S10a 로컬 재순위 모델 (방안C, 조건부) [사람 필요]

## id
21

## title
조건을 만족할 때만 로컬 교차 인코더 재순위를 넣는다

## goal
순위 손실이 많을 때만 상위 문서를 다시 정렬한다. 의도2를 담당한다. 사람이 이 Mac의 시간·메모리 측정을 확인하고 채택을 승인한다.

## files
- src/vault_graph/retrieval/search/reranker.py (신규)
- src/vault_graph/retrieval/search/retrieval_service.py
- tests/test_reranker.py (신규)
- docs/design/reports/2026-11-reranker-measurement.md (신규)

## blockers
10, 11

## acceptance
A-13

## checks
- `uv run --python 3.12 pytest -q tests/test_reranker.py tests/test_retrieval_service_search.py`
- 이 Mac에서 검색 시간 p95와 메모리 측정
- `uv run --python 3.12 ruff check src tests`
- `uv run --python 3.12 mypy src tests`

## done-when
- [ ] 작업 10 보고서에서 순위 손실이 실패의 절반 이상일 때만 진행한다. 아니면 이 작업을 닫고 사유를 남긴다.
- [ ] `bge-reranker-v2-m3`(Apache-2.0)를 직접 등록하고 채택 전 시간과 메모리를 쟀다.
- [ ] 모델 파일이 없거나 읽기에 실패하면 재순위 없이 답하고 경고를 넣는다.
- [ ] 채택 규칙과 목표8(p95 1초 이하)을 만족한 측정 결과가 있을 때만 기본 경로에 넣는다.
