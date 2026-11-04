# 저장소의 임베딩 모델 흐름

조사일: 2026-11-04. 기준 커밋 `44dbf86`. 모든 줄 번호는 이 커밋의 줄이다. 단, `~/llm/models`로 바꾼 미커밋 변경은 반영된 상태다.

## 1. 모델과 폴더를 정하는 곳

- 기본 모델 스펙은 `src/vault_graph/interface/composition/adapters/text_embeddings.py:17-25`에 상수로 있다. 모델 이름, 버전, 차원(384), `spec_version`, Hugging Face 저장소 ID가 여기 있다.
- 설정 클래스 `FastEmbedTextEmbeddingsConfig`는 `:33-60`에 있다. `_config_for_local_files_only`(`:123-136`)가 필드를 하나씩 다시 복사하므로, 필드를 새로 만들면 여기에도 넣어야 한다.
- 모델을 받을 때는 `snapshot_download(repo_id, revision=model_version, ...)`를 부른다(`:139-152`). 모델을 읽을 때는 `fastembed.TextEmbedding(model_name, specific_model_path=...)`를 부른다(`:155-171`). 경고 필터(`:161-164`)는 MiniLM에만 맞게 적혀 있다.
- 모델 폴더 기본값은 `CatalogService.__init__`(`src/vault_graph/operation/scope/catalog_service.py:29-33`)에 있다. 이 값을 넘기는 호출은 하나도 없다.
- 설정 객체를 만드는 곳은 다섯 군데다. 다섯 곳 모두 기본 모델을 쓰고 `cache_dir`와 `local_files_only`만 다르다.
  - `cli/main.py:305-315`
  - `local_index_service_factory.py:338-339`
  - `read_only_service_factory.py:437-448`
  - `recall_index_refresh.py:396-405`
- 모델이나 폴더를 바꾸는 설정 파일, 환경 변수, CLI 옵션은 없다. `vg config` 명령도 없다.

## 2. 모델을 바꾸면 기존 벡터는 어떻게 되나

- Chroma 컬렉션 이름에 모델 스펙 네 필드의 해시가 들어간다(`storage/local/vector_store_adapter.py:145-150`). 그래서 검색은 지금 스펙의 컬렉션만 본다.
- 색인은 `space_id`가 다른 기존 레코드를 삭제 대상으로, 모든 조각을 새로 넣을 대상으로 잡는다(`packages/vector-index/src/vector_index/indexing.py:106-108`). 따라서 `vg index` 한 번이면 전부 다시 임베딩된다.
- 다시 임베딩하기 전까지는 벡터가 오래된 것으로 표시된다(stale). 검색은 그 범위의 벡터를 건너뛰고 키워드 검색만 한다(`retrieval/search/retrieval_service.py:264`). 이때 `vector_stale` 경고를 낸다.
- 모델 파일이 없으면 `embedding_model_unavailable` 경고를 낸다(`retrieval_service.py:339-346`).
- 세션 시작 훅은 벡터가 오래된 것을 보면 백그라운드에서 `vg index`를 띄운다(`recall_index_refresh.py:354-393`). 이 실행은 모델이 없으면 내려받는다.
- 비워진 예전 컬렉션은 지우지 않는다. `chroma_store.py`에 `delete_collection`이 없다.

## 3. 설정을 둘 곳

- `configs/vaults.yaml`은 저장할 때 모르는 키를 지운다(`operation/scope/vault_catalog.py:89-127`). 그래서 임베딩 설정을 여기에 두면 안 된다.
- 작은 JSON 설정을 원자적으로 쓰는 선례는 `interface/composition/graph_store_factory.py:48-60`의 `graph/backend.json`이다.
- Graph Home의 등록과 경로는 M01 `operation/scope/`가 맡는다. 이 영역은 다른 기능 영역을 가져올 수 없다(`docs/ARCHITECTURE.md:199`).

## 4. 지켜야 할 모듈 규칙

- `text_embeddings`, `vector_search`, `vector_index` 패키지는 `vault_graph`를 가져오지 않는다(`docs/SPEC.md:336-337`, `docs/ARCHITECTURE.md:180`). 캐시 정책과 다운로드 정책은 일반 패키지가 맡지 않는다(`packages/text-embeddings/README.md:3`).
- 구체 provider는 `interface/composition/`에서만 만들어 주입한다(`docs/ARCHITECTURE.md:188`).
- 읽기 경로는 아무것도 쓰지 않고, 모델도 내려받지 않는다(`docs/ARCHITECTURE.md:240`). 모델을 받을 수 있는 것은 `setup`, `index`, `watch`뿐이다.
- 다른 모델로 몰래 바꾸지 않는다. 스펙이 바뀌면 벡터를 오래된 것으로 표시한다(`docs/DECISIONS.md:538-541`).
- 테스트는 모델을 내려받지 않는다(`docs/DECISIONS.md:330-333`).
- 경계를 지키는지 확인하는 테스트는 다음과 같다.
  - `tests/test_feature_import_direction.py`
  - `tests/test_module_import_cycles.py`
  - `tests/test_functional_module_boundaries.py`
  - `tests/test_read_only_boundary.py`
  - `tests/test_search_read_only_boundary.py`
  - `tests/test_fastembed_text_embeddings.py`: 기본 상수를 확인한다(`:12-33`).

## 5. 질의와 문서 접두어

- 질의와 문서가 같은 `embed()`를 쓴다. 질의는 `retrieval_service.py:261`에서, 문서는 `vector_index_adapter.py:130,206`에서 부른다.
- e5 계열은 `query:`/`passage:` 접두어가 필요하다. 지금은 이 둘을 구분할 방법이 없다.
- `model_space_id(spec, preprocessing_id=...)`(`packages/vector-index/src/vector_index/indexing.py:124-126`)라는 연결 지점은 이미 있다. 하지만 컬렉션 이름과 `stable_vector_id`는 스펙 네 필드만 해시한다. 그래서 접두어 정책은 `spec_version`에 넣어야 바뀌었을 때 벡터가 오래된 것으로 표시된다.

## 6. 사용자 문서

- README는 "첫 색인 때 고정된 로컬 모델을 받아 Vault 밖에 캐시한다"(`README.md:123-127`)라고만 적는다. 모델 이름, 폴더, 바꾸는 방법, 오프라인 동작은 적혀 있지 않다.
- `docs/FEATURES.md:314-317`: `vg status`가 모델 스펙과 캐시 상태를 보여 준다.
