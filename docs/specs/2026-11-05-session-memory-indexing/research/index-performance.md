# 인덱싱 성능 조사: 원인 5개 검증과 근본 수정안

조사일: 2026-11-05. 코드 기준: `feat/jh/session-memory-indexing` 워크트리. 측정 대상: 활성 generation `94b041d79e5f406da26fc7338bacf4f9` (`$HOME/.vault-graph/projections/active.json`).
측정은 모두 읽기 전용이다. 실제 `vg index`는 돌리지 않았고 `vg index --dry-run`만 실행했다.
확인하지 못한 주장은 "추정"으로 표시한다.

## 1. 요약 표

| 번호 | 원인 | 근거 | 근본 수정 |
|---|---|---|---|
| 원인1 | 세션 기록이 청크 대부분을 차지 | 34,008 청크 중 28,330 (83%), 토큰 74.6% | 세션 청크 설계는 별도 문서. 여기서는 비용만 정량화 |
| 원인2 | 문서 하나가 바뀌면 그 문서 청크 전체를 다시 임베딩 | 지문에 `index_revision` 포함 (`src/vault_graph/indexing/vector_index_adapter.py:343-366`) | 임베딩 키(모델, 임베딩 텍스트 해시)와 메타데이터 지문을 분리. 메타데이터만 바뀌면 Chroma `update`로 메타데이터만 고친다 |
| 원인3 | 백그라운드 `vg index`가 세션마다 실패 | 한 컬렉션 33,065개 > SQLite 변수 한도 32,766. 로그에 같은 오류 9회, 실패 run 26개 | 매니페스트를 우리 SQLite에 두거나, 최소한 `get(limit, offset)`으로 페이지 단위 조회. 실패 시 재시도 간격 기록 |
| 원인4 | 실행마다 고정 비용 | generation 복사 647MB 쓰기, 전체 파일 파싱, 그래프 전체 재조정 (5개 문서 변경에 엔티티 25,998개 upsert) | APFS clone(`clonefile`), mtime+size 사전 검사, 변경 문서 단위 그래프 재조정 |
| 원인5 | 임베딩 메모리 21.2GB | 경로 순서 배치 133개 전부가 최대 길이 500 토큰 이상으로 패딩됨. 패딩 토큰이 실제의 4.5배 | 길이 정렬 + 토큰 예산 배치, 배치마다 저장(스트리밍), CPU 메모리 아레나 끄기 또는 축소 |

## 2. 원인1: 세션 기록의 비용 (정량화만)

활성 generation `metadata.sqlite3`에서 직접 셌다.

- 전체 청크 34,008개, 문서 514개. Vault별: vault-graph 18,191, sgp-981-app 7,693, personal 3,710, vault-builder 2,876, bake 1,147, 981park-flutter-app 391.
- `raw/sessions/` 아래 청크: vault-graph 17,787 (17개 파일), sgp-981-app 7,302 (11개 파일), vault-builder 2,485 (6개), bake 756 (8개). 합계 28,330개 = 83%.
- 앞선 조사의 "26,124 중 15,273"은 이전 시점 수치다. 지금은 세션 파일이 더 늘었다.
- 파일 하나가 최대 5,541 청크다 (`raw/sessions/claude-code/2026-10-29-3613510c-...-part1.md`). 상위 13개가 전부 세션 파일이다.
- XLM-R 계열 토크나이저(설치된 `paraphrase-multilingual-MiniLM-L12-v2`의 `tokenizer.json`, e5-small과 같은 계열로 추정)로 실제 임베딩 입력(`passage: ` + 섹션 경로 + 본문)을 셌다. 전체 3,863,469 토큰 중 세션이 2,881,662 토큰 (74.6%).
- 결론: 임베딩 시간과 메모리의 약 3/4이 세션 기록에서 나온다. 원인2와 겹치면 세션 파일에 한 줄 추가할 때마다 그 파일 청크 수천 개가 다시 임베딩된다.

## 3. 원인2: 문서 단위 재임베딩

### 3.1 청크 ID는 텍스트를 뒤에 덧붙여도 유지된다

- 청크 ID = `stable_id("chunk", CHUNKER_VERSION, vault_id, path, boundary_key)` (`src/vault_graph/indexing/ingestion/document_normalizer.py:52-60`).
- `boundary_key`는 첫/마지막 조각의 block key, unit key, 조각 수로 만든다 (`src/vault_graph/indexing/ingestion/document_chunking.py:211-224`).
- block/unit key는 내용 + 섹션 경로 + 앞에서 나온 같은 내용의 순번이다 (`src/vault_graph/indexing/ingestion/markdown_parser.py:320-351`). 위치 번호가 아니므로 뒤에 추가된 내용은 앞쪽 키를 바꾸지 않는다.
- 실측: sgp-981-app 세션 파일(331KB)을 70% 지점의 `## ` 앞에서 잘라 청크를 만들고 전체 파일과 비교했다. 앞부분 710개 청크가 전체 1,118개 안에 boundary_key와 텍스트까지 모두 같게 들어 있었다 (710/710). 마지막 섹션이 계속 커지는 경우에만 마지막 청크 하나가 바뀐다.

### 3.2 그런데 바뀐 문서의 모든 청크가 다시 임베딩된다

1. 메타데이터 적용은 바뀐 문서의 청크를 전부 지우고 새 `index_revision`으로 다시 넣는다 (`src/vault_graph/storage/local/sqlite_metadata_store.py:148-262`, 특히 `DELETE FROM chunks` 213-216, 청크 INSERT 222-249).
2. 벡터 지문에 `chunk.index_revision`이 들어간다 (`src/vault_graph/indexing/vector_index_adapter.py:343-353`). 저장된 쪽은 `metadata_index_revision` (`src/vault_graph/indexing/vector_index_adapter.py:356-366`).
3. 그래서 내용 해시가 같은 청크도 지문이 달라져 upsert 대상이 된다 (`src/vault_graph/indexing/vector_index_adapter.py:119-176`). 1,118 청크 파일에 400개를 덧붙이면 1,118개를 모두 임베딩한다.
4. 같은 구조로 `source_role`과 `provenance_family_id`도 지문에 들어 있다 (`src/vault_graph/indexing/vector_index_adapter.py:343-353`). 새 페이지가 `supersedes`로 기존 문서를 묶으면 `assign_provenance_families`(`src/vault_graph/indexing/ingestion/document_authority.py:46`)가 family를 바꾸고, family 구성원 문서의 청크가 전부 재임베딩된다. 임베딩 벡터는 이 값들과 무관하다.

### 3.3 근본 수정

- 계획 단계에서 두 가지를 따로 비교한다.
  - 임베딩 키: `(embedding spec, sha256(contextual_embedding_text))`. 이 키가 다를 때만 임베딩한다. `contextual_embedding_text`는 섹션 경로를 포함한다 (`src/vault_graph/indexing/ingestion/document_chunking.py:139-145`). 그래서 키는 `content_hash`가 아니라 실제 입력 텍스트로 만들어야 한다.
  - 메타데이터 지문: `index_revision`, `source_role`, family, 스키마 버전. 이것만 다르면 Chroma `collection.update(ids, metadatas)`로 메타데이터만 고친다. 임베딩은 하지 않는다.
- `index_revision`은 "언제 기록했는지" 값이므로 내용 동일성 비교에 넣지 않는다. 검색 결과의 출처 추적에 필요하면 메타데이터로만 갱신한다.
- 기대 효과: 세션 파일 덧붙이기의 재임베딩량이 파일 전체에서 새 청크 + 마지막 청크 1개로 줄어든다. 위 예에서 1,118개 → 약 409개. 실행이 반복될수록 차이는 커진다.

## 4. 원인3: 백그라운드 `vg index`가 매번 실패

### 4.1 실패 지점과 원인

- 로그 `$HOME/.vault-graph/logs/session-start-index.log`: 같은 traceback이 9번, 마지막 줄은 모두 `InternalError ... too many SQL variables`.
- 호출 경로: `VectorIndexer.apply` → `plan` (`src/vault_graph/indexing/vector_index_adapter.py:178-179`) → `_manifest_for_scopes` (`src/vault_graph/indexing/vector_index_adapter.py:267-272`) → `ChromaVectorStoreAdapter.export_manifest` (`src/vault_graph/storage/local/vector_store_adapter.py:131-137`) → `ChromaStore.export_manifest`의 `collection.get(include=["metadatas"])` (`packages/vector-search/src/vector_search/chroma_store.py:285-304`, 298행).
- `plan` 호출이 `try` 바깥에 있다 (`src/vault_graph/indexing/vector_index_adapter.py:178-197`). 그래서 벡터 실패가 `VectorApplyResult(failed=True)`가 되지 않고 `vg index` 전체를 중단시킨다.
- chromadb 버전: `uv.lock`의 `chromadb 1.5.9` (`uv.lock:443-444`). 설치된 onnxruntime 1.26.0, fastembed 0.8.0.
- 컬렉션 크기 (활성 generation `vector/chroma/chroma.sqlite3`, 읽기 전용 조회):
  - `vault_graph_c51adb...` (e5-small): 33,065개
  - `vault_graph_15e74f...` (MiniLM, 옛 모델): 391개
- SQLite 3.32.0 이후 기본 바인딩 변수 한도는 32,766이다. 33,065는 이 한도를 넘고 391은 넘지 않는다. limit 없는 `get`이 Rust 쪽에서 ID 전체를 한 문장의 변수로 묶는 것으로 추정한다 (Chroma Rust 내부 코드는 확인하지 않았다. 숫자 일치만 확인했다).
- 같은 원인으로 이 컬렉션은 앞으로 32,766개를 넘는 한 계속 실패한다. 세션 파일이 늘수록 커지므로 저절로 풀리지 않는다.

### 4.2 끝없는 재시도

- 세션 시작 hook은 변경 스캔 직후 분리된 프로세스를 띄운다 (`src/vault_graph/interface/cli/hook_commands.py:162-210`). 이 프로세스는 Vault마다 `vg index --vault-id`를 돌린다 (`src/vault_graph/interface/cli/hook_commands.py:214-237`).
- 다시 돌릴지 판단하는 `vectors_need_catch_up`은 `read_only=True` 저장소를 쓴다 (`src/vault_graph/interface/composition/recall_index_refresh.py:356-397`). 읽기 전용 경로는 Chroma 클라이언트가 아니라 SQLite를 직접 읽는 `ChromaSQLiteReader.export_manifest`를 쓴다 (`packages/vector-search/src/vector_search/sqlite_reader.py:102-131`, 분기는 `packages/vector-search/src/vector_search/chroma_store.py:286-287`). 그래서 검사는 성공하고 "stale 있음"을 반환한다.
- 실제 쓰기 경로만 실패하므로 다음 세션에서도 똑같이 다시 시작한다. 재시도 간격이나 실패 횟수 기록이 없다. flock(`src/vault_graph/interface/cli/hook_commands.py:181-187`)은 동시 실행만 막는다.
- 피해: `$HOME/.vault-graph/runs`에 실패 run 26개 (전체 73개). 실패마다 generation 복사(647MB 쓰기)와 메타데이터 전체 적용을 한 뒤 버린다. 활성 generation의 `vector/manifest.json`은 `vector-20261105010817282382`(10:12)에 멈춰 있고, 이후 bundle은 graph와 metadata만 담는다 (`bundle-manifest.json`). 즉 오늘 10:12 이후 새 세션 기록은 벡터 검색에 들어가지 않았다.

### 4.3 근본 수정

1. 매니페스트를 Chroma에서 다시 읽지 않는다. 벡터 매니페스트(vector_id, vault_id, chunk_id, 임베딩 키, 메타데이터 지문)를 우리 SQLite 테이블에 두고 Chroma 쓰기와 같은 run에서 갱신한다. 매니페스트 조회가 Chroma 크기와 버전에 묶이지 않는다. 범위 필터도 SQL `WHERE vault_id IN (...)`로 한다. 지금은 scope마다 모든 컬렉션의 모든 행을 읽고 Python에서 거른다 (`src/vault_graph/storage/local/vector_store_adapter.py:133`).
2. 단기 수정: `export_manifest`에서 `collection.get(include=["metadatas"], limit=N, offset=k)`를 페이지 단위로 반복한다. N은 `_max_batch_size`(`packages/vector-search/src/vector_search/chroma_store.py:29-40`)와 같은 5,000 수준이면 충분하다. 또는 쓰기 모드에서도 `ChromaSQLiteReader`로 읽는다.
3. 재시도 제어: 실패한 `(vault_id, 오류 요약)`과 시각을 `logs/`에 기록하고, 같은 오류면 지수 간격으로만 다시 시도한다. hook 출력에 "벡터 인덱스가 N시간째 실패 중" 경고를 한 줄 낸다.
4. `plan` 실패도 `VectorApplyResult(failed=True)`로 처리해 메타데이터와 그래프는 게시되게 한다. 이 경우 벡터 stale 상태가 status에 보이도록 한다.

## 5. 원인4: 실행마다 드는 고정 비용

| 항목 | 위치 | 측정 |
|---|---|---|
| generation 전체 복사 | `src/vault_graph/indexing/publication/projection_generation.py:75-107` (`shutil.copytree` 96행) | 크기 663MB (graph 293MB, chroma 185MB+, metadata 92MB). 캐시가 데워진 상태에서 Python `copytree` 0.06초, 디스크 사용 647MB 증가. `cp -cR`(clone) 0초, 증가 0MB |
| 세션 시작 빠른 갱신도 같은 복사 | `src/vault_graph/interface/composition/recall_index_refresh.py:295-312` | `quick-refresh-times.json`: personal+vault-graph 15.4~16.0초 |
| 모든 파일 읽기와 파싱 | `src/vault_graph/indexing/metadata_indexer.py:161-201` (`_build_plan`, `_load_normalized`) | 비교 기준은 파싱 결과의 `content_hash` (`src/vault_graph/indexing/metadata_indexer.py:204-218`). 파일 크기/mtime 사전 검사 없음 |
| 그래프 전체 재조정 | `src/vault_graph/indexing/graph_indexer.py:98-130`, `src/vault_graph/indexing/graph_indexer.py:244-300`, `src/vault_graph/indexing/index_service.py:215-245` 문서 주석 | `vg index --dry-run --vault-id vault-graph`: 변경 문서 5개인데 엔티티 25,998, 관계 17,649, 근거 58,891 upsert, stale 41,215 |

- `vg index --dry-run --vault-id vault-graph` 전체: 9.97초, 최대 RSS 479MB. dry-run은 읽기 전용 저장소를 쓰므로 원인3 오류가 나지 않는다 (`src/vault_graph/interface/cli/main.py:617-629`).
- 복사 시간 자체는 캐시가 데워져 있으면 1초 미만이다. 비용은 시간보다 실행마다 650MB를 새로 쓰는 것이다. 보존 generation 3개가 1.9GB를 차지하고, 원인3 때문에 실패 run마다 이 쓰기가 반복된다. 캐시가 식은 상태의 시간은 재지 않았다.
- 그래프 재조정이 전체인 이유: scope의 모든 청크에서 엔티티를 다시 뽑고 (`src/vault_graph/indexing/graph_indexer.py:244-273`), scope 리비전을 모든 청크의 `index_revision`으로 만든다 (`src/vault_graph/indexing/graph_indexer.py:285-299`). 문서 하나만 바뀌어도 scope 전체가 stale이 된다.

근본 수정:
1. generation 준비를 `clonefile`(macOS, `cp -c`와 같음)로 한다. 지원하지 않는 파일시스템이면 지금의 `copytree`로 되돌아간다. SQLite 파일은 쓰기 시점에 블록 단위로만 복사되므로 정확성은 유지된다.
2. 파일 목록 단계에서 `(size, mtime_ns)`가 저장값과 같으면 읽지 않는다. 다르면 지금처럼 해시로 확정한다. 문서 테이블에 두 컬럼이 필요하다.
3. 그래프는 바뀐 문서의 근거(evidence)만 지우고 다시 뽑는다. 엔티티/관계는 근거 참조 수로 유지하고 0이 되면 삭제한다. scope 리비전은 문서별 리비전의 집합 해시가 아니라 run 단위로 기록한다.

## 6. 원인5: 임베딩 메모리

### 6.1 코드 경로

- `VectorIndexer.apply`가 upsert 전체를 임베딩한 뒤 한 번에 쓴다 (`src/vault_graph/indexing/vector_index_adapter.py:178-197`, `src/vault_graph/indexing/vector_index_adapter.py:199-227`). `embed_items`는 결과를 dict에 모두 모은다 (`packages/vector-index/src/vector_index/indexing.py:129-160`).
- 벡터 결과는 Python float 튜플이다 (`packages/text-embeddings/src/text_embeddings/fastembed_provider.py:45-63`). 33,000 × 384 float이면 수백 MB 수준이라 21GB의 주원인은 아니다 (추정).
- 배치 기본값 256, `parallel=None` (`src/vault_graph/interface/composition/adapters/text_embeddings.py:99-100`). fastembed는 `parallel=None`이면 같은 프로세스에서 돈다 (`.venv` fastembed 0.8.0 `fastembed/text/onnx_text_model.py:128-133`). 0이나 양수면 `forkserver`로 워커마다 모델을 따로 올린다 (같은 파일 136-158행). 현재 설정에서는 프로세스 증식이 원인이 아니다.
- fastembed 토크나이저는 길이를 정하지 않은 `enable_padding`을 쓴다 (`fastembed/common/preprocessor_utils.py:51-55`). 배치 안에서 가장 긴 입력 길이로 패딩되고, 최대 길이는 모델 설정(512)로 자른다.
- 청크 순서는 `(vault_id, path, chunk_id)`이다 (`src/vault_graph/indexing/vector_index_adapter.py:331-332`). 같은 파일의 청크가 한 배치에 몰리고, `chunk_id`는 해시라서 그 안의 길이는 무작위로 섞인다.

### 6.2 측정 (전체 34,008 청크, 토큰 수는 512로 자름)

- 토큰 길이: 평균 113.6, 중앙값 51, p95 507, 512에 걸리는 청크 1,656개. 청크 상한은 단어 256개 (`src/vault_graph/indexing/ingestion/document_chunking.py:11`)인데, 한국어와 코드가 섞이면 토큰은 512를 넘는다.
- 경로 순서 배치 256개: 배치 133개 전부가 최대 길이 500 이상. 패딩 포함 토큰 17,412,096 = 실제의 4.5배.
- 길이로 정렬한 배치: 3,927,552 토큰 (실제의 1.02배). 어텐션 비용(길이² 합) 비율은 경로 순서가 정렬의 8.2배.
- 배치 256 × 길이 512의 어텐션 점수 텐서 하나가 256×12×512×512×4B ≈ 3.2GB다. ONNX Runtime CPU 아레나는 한 번 늘어난 메모리를 돌려주지 않는다. 21.2GB 최대 RSS는 이 둘의 결과로 추정한다.

### 6.3 근본 수정

1. 길이 정렬 + 토큰 예산 배치: 임베딩 전에 토큰 길이(또는 문자 수)로 정렬하고, `배치 수 × 배치 안 최대 길이 ≤ 예산`(예: 16,384 토큰)으로 배치를 자른다. 짧은 청크는 큰 배치, 긴 청크는 작은 배치가 된다. 계산량 약 4.4배 감소, 최대 메모리는 예산으로 묶인다.
2. 배치마다 저장: `embed_items`를 반복자로 바꾸고 배치마다 Chroma `upsert`와 매니페스트를 갱신한다. 메모리는 배치 하나로 묶이고, 중간에 죽어도 끝난 배치는 남아 다음 실행이 이어서 한다. staging generation 안에서 쓰므로 게시 원자성은 그대로다.
3. 아레나: fastembed가 노출하는 `enable_cpu_mem_arena=False`를 `extra_session_options`로 넘긴다 (`fastembed/common/onnx_model.py:28`, `fastembed/common/onnx_model.py:156-157`). 지연 시간이 조금 늘 수 있으므로 1번과 함께 측정해서 정한다.
4. 기본 배치 256은 1번이 들어가면 의미가 바뀐다. 설정을 "최대 토큰 예산"으로 바꾸는 것을 권한다.

## 7. 인덱싱 가속 선택지

| 코드 | 선택지 | 기대 효과 | 위험 | 작업량 |
|---|---|---|---|---|
| 가속1 | 길이 정렬 + 토큰 예산 배치 (6.3-1) | 임베딩 계산 약 4.4배 감소 (측정 기반), 메모리 상한 고정 | 거의 없음. 결과 순서만 원래대로 되돌리면 됨 | 작음 |
| 가속2 | 임베딩 캐시 `(모델 spec, 입력 텍스트 해시) → 벡터`를 generation 밖 SQLite에 보관 | 원인2 수정과 합치면 재임베딩이 진짜 새 텍스트로 한정. full 재인덱스, generation 재생성, rollback 후 재실행이 거의 무료 | 캐시 크기 증가(384차원 float32 기준 청크당 1.5KB, 34k면 약 52MB). 모델 버전이 키에 반드시 들어가야 함 | 중간 |
| 가속3 | 원인2 수정 (메타데이터만 바뀌면 `update`) | 세션 덧붙이기마다 수천 개 재임베딩 제거 | Chroma `update` 동작 테스트 필요 | 중간 |
| 가속4 | APFS clone으로 generation 준비 | 실행당 650MB 쓰기 제거, 보존 generation 디스크 공유 | 비 APFS 환경 분기 필요 | 작음 |
| 가속5 | `(size, mtime_ns)` 사전 검사 | 바뀌지 않은 파일의 읽기/파싱 생략. 전체 파일 수가 적어(Vault당 40~64개 md) 지금 이득은 수 초 수준 (추정) | mtime을 보존하는 복사에서 놓칠 수 있음. full 모드는 그대로 해시 | 작음 |
| 가속6 | 변경 문서 단위 그래프 재조정 | dry-run 기준 5개 문서 변경에 엔티티 26k upsert → 변경 문서 몫만. 그래프 293MB 재작성 감소 | 문서 사이 관계(링크 해석, family)의 정확성 검증이 필요. 가장 위험이 큰 항목 | 큼 |
| 가속7 | CoreML 실행 제공자 (Apple Silicon) | 추정 2~5배. 이 저장소 모델로 측정한 적 없음 | int8 양자화 모델은 CoreML에서 CPU로 되돌아갈 수 있음. 동적 shape 지원 제한. 결과 벡터가 CPU와 미세하게 달라 같은 모델 공간인지 판단 필요 | 중간 |
| 가속8 | 양자화 모델 | 이미 int8 사용 중 (`embedding_spec_version`이 `...-int8-...`, `vector/manifest.json`) | 추가 이득 없음 | 없음 |
| 가속9 | `max_length` 상한 축소 (예: 256 토큰) | 어텐션 비용이 긴 청크에서 4배 감소 | 청크 상한(단어 256)과 맞지 않아 뒷부분이 잘림. 청크 상한을 토큰 기준으로 바꾸는 것이 먼저 | 중간 |
| 가속10 | Chroma 대신 sqlite-vec 또는 LanceDB | 매니페스트, 메타데이터, 벡터를 한 SQLite에 두면 원인3 같은 문제 종류가 사라지고 복사/clone이 단순해짐 | 검색 경로 전체 교체, 마이그레이션, ANN 성능 재측정 필요. 34k 규모에서는 sqlite-vec 전수 검색도 충분할 것으로 추정 | 큼 |
| 가속11 | fastembed `parallel` | CPU 코어 수만큼 처리량 증가 가능 | 워커마다 모델과 아레나를 따로 올려 메모리가 워커 수만큼 늘어남. 가속1 이후에만 검토 | 작음 |

권장 순서: 원인3 수정(벡터가 지금 갱신되지 않음) → 가속1 + 배치마다 저장 → 원인2/가속3 → 가속2 → 가속4 → 가속6. 가속7과 가속10은 측정 후 별도 결정.

## 8. 외부 자료

- SQLite 한도 문서, https://www.sqlite.org/limits.html : 한 문장에 묶을 수 있는 변수의 기본 최대값은 3.32.0부터 32,766이다.
- Chroma 이슈 #1693, https://github.com/chroma-core/chroma/issues/1693 : 큰 컬렉션에 limit 없는 `get()`을 부르면 SQLite 오류가 나는 사례. 원인 확정은 스레드에 없다.
- Chroma 페이지네이션 문서, https://docs.trychroma.com/cloud/search-api/pagination-selection : `limit`/`offset`으로 결과를 나눠 받는 방법.
- ONNX Runtime 이슈 #11627, https://github.com/microsoft/onnxruntime/issues/11627 : CPU 아레나를 켜면 입력 shape가 바뀔 때 메모리가 수 GB까지 늘고, 끄면 해결되지만 지연이 늘 수 있다는 보고.
- ONNX Runtime v1.8.0 릴리스, https://github.com/Microsoft/onnxruntime/releases/tag/v1.8.0 : 실행 후 아레나의 사용하지 않는 메모리를 돌려주는 RunOption이 추가됐다. 가끔 큰 입력이 들어오는 동적 shape 모델용이다.
- ONNX Runtime CoreML 실행 제공자, https://onnxruntime.ai/docs/execution-providers/CoreML-ExecutionProvider.html : Apple 기기에서 CoreML로 일부 연산을 넘기는 제공자. 지원 연산과 shape 제약이 있다 (이 조사에서 페이지 내용은 다시 확인하지 않았다).

## 9. 측정 부산물

- `uv run`이 워크트리에 `.venv`를 만들었다 (git 무시 대상, `git status`에 나타나지 않음).
- `$HOME/.vault-graph/projections/generations/7f550e2294da4b408d804fa29e4f64df`는 19:17에 준비된 뒤 게시되지 않은 generation이다. 활성보다 청크가 918개 많다 (34,926개). 원인3 실패 run의 잔여물로 추정한다.
