# Spec: 임베딩 모델 선택과 관리

- task: 20261104-task-0aca
- spec id: 2026-11-04-embedding-model-selection
- base: `feat/jh/embedding-model-config` @ 44dbf86 (+ `~/llm/models` 미커밋 변경 2건)

## 1. Problem

임베딩 모델이 코드 상수 하나로 고정되어 있어 사용자가 모델을 고르거나 바꿀 수 없다. 그 고정 모델은 사용자의 검색 대상(한국어가 섞인 coding agent 세션 원문)에 약하고, 바꾸려 해도 코드가 그 모델 하나만 다루게 짜여 있다.

1. 문제1 모델을 고르는 방법이 없다.
   - 모델 스펙은 `src/vault_graph/interface/composition/adapters/text_embeddings.py:17-25`의 상수 `DEFAULT_FASTEMBED_MODEL_SPEC`, `FASTEMBED_ARTIFACT_REPO_ID`, `SOURCE_MODEL_REVISION`이다.
   - 설정 객체 `FastEmbedTextEmbeddingsConfig`를 만드는 곳이 다섯 군데이고, 모두 기본 모델을 쓰며 `cache_dir`와 `local_files_only`만 다르다. `interface/cli/main.py:306`, `main.py:311`, `interface/composition/local_index_service_factory.py:339`, `read_only_service_factory.py:444`, `recall_index_refresh.py:404`.
   - 모델이나 폴더를 바꾸는 설정 파일, 환경 변수, CLI 옵션이 없다.
2. 문제2 모델 폴더 기본값 `~/llm/models`가 두 곳에 따로 적혀 있다(미커밋 변경). `FastEmbedTextEmbeddingsConfig.cache_dir`(`adapters/text_embeddings.py:40`)와 `CatalogService.__init__`(`operation/scope/catalog_service.py:29-33`)다. `CatalogService`의 `embedding_cache_path` 인자를 넘기는 호출은 하나도 없다.
3. 문제3 지금 모델(paraphrase-multilingual-MiniLM-L12-v2)이 사용자 데이터에 맞지 않는다.
   - 공개 한국어 질의응답 점수(7개 과제 NDCG@10 평균)가 0.410이다. 같은 표에서 snowflake-arctic-embed-l-v2.0은 0.724, multilingual-e5-small은 0.671이다(`research/model-candidates.md` 비교 표).
   - 조각마다 앞 128토큰만 읽는다(같은 파일 "확인한 사실").
   - 사용자 Graph Home의 26,124조각 중 15,273조각이 coding agent 세션 원문이다. 영어 도구 출력·코드·경로 사이에 한국어 대화가 섞여 있고, 질문은 주로 짧은 한국어다(`research/measurement-and-data.md` "사용자 Vault 구성").
4. 문제4 질의와 문서를 구분하지 않는다. 질의는 `retrieval/search/retrieval_service.py:261`, 문서는 `indexing/vector_index_adapter.py:212`(`embed_items`)에서 같은 `embed()`를 부른다. e5 계열은 질의와 문서에, arctic-l은 질의에만 접두어 `query: `가 필요하다.
5. 문제5 모델을 읽고 받는 코드가 MiniLM 하나에 맞춰져 있다.
   - 백엔드는 `fastembed.TextEmbedding(model_name=...)`만 부른다(`adapters/text_embeddings.py:167-172`). fastembed 기본 목록 밖 모델에 필요한 `TextEmbedding.add_custom_model` 등록이 없다.
   - 경고 필터가 MiniLM 경고 문구에 맞춰져 있다(`:158-166`).
   - `snapshot_download`가 받을 파일을 제한하지 않는다(`:143-150`). 지금 받는 `qdrant/...-onnx-Q` 저장소에는 ONNX 하나뿐이라 문제가 드러나지 않았다.
6. 문제6 사용자가 이 기능을 알 수 없다. README는 "첫 색인 때 고정된 로컬 모델을 받아 Vault 밖에 캐시한다"(`README.md:123-127`)라고만 적는다. 모델 이름, 폴더, 바꾸는 법, 바꾼 뒤 검색 동작이 없다.
7. 문제7 모델을 바꾸면 예전 모델의 Chroma 컬렉션이 빈 채로 계속 남는다.
   - 컬렉션 이름은 `vault_graph_` + 스펙 네 필드 해시다(`storage/local/vector_store_adapter.py:29`, `:145-150`). 다시 임베딩하면 예전 레코드는 지워지지만(`packages/vector-search/src/vector_search/chroma_store.py:178-186`) 컬렉션은 지우지 않는다. 일반 패키지 `ChromaVectorStore`에 컬렉션을 지우는 공개 메서드가 없다(`chroma_store.py` 전체).
   - 색인은 매번 활성 세대 폴더 전체를 새 세대로 복사한 뒤 쓴다(`indexing/publication/projection_generation.py:90-98`). 그래서 빈 컬렉션도 세대마다 함께 복사된다.

확인 방법: 기준 커밋 `44dbf86`과 미커밋 변경 2건 위에서 위 파일들을 직접 읽었다. `src`에서 `FastEmbedTextEmbeddingsConfig(`, `DEFAULT_FASTEMBED_MODEL_SPEC`, `.embed(`, `transactional=`, `commit_projection(`, `import chromadb`를 검색해 생성·호출 위치를 셌다. 모델 점수·속도·사용자 데이터 구성은 `research/` 세 파일의 기록을 근거로 했고, 직접 다시 재지 않았다.

## 2. Intent

사람의 요청은 "임베딩을 하기 위한 모델을 변경수정 하고 관리하기 좋게 개선"이다. 사람이 밝힌 목적은 세 가지다. README 같은 곳에서 이 기능이 있다는 것을 알고 편하게 관리하는 것, 임베딩 성능을 자기 언어와 coding agent 세션에 맞추는 것, 자기 작업 특성에 맞는 모델을 고르는 것이다.

변경 후 성립해야 하는 것:

1. 사용자는 README 한 곳에서 쓸 수 있는 모델, 기본 모델, 모델 폴더, 모델을 바꾸는 명령, 바꾼 뒤 다시 색인되는 동안 검색이 어떻게 동작하는지 읽을 수 있다. 사람의 말로는 "사용자의 입장에서 이해하기 쉬운 설치 및 관리"다.
2. 기본 모델은 snowflake-arctic-embed-l-v2.0 int8이다. 사람은 첫 전체 재색인이 최대 약 48분 걸리고 벡터 저장소가 약 2.7배 커지는 것을 알고 이 모델을 골랐다. 이미 쓰던 Graph Home도 업그레이드하면 바로 이 모델로 바뀐다(spec gate 질문1 답).
3. 사용자에게는 "이런 유형의 작업에 가장 적합한 모델 하나"를 먼저 내세운다. 사람의 말은 "이런 유형에 작업에 가장 적합한 모델을 후보로 골라서 하나만으로 먼저 시작합니다. 위 세 개로 추가해도 무방할 듯 합니다"다. README와 `vg embedding list`는 arctic-l을 한국어와 coding agent 세션에 맞는 추천 모델 하나로 보여 주고, 나머지 둘은 대안으로 보여 준다(spec gate 질문3 답).
4. 모델을 바꾼 뒤 예전 모델의 빈 벡터 컬렉션이 디스크에 계속 쌓이지 않는다(spec gate 질문2 답).
5. 모델 파일은 `~/llm/models`에 둔다. 사람이 앞선 대화에서 정했고, 이미 받은 모델 파일도 그 폴더로 옮겨 두었다.
6. 모델을 하나 더 쓰려면 모델 목록에 항목 하나를 더하면 되고, 다른 코드를 고칠 필요가 없다. 사람의 말 "임베딩이 용이하고 쉬운 구조"를 이렇게 해석했다. [가정]
7. 바뀐 코드가 저장소의 모듈 규칙(일반 패키지는 `vault_graph`를 가져오지 않음, 구체 provider는 `interface/composition/`에서 만듦, 읽기 경로는 모델을 내려받지 않음)을 지킨다. 사람의 말로는 "모듈화된 구조에 대한 순응"이다.

## 3. Non-goals

1. 측정1(`docs/SPEC.md:171-175`)을 실행하지 않는다. 이 작업은 n차-4(`docs/SPEC.md:366`)의 모델 선택을 사람의 결정과 공개 자료로 앞당길 뿐이고, 측정으로 확인하는 일은 n차-4에 남는다.
2. 조각 크기와 조각 나누는 방식을 바꾸지 않는다.
3. 목록 밖 모델(사용자가 Hugging Face 저장소를 직접 적는 방식)을 지원하지 않는다. 모든 모델은 고정 revision을 가진 목록 항목으로만 쓴다.
4. 일반 패키지 `packages/text-embeddings`, `packages/vector-index`, `packages/vector-search`의 공개 계약을 바꾸지 않는다. 예전 컬렉션 정리도 `vault_graph` 쪽 어댑터에서 한다(4.7).
5. 모델끼리 검색 품질을 비교하는 도구를 만들지 않는다.
6. 기존 CLI 명령, MCP 도구, HTTP 응답의 인자와 필드를 지우거나 이름을 바꾸지 않는다. 새 명령 그룹 `vg embedding`만 더한다.
7. 이번 목록에는 프리셋 세 개(arctic-l, e5-small, minilm)만 넣는다. bge-m3, multilingual-e5-large, KURE 등은 넣지 않는다(결정2).
8. 아직 공개된 데이터가 남아 있는 예전 컬렉션, 예전 세대 폴더 안의 컬렉션, Chroma SQLite 파일 크기 줄이기(VACUUM)는 다루지 않는다. 정리 대상은 4.7의 조건을 모두 맞는 컬렉션뿐이다.
9. 이 저장소의 작업 트리 코드로 사용자의 실제 Graph Home(`$HOME/.vault-graph`)을 색인하지 않는다(9절 "실행 일정").

## 4. Design

핵심 계약: 사용자는 이름 붙은 모델 목록에서 모델 하나를 고르고, 그 선택은 Graph Home의 임베딩 설정 파일에 남는다. 임베딩 객체는 `interface/composition/adapters/text_embeddings.py`의 함수 하나만 만들고, 그 함수가 설정 파일을 읽어 프리셋을 고른다. 모델을 바꾸면 스펙이 바뀌므로 기존 벡터는 지금 있는 stale 처리로 오래된 것이 되고, 기존 `vg index`(또는 세션 시작 백그라운드 색인)가 다시 임베딩한다. 다시 임베딩이 성공하면 그 색인이 발행 전 새 세대에서 예전 모델의 빈 컬렉션을 지운다(4.7).

용어

- 프리셋: 모델 목록의 한 항목. 이름(예: `arctic-l`)과 그 모델을 받고 읽고 쓰는 데 필요한 값을 모두 가진다.
- 임베딩 설정 파일: `<graph-home>/configs/embedding.json`. 고른 프리셋 이름과 모델 폴더를 담는다.
- 모델 폴더: 모델 파일을 받아 두는 폴더. 기본값은 `~/llm/models`다.

### 4.1 프리셋 (`interface/composition/adapters/text_embeddings.py`)

- `@dataclass(frozen=True) class EmbeddingPreset`. 필드는 다음과 같다.
  - `name`: 사용자가 부르는 이름.
  - `model_name`, `revision`, `dimensions`, `spec_version`: `EmbeddingModelSpec`의 네 필드가 된다. `revision`이 지금의 `model_version` 자리에 들어간다.
  - `repo_id`: 내려받을 Hugging Face 저장소. `source_model_revision`: 원본 모델 출처 revision(정보용, 없으면 빈 문자열).
  - `files`: 내려받을 파일 패턴 목록. `None`이면 저장소 전체를 받는다(지금 MiniLM 동작).
  - `fastembed_registration`: `"builtin"`(fastembed 기본 목록) 또는 `"custom"`(`add_custom_model`로 등록).
  - `model_file`, `pooling`, `normalization`: `"custom"`일 때 `add_custom_model`에 넘긴다.
  - `max_tokens`, `download_mb`, `summary`: `vg embedding list`에 보여 줄 값. `summary`는 쓰임새 한 줄이다. `arctic-l`은 "추천: 한국어와 coding agent 세션", `e5-small`은 "대안: 작고 빠름", `minilm`은 "대안: 예전 기본 모델, 되돌리기용"이다.
  - `query_prefix`, `document_prefix`: 질의와 문서 앞에 붙일 문자열. 없으면 빈 문자열.
- `EMBEDDING_PRESETS: Mapping[str, EmbeddingPreset]`와 `DEFAULT_EMBEDDING_PRESET = "arctic-l"`을 같은 파일에 둔다. 모델을 더하는 일은 이 표에 항목을 하나 더하는 것으로 끝난다.
- 처음 목록:

| 이름 | `model_name` | 차원 | 최대 토큰 | 등록 | pooling | 질의 접두어 | 문서 접두어 | 받는 크기 |
|---|---|---|---|---|---|---|---|---|
| `arctic-l` (기본, 추천) | `Snowflake/snowflake-arctic-embed-l-v2.0` (int8 ONNX) | 1024 | 8192 | custom | CLS, 정규화 | `query: ` | 없음 | 약 570MB |
| `e5-small` (대안) | `Xenova/multilingual-e5-small` (int8 ONNX) | 384 | 512 | custom | MEAN, 정규화 | `query: ` | `passage: ` | 약 118MB |
| `minilm` (대안) | `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` | 384 | 128 | builtin | fastembed 기본 | 없음 | 없음 | 약 220MB |

- `minilm`은 지금 상수 값을 그대로 쓴다. `revision`은 `faf4aa4225822f3bc6376869cb1164e8e3feedd0`, `repo_id`는 `qdrant/paraphrase-multilingual-MiniLM-L12-v2-onnx-Q`, `spec_version`은 `fastembed-multilingual-minilm-l12-v2-cosine-v1`이다. 그래서 `minilm`을 고른 Graph Home의 기존 벡터는 그대로 유효하다(결정5).
- `arctic-l`과 `e5-small`의 `revision`(40자 커밋 해시), `model_file`, `files`는 구현 때 Hugging Face 저장소에서 확인해 고정한다(7절 1번).
- `spec_version` 이름 규칙: 모델, 양자화, pooling, 접두어 정책, 버전 번호를 담는다. 예: `fastembed-arctic-embed-l-v2-int8-cls-qprefix-v1`, `fastembed-multilingual-e5-small-int8-mean-qpprefix-v1`. 접두어나 pooling을 바꾸면 `spec_version`도 바꾼다. 컬렉션 이름과 `stable_vector_id`는 스펙 네 필드만 해시하므로(`storage/local/vector_store_adapter.py:145-150`), 이 규칙이 있어야 접두어가 바뀌었을 때 벡터가 오래된 것으로 표시된다.
- 상수 `DEFAULT_FASTEMBED_MODEL_SPEC`, `FASTEMBED_ARTIFACT_REPO_ID`, `SOURCE_MODEL_REVISION`은 지우고 프리셋으로 대신한다. 별칭을 남기지 않는다(`docs/ARCHITECTURE.md:252`).

### 4.2 설정 객체와 임베딩 객체 (`interface/composition/adapters/text_embeddings.py`)

- `FastEmbedTextEmbeddingsConfig`의 모델 필드 여섯 개(`model_name`, `model_version`, `dimensions`, `spec_version`, `artifact_repo_id`, `source_model_revision`)를 `preset: EmbeddingPreset` 하나로 바꾼다. 실행 필드(`cache_dir`, `embedding_batch_size`, `embedding_parallelism`, `embedding_lazy_load`, `local_files_only`)는 그대로 둔다. `cache_dir`의 기본값은 4.3의 `DEFAULT_MODELS_DIR`를 쓴다.
- `_config_for_local_files_only`는 필드를 하나씩 복사하지 않고 `dataclasses.replace(config, local_files_only=True)`를 쓴다.
- 임베딩 객체를 만드는 함수는 하나다.
  - `def text_embeddings_for(catalog_service: CatalogService, *, local_files_only: bool) -> FastEmbedTextEmbeddings`
  - 임베딩 설정 파일을 읽고(4.3), 프리셋 이름이 없으면 `DEFAULT_EMBEDDING_PRESET`을 쓰고, 모르는 이름이면 `TextEmbeddingsError`를 낸다. 오류 문구에는 파일 경로와 쓸 수 있는 이름 목록이 들어간다.
  - 1절 문제1의 다섯 곳은 모두 이 함수를 부른다. 색인 경로(`main.py:306`의 `_text_embeddings`는 `vg index`가 `main.py:573`에서 `LocalIndexServiceFactory`에 넘긴다, `local_index_service_factory.py:339`)는 `local_files_only=False`, 읽기 경로(`main.py:311`, `read_only_service_factory.py:444`)와 백그라운드 색인 판단(`recall_index_refresh.py:404`)은 `True`다.
- 내려받기(`_resolve_snapshot`)는 `repo_id=preset.repo_id`, `revision=preset.revision`, `allow_patterns=preset.files`로 `snapshot_download`를 부른다.
- 백엔드(`_default_backend_factory`)
  - `"custom"` 프리셋은 `TextEmbedding.add_custom_model(...)`로 먼저 등록한다. 한 프로세스에서 이미 등록된 이름이면 다시 등록하지 않는다.
  - 그다음 지금처럼 `TextEmbedding(model_name, specific_model_path, cache_dir, lazy_load)`를 부른다.
  - MiniLM 경고 필터는 `minilm` 프리셋일 때만 건다.

### 4.3 임베딩 설정 파일 (M01 `operation/scope/`)

- 새 모듈 `operation/scope/embedding_selection.py`. M01은 다른 기능 영역을 가져오지 않으므로(`docs/ARCHITECTURE.md:199`) 이 모듈은 프리셋을 모르고 형식만 확인한다.
  - `DEFAULT_MODELS_DIR = Path("~/llm/models")`. 모델 폴더 기본값은 이 한 곳에만 둔다.
  - `@dataclass(frozen=True) class EmbeddingSelection`: `model: str | None`, `models_dir: Path`.
  - `def load_embedding_selection(path: Path) -> EmbeddingSelection`
  - `def save_embedding_selection(path: Path, selection: EmbeddingSelection) -> None`
- 파일 형식: JSON 객체 `{"version": 1, "model": "<프리셋 이름>", "models_dir": "<절대 경로>"}`. 다른 키가 있거나, `version`이 1이 아니거나, 값의 타입이 틀리면 `load_embedding_selection`이 오류를 낸다. 읽기는 4 KiB 이하의 일반 파일만 받는다(`graph_store_factory.py:33-38`의 `backend.json` 읽기와 같은 방식).
- 파일이 없으면 `EmbeddingSelection(model=None, models_dir=DEFAULT_MODELS_DIR)`를 돌려준다. 파일을 만들지 않는다.
- 쓰기는 임시 파일에 쓴 뒤 `os.replace`로 바꾼다(`graph_store_factory.py:48-70`의 방식).
- `CatalogService`
  - `embedding_config_path = <graph-home>/configs/embedding.json`을 더한다.
  - `embedding_cache_path` 인자와 속성은 지운다. 모델 폴더는 임베딩 설정 파일에서만 정해진다. 이 속성을 쓰는 색인 전 안전 검사(`local_index_service_factory.py:237`의 `assert_cache_target_safe`)는 임베딩 설정 파일의 모델 폴더로 검사한다.
  - `def save_embedding_selection(self, selection: EmbeddingSelection) -> None`을 더한다. `save_catalog`처럼 `assert_graph_home_write_target_safe`로 쓰기 대상을 확인하고, `assert_target_outside_vaults`로 모델 폴더가 등록된 Vault 밖인지 확인한 뒤 쓴다.

### 4.4 질의와 문서 접두어

- `storage/interfaces/text_embeddings.py`의 `TextEmbeddings` Protocol에 `def embed_query(self, text: str) -> EmbeddingVector`를 더한다. 기존 `embed()`는 문서 임베딩으로 정의한다(결정4).
- `FastEmbedTextEmbeddings.embed_query`는 `preset.query_prefix + text`를, `embed`는 각 입력 앞에 `preset.document_prefix`를 붙여 일반 provider에 넘긴다. 문서 쪽 입력은 지금처럼 `contextual_embedding_text`(`vector_index_adapter.py:206`)를 거친 문자열이고, 접두어는 그 앞에 붙는다.
- `retrieval_service.py:261`은 `embed_query(request.query_text)`를 부른다. 검색 서비스는 접두어를 모른다.
- 같은 Protocol을 구현하는 테스트 대역 세 개(`tests/fakes/deterministic_text_embeddings.py`, `tests/test_acceptance_success_criteria.py`, `tests/test_cli_search.py`)에 `embed_query`를 더한다.
- 일반 패키지 `text_embeddings`의 Protocol은 바꾸지 않는다. 접두어 정책은 `vault_graph` 어댑터가 가진다.

### 4.5 CLI `vg embedding` (`interface/cli/embedding_commands.py`)

`main.py`의 다른 그룹처럼 `embedding_app = typer.Typer(no_args_is_help=True)`를 `app.add_typer(embedding_app, name="embedding")`로 붙인다.

- `vg embedding list [--graph-home PATH] [--format text|json]`
  - `arctic-l`을 맨 위에 "추천"으로 보여 주고, 나머지 둘은 "대안"으로 그 아래에 보여 준다.
  - 프리셋마다 이름, 추천/대안, 선택 여부, 차원, 최대 토큰, 받는 크기, 모델 폴더에 이미 받았는지, 한 줄 설명(`summary`)을 보여 준다.
  - 맨 위에 임베딩 설정 파일 경로와 모델 폴더를 보여 준다.
  - 받았는지는 `local_files_only=True`로만 확인한다. 네트워크를 쓰지 않고 아무것도 쓰지 않는다.
- `vg embedding use NAME [--models-dir PATH] [--graph-home PATH]`
  - 순서: (1) 이름이 목록에 있는지 확인, (2) 모델 폴더가 등록 Vault 밖인지 확인, (3) 모델 폴더에 모델이 없으면 내려받기, (4) 임베딩 설정 파일 쓰기, (5) 다음 할 일 안내 출력.
  - `--models-dir`가 없으면 지금 설정의 모델 폴더를 그대로 쓴다. 상대 경로와 `~`는 절대 경로로 바꿔 저장한다.
  - 다시 임베딩은 하지 않는다. 안내 문구는 "다음 `vg index`(또는 다음 세션 시작 때의 백그라운드 색인)가 모든 조각을 다시 임베딩한다. 그동안 그 Vault의 검색은 키워드 결과만 돌려준다"는 뜻을 담는다.
  - Graph Home이 초기화되지 않았으면 `vg init`을 먼저 하라는 오류를 낸다.
- `vg status`의 출력은 바꾸지 않는다. 이미 모델 이름과 revision을 보여 준다(`operation/diagnostics/index_status_reader.py:136-137`). 선택된 프리셋 이름과 모델 폴더는 `vg embedding list`에서 본다(결정11).

### 4.6 문서

- README에 "Embedding model" 절을 더한다(영어, README의 언어). 먼저 추천 모델 `arctic-l` 하나를 한국어와 coding agent 세션에 맞는 기본 모델로 소개하고, 그 아래 대안 두 개(`e5-small` 작고 빠름, `minilm` 예전 기본 모델·되돌리기용)를 짧은 표로 적는다. 이어서 모델 폴더와 바꾸는 법, `vg embedding list`와 `vg embedding use`, 모델을 바꾼 뒤 다시 색인되는 동안 검색이 키워드 결과만 돌려준다는 것, 첫 전체 재색인 시간과 저장 공간 증가, 다시 색인이 끝나면 예전 모델의 빈 컬렉션이 지워진다는 것을 적는다. 첫 설치 순서는 `vg init` → (원하면) `vg embedding use` → `vg index`로 적는다. "Common Commands" 표에 두 명령을 더한다. `tests/test_readme_onboarding_contract.py:26`이 확인하는 문장은 유지한다.
- `docs/ARCHITECTURE.md` §4(`:240-242`)에 `vg embedding use`를 모델을 내려받고 설정 파일을 쓸 수 있는 명시적 명령으로 더한다. 같은 곳에 "성공한 색인은 발행 전 새 세대에서 예전 모델의 빈 벡터 컬렉션을 지운다. 읽기 경로는 지우지 않는다"(4.7)를 한 문장으로 더한다. §2(`:182`)에 프리셋과 임베딩 설정 파일의 위치를 한 줄 더한다.
- `docs/DECISIONS.md`에는 spec 승인 뒤 "기본 임베딩 모델을 arctic-l로 바꾸고 프리셋으로 고르게 한다" 결정을 더한다. 2026-06-08 MiniLM 결정(`:518-541`)은 지우지 않고 새 결정이 대신한다고 적는다.
- `docs/SPEC.md:84`(가치2 "다국어 MiniLM 임베딩")와 `:366`(n차-4), `docs/TODO.md:54`를 "모델은 사람의 결정으로 정했고, 측정1 비교는 남아 있다"는 뜻으로 고친다.

### 4.7 예전 빈 컬렉션 정리 (결정8)

지금 구조에서 확인한 사실

- 색인(`vg index`, `vg setup`, `vg watch`, MCP 쓰기 뒤 백그라운드 색인)은 `transactional=True`로 연다(`main.py:576`, `operation/runtime/setup_service.py:112`, `watch_service.py:74`, `interface/mcp/mcp_service_factory.py:258`). 이때 활성 세대 폴더를 새 세대 폴더로 복사하고(`projection_generation.py:75-102`), `CatalogService.vector_path`를 그 새 폴더 안으로 바꾼다(`local_index_service_factory.py:143-145`, `:342-345`). 새 세대는 발행 잠금을 쥔 채 만들어지고, 발행 전에는 어떤 읽기 경로도 열지 않는다.
- 발행은 `LocalIndexServiceBundle.commit_projection`(`local_index_service_factory.py:52-96`)이 한다. `vg index`는 실행 결과의 종료 코드가 0일 때만 이를 부른다(`main.py:585-586`). 발행에 실패하거나 부르지 않으면 새 세대는 버려진다(`:98-113`).
- 발행 뒤에는 현재 세대와 바로 이전 세대만 남는다(`projection_generation.py:112-118`, `docs/ARCHITECTURE.md:240`).
- 일반 패키지 `vector_search.ChromaVectorStore`는 컬렉션 목록·삭제 공개 메서드가 없고, Chroma 클라이언트는 비공개 `_require_client`(`chroma_store.py:90-97`) 안에 있다. `src`에는 `chromadb`를 직접 가져오는 곳이 없다.

설계

- 새 메서드는 `storage/local/vector_store_adapter.py`의 `ChromaVectorStore`(vault_graph 어댑터)에 둔다.
  - `def remove_empty_collections(self, *, keep: EmbeddingModelSpec) -> tuple[str, ...]`
  - 이 어댑터가 `chromadb.PersistentClient(path)`를 함수 안에서 지연 가져와 직접 연다. 일반 패키지는 바꾸지 않는다(A-16).
  - 지우는 컬렉션은 다음을 모두 만족하는 것뿐이다. (1) 이름이 `f"{COLLECTION_PREFIX}_"`로 시작한다. (2) 이름이 `_collection_spec(keep).name`과 다르다. (3) 레코드 수가 0이다. 지운 이름 목록을 돌려준다.
  - `read_only=True`로 연 저장소에서 부르면 `VectorStoreError`를 내고 아무것도 지우지 않는다.
- 부르는 곳은 `LocalIndexServiceBundle.commit_projection` 하나다. 다음 조건을 모두 만족할 때만, `_write_projection_component_manifests`와 `activate` 바로 앞에서 부른다.
  - `self.staged_generation`이 있고 `self.bundle_publisher`가 있다. 즉 아직 발행되지 않은 새 세대 폴더에만 쓴다.
  - `report.vector`가 `VectorApplyResult`이고 `failed`가 `False`다. 벡터 단계가 실패했거나 계획만 세운 실행(`--dry-run`)에서는 부르지 않는다.
  - `keep`은 이 실행이 실제로 쓴 스펙(`report.vector.embedding_spec`)이다. 실행 중에 임베딩 설정 파일이 바뀌어도 이 값을 쓴다.
- 레코드 수 0 조건 때문에 `--vault-id`로 일부 Vault만 다시 임베딩한 실행에서는, 다른 Vault의 예전 레코드가 남은 컬렉션을 지우지 않는다. 마지막 Vault까지 다시 임베딩된 실행에서 비로소 지워진다.
- 정리가 실패하면(`VectorStoreError`) 발행은 그대로 한다. 컬렉션이 남는 것은 검색 결과를 바꾸지 않기 때문이다. 정리는 다음 성공한 색인에서 다시 시도된다.
- `commit_projection`은 지운 컬렉션 이름과 정리 실패 메시지를 돌려준다(지금은 `None`을 돌려주므로 추가 변경). `vg index`만 이를 출력한다. 지운 것이 있으면 `removed_vector_collections: <개수>`, 실패했으면 `warning: vector collection cleanup failed: <메시지>` 한 줄이다. 둘 다 없으면 출력은 지금과 같다. 다른 호출자(setup, watch, MCP 백그라운드 색인, 세션 시작 빠른 갱신)는 돌려받은 값을 쓰지 않는다.
- 읽기 경로(`vg search`, MCP 읽기 도구, 세션 시작 회상, `vg status`)와 임베딩 없이 도는 세션 시작 빠른 갱신(`recall_index_refresh.py:224`, `report.vector`가 없음)은 이 메서드를 부르지 않는다.
- 디스크가 실제로 줄어드는 시점: 정리된 세대가 발행된 뒤에도 바로 이전 세대 폴더에는 예전 컬렉션이 남는다. 그다음 발행에서 그 이전 세대가 지워질 때 공간이 돌아온다.

## 5. Decisions

| 결정 | 내용 | 이유 | 누가 |
|---|---|---|---|
| 결정1 | 기본 프리셋은 `arctic-l`(snowflake-arctic-embed-l-v2.0 int8) | 공개 한국어 점수가 후보 중 가장 높은 쪽(0.724, bge-m3와 같음)이고, Apache-2.0이며, 받는 크기가 bge-m3의 약 4분의 1이다. 최대 8192토큰이라 128토큰에서 잘리던 긴 조각도 읽는다. 대가는 첫 전체 재색인 최대 약 48분과 벡터 저장소 약 2.7배다 | 사람(인터뷰 "arctic-l") |
| 결정2 | 이 작업에 가장 맞는 모델 하나(`arctic-l`)를 추천 모델로 내세우고, 목록에는 대안 둘(`e5-small`, `minilm`)을 함께 둔다. README와 `vg embedding list`는 `arctic-l`을 한국어와 coding agent 세션용 추천 모델로, `e5-small`을 작고 빠른 대안으로, `minilm`을 예전 모델이자 되돌리기 경로로 보여 준다 | 사람의 답 "이런 유형에 작업에 가장 적합한 모델을 후보로 골라서 하나만으로 먼저 시작합니다. 위 세 개로 추가해도 무방할 듯 합니다"를 "추천은 하나, 목록은 세 개"로 해석했다. `minilm`은 지금 벡터를 그대로 쓰는 되돌리기 경로라 남길 이유가 있다. 더 큰 모델은 받는 크기가 2GB를 넘고 arctic-l보다 점수 이득이 없다 | 사람(spec gate 질문3, 해석은 coordinator) |
| 결정3 | 선택은 `<graph-home>/configs/embedding.json`에 둔다 | `configs/vaults.yaml`은 저장할 때 모르는 키를 지운다(`operation/scope/vault_catalog.py:89-127`). 작은 JSON을 원자적으로 쓰는 선례(`graph/backend.json`)가 있다 | [가정] brief 가정2 |
| 결정4 | 질의는 새 메서드 `embed_query`, 문서는 기존 `embed` | 질의 임베딩을 부르는 곳은 `retrieval_service.py:261` 하나다. 메서드를 나누면 타입 검사가 잘못된 호출을 잡는다. 다른 안은 설정에 "질의용/문서용" 역할을 두고 객체를 두 개 만드는 것인데, 잘못 만든 객체를 넘겨도 아무 검사에 걸리지 않는다 | spec 작성자 |
| 결정5 | `minilm` 프리셋의 스펙 네 필드는 지금 값과 같게 둔다 | `minilm`을 고르면 지금 벡터를 다시 임베딩하지 않고 그대로 쓴다 | spec 작성자 |
| 결정6 | `vg embedding use`는 모델을 받고 설정만 쓴다. 다시 임베딩은 기존 `vg index`와 세션 시작 백그라운드 색인이 한다 | 다시 임베딩 경로가 이미 있다(`recall_index_refresh.py:354-393`, `hook_commands.py:161`). 같은 일을 두 번 만들지 않는다. 내려받기를 먼저 하고 설정을 나중에 써서, 내려받기가 실패하면 설정이 바뀌지 않는다 | [가정] brief 가정3 |
| 결정7 | 임베딩 설정 파일이 깨졌거나 모르는 프리셋 이름이면, 모델을 쓰는 명령은 오류로 끝난다. 기본 모델로 바꿔 쓰지 않는다 | 다른 모델로 몰래 바꾸지 않는다는 기존 결정(`docs/DECISIONS.md:538-539`)을 따른다. 이 파일은 `vg embedding use`만 쓰므로 깨지는 경우는 손으로 고쳤을 때뿐이다 | spec 작성자 |
| 결정8 | 비워진 예전 Chroma 컬렉션을 이번 작업에서 지운다. 성공한 색인이 아직 발행하지 않은 새 세대 안에서, `vault_graph_` 접두어를 가졌고 이번 실행의 스펙 컬렉션이 아니며 레코드가 0개인 컬렉션만 지운다(4.7). 일반 패키지는 바꾸지 않고 vault_graph 어댑터가 Chroma 클라이언트를 직접 연다 | 모델을 바꿀 때마다 빈 컬렉션이 세대마다 복사되며 쌓인다(1절 문제7). 발행 전 새 세대에서만 지우므로 읽는 쪽이 보는 활성 세대는 바뀌지 않고, 실패하면 그 세대가 통째로 버려진다(`local_index_service_factory.py:98-113`). 레코드 0개 조건은 일부 Vault만 다시 임베딩한 경우 다른 Vault의 데이터를 지키기 위해서다. 일반 패키지에 메서드를 더하는 안도 있지만, 어댑터 안에서 해결되므로 `packages/` 계약을 건드리지 않는다 | 사람(spec gate 질문2 "이번에 넣음"). 위치와 조건은 coordinator 지시 |
| 결정9 | 임베딩 설정 파일이 없는 Graph Home은 `arctic-l`을 쓴다 | 결정1의 기본 모델이 설치 직후부터 적용된다. 대가로 이미 쓰던 Graph Home은 새 버전을 설치한 뒤 첫 세션에 다시 임베딩이 시작된다 | 사람(spec gate 질문1 "바로 arctic-l") |
| 결정10 | 내려받을 파일을 프리셋의 `files`로 제한한다 | Hugging Face 저장소에는 int8 외의 가중치 파일이 함께 있을 수 있다. 제한하지 않으면 570MB 대신 몇 GB를 받을 수 있다(7절 2번) | spec 작성자 |
| 결정11 | `vg embedding status`는 만들지 않고, `vg embedding list`가 선택·폴더·받음 여부를 함께 보여 준다. `vg status`는 바꾸지 않는다 | 명령 두 개로 충분하다. 벡터가 오래되었는지는 이미 `vg status`가 보여 준다 | [가정] brief 가정3을 줄임 |
| 결정12 | 모델 폴더 기본값 `~/llm/models` | 사람이 정했다 | 사람(앞선 대화) |

## 6. Failure and boundary behavior

| 상황 | 동작 |
|---|---|
| 임베딩 설정 파일이 없다 | 기본 프리셋 `arctic-l`과 `~/llm/models`를 쓴다. 파일을 만들지 않는다 |
| 임베딩 설정 파일이 JSON이 아니다, `version`이 1이 아니다, 모르는 키나 틀린 타입이 있다, 4 KiB를 넘는다 | `vg index`, `vg search`, MCP 도구 등 임베딩 객체를 만드는 명령은 파일 경로와 이유를 담은 오류로 끝난다. 파일을 고치지 않는다 |
| 임베딩 설정 파일의 프리셋 이름을 모른다 | 위와 같이 오류로 끝나고, 쓸 수 있는 이름 목록을 함께 보여 준다 |
| 설정 파일이 잘못된 상태에서 세션 시작 훅이 돈다 | 회상은 임베딩 모델을 열지 않으므로 그대로 나온다. 백그라운드 색인 판단(`vectors_need_catch_up`)은 오류를 로그(`<graph-home>/logs`)에 남기고 색인을 시작하지 않는다 |
| `vg embedding use`에 모르는 이름을 준다 | 0이 아닌 종료 코드, 쓸 수 있는 이름 목록 출력. 설정 파일과 모델 폴더는 바뀌지 않는다 |
| `vg embedding use` 중 내려받기가 실패한다(오프라인, 저장소 접근 실패, 디스크 부족) | 0이 아닌 종료 코드. 설정 파일은 바뀌지 않는다. 일부 받은 파일은 Hugging Face 캐시 규칙대로 남고 다음 시도에서 이어 받는다 |
| `vg embedding use`의 모델 폴더가 등록된 Vault 안이다 | 0이 아닌 종료 코드. 내려받지 않고 설정 파일도 쓰지 않는다 |
| `vg embedding use`로 이미 선택된 프리셋을 다시 고른다 | 모델이 폴더에 있으면 내려받지 않는다. 설정 파일 내용은 같다. 스펙이 같으므로 다시 임베딩되지 않는다 |
| Graph Home이 초기화되지 않은 상태에서 `vg embedding use` 또는 `list` | `vg init`을 먼저 하라는 오류. 아무것도 쓰지 않는다 |
| 모델을 바꾼 뒤 다시 임베딩되기 전에 검색한다 | 지금 동작과 같다. 그 범위는 `vector_stale` 경고와 함께 키워드 결과만 돌려준다(`retrieval_service.py:264`) |
| 모델을 바꾼 뒤 모델 파일이 폴더에 없는 상태에서 검색한다 | 읽기 경로는 내려받지 않는다. `embedding_model_unavailable` 경고와 함께 키워드 결과만 돌려준다(`retrieval_service.py:339-346`) |
| 세션 시작 백그라운드 색인이 새 모델로 다시 임베딩한다 | 모델이 없으면 그 프로세스가 내려받는다. 다시 임베딩은 Vault마다 차례로 돌고, 끝난 Vault부터 벡터 검색이 돌아온다. 시간 제한은 없다(`hook_commands.py:161-206`) |
| 다시 임베딩 중 세션이 끝나거나 프로세스가 죽는다 | 지금 동작과 같다. 벡터가 계속 오래된 상태로 남고 다음 세션 시작이 다시 실행한다 |
| `vg index`가 도는 중 `vg embedding use`로 모델을 바꾼다 | 돌고 있는 색인은 시작할 때의 스펙으로 끝난다. 다음 색인이 새 스펙으로 다시 임베딩한다 |
| MCP 서버가 떠 있는 동안 모델을 바꾼다 | 서버는 서비스를 다시 열 때 설정 파일을 다시 읽는다. 다시 열기 전까지는 예전 스펙으로 질의하므로 새 벡터를 오래된 것으로 보고 키워드 결과만 돌려준다. 다시 열리는 시점은 7절 6번 |
| `custom` 프리셋을 한 프로세스에서 두 번 연다 | `add_custom_model`은 처음 한 번만 부른다 |
| 1024차원 벡터를 쓸 디스크 공간이 모자란다 | 색인이 실패하고 기존 실패 경로(`VectorApplyResult` `failed`)로 보고된다. 기존 벡터는 오래된 상태로 남는다 |
| `minilm`으로 되돌린다 | 지금 쓰던 스펙과 같으므로, 다른 모델로 다시 임베딩한 적이 없다면 벡터를 그대로 쓴다. 다른 모델로 다시 임베딩한 뒤라면 MiniLM 레코드와 빈 컬렉션은 이미 지워졌으므로(`packages/vector-index/src/vector_index/indexing.py:106-108`, 4.7) 다시 임베딩한다 |
| 색인이 성공하고 예전 스펙의 컬렉션이 비었다 | 발행 전 새 세대에서 그 컬렉션을 지우고 발행한다. `vg index`는 `removed_vector_collections: <개수>`를 출력한다 |
| `--vault-id`로 일부 Vault만 다시 임베딩해 예전 컬렉션에 다른 Vault 레코드가 남았다 | 지우지 않는다. 나머지 Vault까지 다시 임베딩된 색인에서 지운다 |
| 이번 실행의 스펙 컬렉션이 비어 있다(예: Vault에 조각이 없음) | 지우지 않는다. `keep` 컬렉션은 레코드 수와 상관없이 남긴다 |
| 이름이 `vault_graph_`로 시작하지 않는 컬렉션 | 건드리지 않는다 |
| 벡터 단계가 실패했다(`VectorApplyResult.failed`), 결과에 벡터가 없다, `--dry-run`이다, 종료 코드가 0이 아니라 발행하지 않는다 | 정리하지 않는다 |
| 정리 중 Chroma 오류가 난다 | 발행은 그대로 한다. `vg index`는 경고 한 줄을 출력하고 종료 코드는 바뀌지 않는다. 다음 성공한 색인이 다시 시도한다 |
| 정리 뒤 발행이 실패한다 | 새 세대는 통째로 버려진다(`local_index_service_factory.py:98-113`). 활성 세대의 컬렉션은 그대로다 |
| 정리가 도는 동안 검색한다 | 검색은 활성 세대만 읽고, 정리는 발행 잠금을 쥔 아직 발행되지 않은 세대에서만 일어나므로 결과가 바뀌지 않는다 |
| 발행 뒤 `rollback`으로 이전 세대로 돌아간다 | 이전 세대 폴더에는 예전 컬렉션이 그대로 있으므로 그 세대의 벡터를 그대로 쓴다 |

## 7. What could be wrong

1. `arctic-l`과 `e5-small`의 고정 revision, ONNX 파일 경로(`model_file`), 필요한 토크나이저 파일 목록(`files`)을 확인하지 못했다. `research/model-candidates.md`는 두 모델이 fastembed 0.8.0에서 돈다는 것만 기록했다. 구현 때 Hugging Face 저장소에서 확인해 프리셋에 적어야 하고, 파일 목록이 빠지면 첫 로드가 실패한다.
2. Snowflake 저장소에 int8 외의 큰 가중치 파일이 함께 있는지 확인하지 않았다. 결정10은 그럴 수 있다는 추정에 기대고 있다. 없더라도 `files` 제한은 해가 없다.
3. 한국어 점수는 공식 MTEB 실행이 아니라 커뮤니티 표의 한국어 문장 질의응답 점수다. 코드 식별자, 경로, 셸 출력이 섞인 세션 원문에서 arctic-l이 MiniLM보다 낫다는 것은 측정되지 않았다(n차-4에 남음).
4. 재색인 시간 48분과 저장소 2.7배는 32개 조각(405토큰)으로 한 번 잰 속도와 차원 비율로 계산한 값이다. 실제 조각은 더 짧아 시간은 더 짧을 것으로 보지만 확인하지 않았다.
5. arctic-l을 배치 크기 256으로 돌릴 때 메모리 사용량을 재지 않았다. 최대 8192토큰을 읽으므로 긴 조각이 많은 배치에서 메모리가 크게 늘 수 있다.
6. 떠 있는 MCP 서버가 언제 서비스를 다시 여는지 확인하지 않았다. `docs/ARCHITECTURE.md:242`는 활성 세대가 바뀌면 다시 연다고 적지만, 그때 임베딩 객체도 다시 만들어 설정 파일을 다시 읽는지는 코드로 확인하지 않았다. 아니라면 모델을 바꾼 뒤 MCP 서버를 다시 시작해야 하고, README에 그렇게 적어야 한다.
7. fastembed 0.8.0에서 `add_custom_model`을 같은 이름으로 두 번 부르면 어떻게 되는지 확인하지 않았다. 4.2는 "이미 등록되었으면 건너뜀"으로 이를 피한다.
8. fastembed의 custom 등록 경로(CLS pooling + 정규화)가 원본 sentence-transformers 결과와 같은 벡터를 내는지 확인하지 않았다. 다르면 공개 점수만큼의 품질이 나오지 않을 수 있다.
9. 업그레이드 직후 백그라운드 재임베딩이 도는 동안 이 컴퓨터의 다른 작업이 느려질 수 있다. CPU 사용량은 재지 않았다.
10. 같은 프로세스에서 일반 패키지의 Chroma 클라이언트(`chroma_store.py:96`)가 열린 채 어댑터가 같은 경로로 두 번째 `chromadb.PersistentClient`를 열 때의 동작을 확인하지 않았다. Chroma가 경로마다 내부 시스템을 하나만 두고 함께 쓴다고 알고 있지만 이 저장소의 chromadb 버전으로 재지 않았다. 문제가 있으면 일반 패키지 `vector_search.ChromaVectorStore`에 컬렉션 이름 목록과 삭제 공개 메서드를 더하는 것이 대안이다. 이 경우 기존 시그니처는 그대로 두고 메서드만 더하지만 A-16을 바꿔야 하므로 다시 승인받는다.
11. Chroma가 컬렉션을 지울 때 디스크 공간을 얼마나 돌려주는지 확인하지 않았다. 벡터 색인 파일 폴더는 지워질 것으로 보지만, `chroma.sqlite3` 파일은 VACUUM 없이는 줄지 않을 수 있다(3절 8번).
12. 일부 Vault에서 색인이 계속 실패하면 그 Vault의 예전 레코드가 남아 컬렉션이 지워지지 않는다. 사용자가 이 상태를 볼 방법은 `vg status`의 stale 표시뿐이다.

## 8. Acceptance criteria

검사 명령은 CI(`.github/workflows/ci.yml:19-23`)와 같다.

- A-1 `uv run --python 3.12 ruff check src tests packages`가 통과한다.
- A-2 `uv run --python 3.12 mypy src tests packages/text-embeddings/src packages/vector-search/src packages/vector-index/src`가 통과한다.
- A-3 `uv run --python 3.12 --all-packages --all-extras pytest -q tests packages/*/tests`가 통과한다. 새 테스트와 바뀐 테스트는 `snapshot_resolver`·`backend_factory` 대역이나 가짜 `fastembed` 모듈만 쓰고, 모델 파일을 내려받거나 실제 모델 폴더를 바꾸지 않는다(`docs/DECISIONS.md:333`).
- A-4 `EMBEDDING_PRESETS`에 `arctic-l`, `e5-small`, `minilm`이 있고 `DEFAULT_EMBEDDING_PRESET == "arctic-l"`이다. 모든 프리셋의 `revision`은 40자 16진수이고, `spec_version`은 서로 다르다. 테스트로 확인한다.
- A-5 `minilm` 프리셋의 스펙 네 필드가 `44dbf86`의 `DEFAULT_FASTEMBED_MODEL_SPEC`(`faf4aa4225822f3bc6376869cb1164e8e3feedd0`, 384, `fastembed-multilingual-minilm-l12-v2-cosine-v1`)과 같고, `repo_id`가 `qdrant/paraphrase-multilingual-MiniLM-L12-v2-onnx-Q`다. 테스트로 확인한다.
- A-6 임베딩 설정 파일이 없는 Graph Home에서 `text_embeddings_for(..., local_files_only=True).model_spec()`이 `arctic-l`의 스펙이고, `config.cache_dir`가 `~/llm/models`를 펼친 경로다. 이 호출 뒤 Graph Home에 새 파일이 없다.
- A-7 `src` 안에서 `FastEmbedTextEmbeddingsConfig(`를 부르는 곳은 `interface/composition/adapters/text_embeddings.py` 한 파일뿐이고, `llm/models` 문자열은 `operation/scope/embedding_selection.py` 한 곳에만 있다. `rg` 검색으로 확인한다.
- A-8 `vg embedding use e5-small --graph-home <tmp>`(가짜 내려받기)를 실행하면 종료 코드가 0이고, `<tmp>/configs/embedding.json`이 `{"version": 1, "model": "e5-small", "models_dir": <절대 경로>}`이다. 내려받기 대역은 `local_files_only=False`, `revision`이 프리셋 값, `allow_patterns`가 프리셋 `files`인 호출을 받는다.
- A-9 `vg embedding use nope`, 내려받기 대역이 실패하는 `vg embedding use e5-small`, 등록 Vault 안을 가리키는 `--models-dir`로 실행한 `vg embedding use e5-small`은 모두 0이 아닌 종료 코드로 끝나고, 실행 전후 `configs/embedding.json`의 바이트(또는 없음)가 같다.
- A-10 `vg embedding list --format json`은 프리셋 세 개를 이름, 추천/대안 표시, 선택 여부, 차원, 받음 여부, `summary`와 함께 돌려준다. 첫 항목은 `arctic-l`이고 추천으로 표시되며, 나머지 둘은 대안으로 표시된다. 결과는 또한 설정 파일 경로와 모델 폴더를 담는다. 실행 중 내려받기 대역은 `local_files_only=True` 호출만 받고, 실행 전후 Graph Home 바이트가 같다.
- A-11 가짜 백엔드가 받은 문자열로 접두어를 확인한다. `e5-small`: `embed_query("x")` → `"query: x"`, `embed`의 문서 `"y"` → `"passage: y"`. `arctic-l`: `"query: x"`, `"y"`. `minilm`: `"x"`, `"y"`.
- A-12 검색 서비스가 질의를 `embed_query`로 임베딩한다. `embed`를 부르면 실패하는 대역으로 `RetrievalService` 벡터 검색 테스트를 돌려 확인한다.
- A-13 `custom` 프리셋으로 `_default_backend_factory`를 같은 프로세스에서 두 번 부르면, 가짜 `fastembed` 모듈의 `add_custom_model`이 프리셋의 `model_name`, `pooling`, `normalization`, `dim`, `model_file`로 한 번만 불린다. `minilm`에서는 불리지 않고, 기존 MiniLM 경고 억제 테스트(`tests/test_fastembed_text_embeddings.py:130-152`)가 통과한다.
- A-14 잘못된 임베딩 설정 파일(JSON 아님, `version: 2`, 모르는 키, 모르는 프리셋 이름 각각)로 `vg search`와 `vg index`를 실행하면 0이 아닌 종료 코드와 파일 경로가 담긴 오류가 나오고, 다른 모델로 임베딩하지 않으며, 설정 파일 바이트가 같다.
- A-15 경계 테스트 `tests/test_feature_import_direction.py`, `tests/test_module_import_cycles.py`, `tests/test_functional_module_boundaries.py`, `tests/test_read_only_boundary.py`, `tests/test_search_read_only_boundary.py`가 위반 예외 목록을 늘리지 않고 통과한다. `operation/scope/embedding_selection.py`는 다른 기능 영역을 가져오지 않는다.
- A-16 `git diff 44dbf86 -- packages/` 출력이 비어 있다(일반 패키지 계약 무변경).
- A-17 기존 CLI 명령과 인자가 그대로 있다. `vg --help`의 기존 명령 목록에서 빠지거나 이름이 바뀐 것이 없고 `embedding`만 더해졌다. 기존 CLI·MCP 계약 테스트가 고치지 않고 통과한다.
- A-18 README에 "Embedding model" 절이 있고, 그 절에 `arctic-l`, `e5-small`, `minilm`, `~/llm/models`, `vg embedding list`, `vg embedding use`가 있다. 절 안에서 `arctic-l`이 다른 두 이름보다 먼저 나오고 추천 모델(recommended)로 적혀 있다. 모델을 바꾼 뒤 다시 색인될 때까지 키워드 결과만 나온다는 문장이 있다. `tests/test_readme_onboarding_contract.py`에 이 확인을 더하고, 기존 확인 문장(`:26`)도 계속 통과한다.
- A-19 `docs/ARCHITECTURE.md` §4가 `vg embedding use`를 모델을 내려받고 설정을 쓸 수 있는 명시적 명령으로 적고, 색인 발행 전 새 세대에서 빈 예전 벡터 컬렉션을 지운다는 것을 적는다.

예전 빈 컬렉션 정리(4.7). 모두 임시 폴더의 실제 Chroma 저장소와 가짜 임베딩으로 확인하며 모델을 내려받지 않는다.

- A-20 컬렉션 세 개(이번 스펙 컬렉션, 비어 있는 예전 `vault_graph_` 컬렉션, 레코드가 있는 예전 `vault_graph_` 컬렉션)와 접두어가 다른 빈 컬렉션 하나가 있는 저장소에서 `remove_empty_collections(keep=<이번 스펙>)`을 부르면, 비어 있는 예전 `vault_graph_` 컬렉션 하나만 지워지고 그 이름만 돌려받는다.
- A-21 이번 스펙 컬렉션이 비어 있어도 `remove_empty_collections`는 그것을 지우지 않는다.
- A-22 `read_only=True`로 연 어댑터에서 `remove_empty_collections`를 부르면 `VectorStoreError`가 나고 컬렉션 수가 같다.
- A-23 스펙 A로 색인해 발행한 Graph Home에서 스펙 B로 `vg index --all-vaults`를 성공시키면, 새 활성 세대의 Chroma에는 스펙 B 컬렉션만 남고, 바로 이전 세대 폴더의 Chroma에는 스펙 A 컬렉션이 그대로 있다. 출력에 `removed_vector_collections: 1`이 있다.
- A-24 같은 준비에서 벡터 단계가 실패하도록 한 색인(임베딩 대역이 오류를 냄)과 `--dry-run` 실행 뒤에는 활성 세대가 바뀌지 않고, 활성 세대의 스펙 A 컬렉션이 그대로 있다.
- A-25 Vault 두 개 중 하나만 `--vault-id`로 스펙 B로 다시 임베딩하면 스펙 A 컬렉션이 남는다. 나머지 Vault까지 다시 임베딩하면 그 색인에서 지워진다.
- A-26 정리 중 오류가 나도록 한 대역으로 `vg index`를 실행하면 종료 코드는 0이고, 새 세대가 발행되며, 출력에 `warning: vector collection cleanup failed` 줄이 있다.
- A-27 `vg search`, `vg status`, `vg hook session-start` 실행 전후로 활성 세대 Chroma의 컬렉션 이름 목록이 같다. `remove_empty_collections`를 부르는 곳은 `src`에서 `local_index_service_factory.py` 한 곳뿐이다(`rg` 확인).

일정과 실제 Graph Home 보호(9절 "실행 일정")

- A-28 지금 구현 세션은 모델 파일을 내려받지 않는다. 구현 세션 전후로 `$HOME/.vault-graph/projections/active.json`과 `$HOME/.vault-graph/configs/`의 바이트가 같다.
- A-29 2026-11-05 01:00 실행 세션의 결과로 다음이 남는다. (1) `~/llm/models`에 `arctic-l` 프리셋의 고정 revision 스냅샷이 있다. (2) 그 모델로 짧은 한국어 질의와 영어 코드 문장을 임베딩해 1024차원 벡터가 나온다. (3) 임시 Graph Home에서 사용자 Vault 전체를 `arctic-l`로 다시 임베딩한 시간과 벡터 폴더 크기가 기록된다. (4) 이 실행 전후로 `$HOME/.vault-graph`의 `projections/active.json`과 `configs/`의 바이트가 같다.

## 9. Open decisions

남은 질문은 없다. spec gate(2026-11-04)에서 사람이 세 질문에 답했고 spec을 승인했다.

### spec gate 답

| 질문 | 사람의 답 | 반영한 곳 |
|---|---|---|
| 질문1 이미 쓰던 Graph Home도 바로 arctic-l로 바꿀 것인가 | 옵션1 "바로 arctic-l" | 결정9, 2절 2번 |
| 질문2 예전 빈 벡터 컬렉션 정리를 이번에 넣을 것인가 | 옵션2 "이번에 넣음" | 결정8, 1절 문제7, 4.7, 6절, A-20~A-27. 3절에서 정리 제외 항목을 지웠다 |
| 질문3 목록을 세 개로 시작할 것인가 | "이런 유형에 작업에 가장 적합한 모델을 후보로 골라서 하나만으로 먼저 시작합니다. 위 세 개로 추가해도 무방할 듯 합니다 만 일단 이런 의견을 고려해서 진행해주세요" | 결정2, 2절 3번, 4.1·4.5·4.6, A-10, A-18. 해석: 추천 모델은 `arctic-l` 하나로 내세우고, 목록에는 대안 둘을 함께 둔다 |
| 승인 | "승인합니다 위 작업에 다운로드 양이 많다면 이작업을 내일 세벽 1시부터 스케쥴하여 다시 시작하는 걸로합니다." | 아래 "실행 일정" |

### 실행 일정

1. 지금(2026-11-04) 코드와 테스트를 구현한다. 테스트는 모델을 내려받지 않으므로(A-3) 큰 내려받기 없이 끝난다(A-28).
2. 큰 내려받기가 필요한 일은 2026-11-05 01:00(이 컴퓨터 시간)에 예약한 세션에서 한다(A-29).
   1. `arctic-l`(약 570MB)을 `~/llm/models`에 받는다.
   2. 실제 모델로 짧은 임베딩을 돌려 로드와 차원을 확인한다.
   3. 임시 Graph Home을 만들어 사용자 Vault를 등록하고, `arctic-l`로 전체를 다시 임베딩하는 시간과 벡터 폴더 크기를 잰다. 결과는 Vault 내용 없이 합계만 남긴다. 7절 4번의 추정값을 이 값으로 바꾼다.
3. 지금 쓰이는 `vg`는 uv tool로 설치된 vault-graph 0.2.1이다(`$HOME/.local/share/uv/tools/vault-graph/lib/python3.12/site-packages/vault_graph-0.2.1.dist-info`로 확인). 그래서 사용자의 실제 Graph Home(`$HOME/.vault-graph`)은 새 버전을 릴리스해 설치한 뒤에야 `arctic-l`로 바뀐다.
4. 01:00 세션은 작업 트리 코드로 `$HOME/.vault-graph`를 색인하지 않는다. 설치된 0.2.1의 세션 시작 훅이 MiniLM 스펙으로 벡터를 오래된 것으로 보고 다시 MiniLM으로 임베딩해 되돌리기 때문이다. 시간 측정은 임시 Graph Home에서만 한다(3절 9번, A-29).
