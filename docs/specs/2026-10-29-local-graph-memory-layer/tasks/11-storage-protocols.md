## id

11

## title

보완4 저장소 구체 클래스를 Protocol과 주입으로 바꾼다

## goal

기능 코드가 `storage.local`을 가져오지 않는다. 1차-4의 새 서비스가 따를 주입 형태가 먼저 생긴다 (보완 계획 표의 "1차-4 전 권장").

## files

- `src/vault_graph/storage/interfaces/` (새 Protocol 파일, `LocalVectorStatusStore`, `LocalGraphStatusStore`, `SQLiteMetadataStore`, `ChromaVectorStore` 중 기능 코드가 쓰는 메서드만)
- `src/vault_graph/indexing/index_service.py`
- `src/vault_graph/operation/diagnostics/index_status_reader.py`
- `src/vault_graph/operation/diagnostics/projection_hygiene_service.py`
- `src/vault_graph/interface/composition/local_index_service_factory.py`
- `src/vault_graph/interface/composition/read_only_service_factory.py`
- `tests/test_feature_import_direction.py`

## blockers

2

## acceptance

A-20

## checks

- `uv run --python 3.12 --all-packages --all-extras pytest -q tests/test_feature_import_direction.py tests/test_foundation_import_boundaries.py`
- CI 검증 세 명령 (작업 1의 checks와 같음)

## done-when

- [ ] 기능 영역에서 `storage.local`을 가져오는 곳이 0건이다
- [ ] 구체 클래스 생성은 composition에만 있다
- [ ] `tests/test_feature_import_direction.py` 예외 목록에서 발견7이 빠졌다
