## id

10

## title

보완7 남은 순환 3종(발견8-b, 8-c, 8-d)을 끊는다

## goal

모듈 단위 순환이 0건이 되고, 공개 가져오기 경로는 유지된다 (VG-MOD DEP-03/04 취지).

## files

- `src/vault_graph/retrieval/search/__init__.py`
- `src/vault_graph/operation/scope/catalog_service.py`
- `src/vault_graph/indexing/ingestion/document_authority.py`
- `src/vault_graph/indexing/ingestion/document_normalizer.py`
- `src/vault_graph/interface/mcp/` 리소스 리더 3개 (`graph_resource_reader.py`, `metadata_resource_reader.py`, `mcp_resources.py`, 구현 시 확인)
- `tests/test_feature_import_direction.py` (순환 0건 검사 추가)

## blockers

2

## acceptance

A-20

## checks

- `uv run --python 3.12 --all-packages --all-extras pytest -q tests/test_feature_import_direction.py tests/test_mcp_import_boundaries.py tests/test_retrieval_import_boundaries.py`
- CI 검증 세 명령 (작업 1의 checks와 같음)

## done-when

- [ ] 모듈 단위 순환이 0건이다
- [ ] 공개 가져오기 경로가 같다
- [ ] `tests/test_feature_import_direction.py` 예외 목록에서 발견8-b, 8-c, 8-d가 빠졌다
