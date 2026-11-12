# 24. S12 검색 시간을 1초 아래로 줄인다

## id
24

## title
준비 상태 검사와 벡터 읽기를 파일이 바뀔 때만 다시 계산한다

## goal
한 프로세스에서 검색 p95가 층1 측정용 Graph Home 기준 1초 이하다(목표8). 결과와 순서는 그대로다. spec 4.2.6, 결정15.

## files
(경로는 코드에서 확인함: 2026-11-12 프로파일)
- packages/vector-search/src/vector_search/sqlite_reader.py
- packages/vector-search/tests/ (읽기 캐시 테스트)
- src/vault_graph/operation/readiness/search_readiness_service.py
- src/vault_graph/interface/composition/read_only_service_factory.py
- tests/test_search_readiness_cache.py (신규)
- src/vault_graph/storage/local/sqlite_metadata_store.py (좁은 읽기 두 개, 색인 두 개)
- src/vault_graph/retrieval/search/evidence_result_assembly.py, context_expansion.py
- src/vault_graph/storage/interfaces/keyword_index.py, storage/local/sqlite_keyword_index.py, retrieval/search/retrieval_service.py
- tests/test_narrow_metadata_reads.py (신규), tests/test_keyword_field_weights.py
- tests/test_graph_readiness_batch.py (참고 질의가 스캔 순서에 기대던 것을 MIN()으로 고정)

## blockers
없음

## acceptance
A-15

## checks
- `uv run --python 3.12 --all-packages --all-extras pytest -q packages/vector-search/tests tests/test_search_readiness_cache.py`
- `uv run --python 3.12 --all-packages --all-extras ruff check src tests packages`
- `uv run --python 3.12 --all-packages --all-extras mypy src`
- 층1·층2 평가를 다시 돌려 문항별 순위를 기준값과 비교한다.

## done-when
- [x] 같은 파일에서 두 번째 검색은 벡터 목록과 조각을 다시 읽지 않는다.
- [x] SQLite 파일이나 `-wal` 파일이 바뀌면 다음 검색이 다시 읽는다.
- [x] 층1 p95가 1초 이하이고 층1·층2 문항별 순위가 기준값과 같다.

## 결과 (2026-11-12)

- 층1 192문항: p50 28.6초, p95 32.5초에서 p50 0.13초, p95 0.30초로 줄었다. evidence 모드 p95 0.32초, knowledge 모드 p95 0.15초.
- 층1 222문항과 층2 210문항 모두 문항별 순위(키워드, 벡터, 합친 순위, 문서 순위, 최종 순위)가 기준값과 같다.
