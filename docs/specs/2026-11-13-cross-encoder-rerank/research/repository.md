# 저장소 근거

기준 커밋은 `40065d0`이다. 모델은 내려받지 않았고 Vault와 Graph Home에는 쓰지 않았다. 아래 블록 번호는 이 파일 안에서만 쓰고, 다른 파일이 X20부터 이어 쓴다.

## 검색 흐름과 재정렬 위치

### X1. 재정렬이 들어갈 자리
- source: src/vault_graph/retrieval/search/retrieval_service.py:139-181@40065d0
- basis:
`_search_request`는 키워드·벡터·그래프 후보를 모아 `fuse_candidates`로 합치고, `EvidenceResultAssembly.resolve_results`로 문서(또는 세션 교환) 단위 결과를 만든다(162-169). 그 뒤 refill 판단(170-173)이 끝나면 `results[: request.limit]`로 자르고 `_expand_context`에 넘긴다(177-181).
재정렬은 refill 루프가 끝난 174행 뒤, 178행의 slice 앞에서 `results` 전체(또는 상위 N개)를 다시 정렬하면 된다. 이 자리라면 refill 판단과 `_expand_context`(자른 결과만 처리)는 바뀌지 않는다.

### X2. 후보 수 공식과 refill 규칙
- source: src/vault_graph/retrieval/search/retrieval_service.py:47-52,140,170-173,196-206@40065d0
- basis:
신호마다 후보 수는 `max(limit * 4, 20)`이다(`CANDIDATES_PER_RESULT=4`, `MIN_CANDIDATES=20`). 문서 결과가 `limit`보다 적고 키워드나 벡터 목록이 꽉 찼을 때만(`saturated`) 후보 수를 4배로 늘려 한 번 더 돈다.
`stage_trace`의 `document_ranks`는 slice 전 `results` 전체로 만든다(200행). 그래서 재정렬을 slice 앞에 넣으면 trace도 재정렬 뒤 순위를 기록할지 정해야 한다.

### X3. RetrievalResult가 가진 텍스트
- source: src/vault_graph/retrieval/search/retrieval_result.py:65-84@40065d0; src/vault_graph/retrieval/search/evidence_result_assembly.py:115,267-282,533-545@40065d0
- basis:
`RetrievalResult`의 텍스트 필드는 `title`과 `summary`뿐이다. `title`은 페이지 frontmatter title이 아니라 `path#anchor` 또는 `path#section` 또는 `path`다(`_title_for_evidence`). `summary`도 frontmatter summary가 아니라 가장 높은 조각 본문을 공백을 접어 240자로 자른 발췌다(`_excerpt`, 115행).
즉 결과 객체만으로는 조각 전문, 페이지 title·summary·aliases를 얻을 수 없다. 재정렬 입력으로 쓰기엔 240자 발췌와 경로뿐이다.

### X4. 전문은 resolve_results 안에 이미 있다
- source: src/vault_graph/retrieval/search/evidence_result_assembly.py:87-119,137-140@40065d0; src/vault_graph/storage/local/sqlite_metadata_store.py:593-611@40065d0
- basis:
`resolve_results`는 후보 조각마다 `resolve_chunk`(SQLite 한 행, `chunks`와 `content_blobs` join)와 `resolve_document`(문서 캐시)를 이미 부른다. 조각 전문은 지역 변수 `chunks`에, frontmatter는 `documents`에 담기지만 반환하지 않고 버린다.
결과 밖에서 재정렬하면 결과마다 `resolve_chunk`를 다시 불러야 한다(결과당 SQLite 질의 1회). 재정렬을 `resolve_results` 안 그룹 단계(`_ParentGroup.chunk`, `.document`)에 두거나 텍스트를 함께 돌려주면 추가 읽기가 없다.

### X5. 지금의 문서 순위 계산
- source: src/vault_graph/retrieval/search/evidence_result_assembly.py:118-128,310-354@40065d0
- basis:
조각을 `parent_key`(세션 교환) 또는 `document_id`(문서)로 묶고, 묶음 점수는 `document_score(조각 fused 점수)`에 title 신호를 더해 모드별 역할 가중치를 곱한다. 이 점수로 정렬한 뒤 대체 페이지 접기, 세션 사본 접기, 중복 내용 접기를 거쳐 `rank`를 1부터 매긴다.
`rank`와 `result_id`(`...:rank-N`, 268행)가 결과 생성 때 정해지므로, 결과 뒤에서 재정렬하면 둘 다 다시 매겨야 한다.

### X6. slice 전 문서 결과 수
- source: src/vault_graph/interface/mcp/mcp_tools.py:92,103,116@40065d0; src/vault_graph/context/pack/context_pack.py:13@40065d0; tests/benchmarks/eval_scoring.py:29@40065d0; tests/benchmarks/measure_session_recall.py:34@40065d0
- basis:
MCP `ask_vault`, `search_vault`, `build_context_pack` 기본 `limit`은 10이라 신호마다 40개, 키워드와 벡터 합쳐 최대 80개 조각이 후보다. 평가 도구는 `limit=20`으로 불러 신호마다 80개, refill 시 320개다. LongMemEval은 `--limit 5`라 20개다.
조각이 문서로 접히므로 문서 결과 수는 이보다 적다. 평소 몇 개인지 잰 기록은 저장소에 없다. 상한은 후보 조각 수이고 하한은 refill 조건(`limit`보다 적고 목록이 꽉 참)으로만 정해진다.

### X7. 세션 검색도 같은 경로다
- source: src/vault_graph/retrieval/search/retrieval_service.py:53-69@40065d0; src/vault_graph/retrieval/search/evidence_result_assembly.py:142-186,325-334@40065d0; src/vault_graph/indexing/ingestion/session_exchange_v2_chunker.py:37-42@40065d0
- basis:
세션 교환은 `raw_evidence` 역할이라 `evidence` 모드(그리고 `all`)에서 같은 `_search_request`로 검색된다. 별도 세션 검색 경로는 없다. 조각은 `parent_key`로 교환 하나에 묶이고, 결과는 교환 전체 위치를 근거로 가리키되 가장 높은 창 하나를 인용한다.
재정렬 모델이 받을 세션 텍스트는 그 창(약 96 단어, `SESSION_WINDOW_MAX_TOKENS=96`)이고 결과의 `summary`는 그 창의 240자 발췌다. 교환 전체 텍스트를 쓰려면 같은 `parent_key`의 창들을 따로 읽어야 한다. 지금 `_exchange_signature`는 해시만 읽는다.

### X8. 문서 조각 크기
- source: src/vault_graph/indexing/ingestion/wiki_page_chunker.py:1-18,38-42@40065d0; src/vault_graph/indexing/ingestion/document_snapshots.py:38@40065d0; src/vault_graph/indexing/ingestion/document_chunking.py:12@40065d0
- basis:
wiki 페이지는 약 160 단어 본문 창, 템플릿 조각, frontmatter로 만든 `page_card` 조각 하나로 나뉜다. 일반 문서는 256 토큰 창이다.
따라서 결과의 "가장 높은 조각"이 page_card라면 재정렬 입력은 title·summary·aliases 위주가 되고, 본문 창이라면 본문 160 단어다. 재정렬 입력을 무엇으로 할지(가장 높은 조각, page_card+본문 등)는 설계에서 정해야 한다.

## 임베딩 모델 구성

### X9. 모델 preset 목록
- source: src/vault_graph/interface/composition/adapters/text_embeddings.py:24-108@40065d0
- basis:
`EmbeddingPreset`은 이름, Hugging Face repo, 고정 revision, 내려받을 파일 목록, fastembed 등록 방식(`builtin`/`custom`), ONNX 파일, pooling, 최대 토큰, 내려받기 크기, 접두사를 가진다. `EMBEDDING_PRESETS`에 `e5-small`과 `arctic-m`이 있고 기본은 `arctic-m`이다.
주석대로 모델을 더하려면 이 목록에 항목 하나를 더한다. 재정렬 모델도 같은 모양(고정 revision, 파일 목록, 크기)으로 적는 것이 기존 방식과 맞다.

### X10. 모델 적재 순서
- source: src/vault_graph/interface/composition/adapters/text_embeddings.py:145-164,252-265,282-330@40065d0
- basis:
`text_embeddings_for`가 `configs/embedding.json`을 읽어 preset을 고르고 설정 객체를 만드는 유일한 곳이다. 적재는 `huggingface_hub.snapshot_download`(고정 revision, `allow_patterns`, `local_files_only`)로 스냅숏 폴더를 찾은 뒤 fastembed `TextEmbedding(specific_model_path=...)`를 만든다.
`custom` preset은 프로세스당 한 번 잠금 아래 `TextEmbedding.add_custom_model`로 등록한다. 적재는 기본 lazy라 첫 `embed` 때 일어난다.

### X11. 모델 파일 위치와 설정 파일
- source: src/vault_graph/operation/scope/embedding_selection.py:1,19-24,33-41@40065d0; src/vault_graph/operation/scope/catalog_service.py:21@40065d0; 명령 `ls ~/llm/models`
- basis:
모델 폴더 기본값은 `~/llm/models`이고 Graph Home `configs/embedding.json`(키 `version`, `model`, `models_dir`)이 바꿀 수 있다. 파일이 없으면 기본 preset과 기본 폴더를 쓴다.
지금 `~/llm/models`에는 `models--Snowflake--snowflake-arctic-embed-m-v2.0`만 있다. 재정렬 모델은 내려받지 않은 상태다. 재정렬 설정을 같은 파일에 넣을지 새 파일로 둘지는 정해지지 않았다.

### X12. 검색은 내려받지 않는다
- source: src/vault_graph/interface/composition/read_only_service_factory.py:445-448@40065d0; src/vault_graph/interface/cli/main.py:314-319@40065d0
- basis:
검색용 임베딩은 `local_files_only=True`로 만든다(MCP·HTTP의 읽기 전용 팩토리와 CLI `_search_text_embeddings`). 색인용(`_text_embeddings`)만 `local_files_only=False`라 내려받을 수 있다.
재정렬도 검색 경로이므로 같은 규칙(`local_files_only=True`)을 따라야 한다. 내려받기는 `vg embedding use`처럼 명시 명령에서만 한다.

### X13. 모델 없음이 경고가 되는 길
- source: src/vault_graph/interface/composition/adapters/text_embeddings.py:203-208@40065d0; src/vault_graph/operation/readiness/search_readiness_service.py:93-102@40065d0; src/vault_graph/retrieval/search/retrieval_service.py:332-347,382-388,429-449@40065d0
- basis:
준비 상태 검사가 `can_embed_without_download()`(local_files_only로 스냅숏 확인)를 부르고, 거짓이면 `embedding_model_unavailable`과 `degraded_keyword_only` 경고를 붙여 키워드만으로 답한다. 질의 임베딩이 실패하면 `TextEmbeddingsError`를 잡아 `vector_query_failed` 경고를 붙인다.
재정렬도 이 모양(모델 확인 → 실패 시 재정렬 없이 답하고 경고 코드 하나)을 따르면 작업 21 done-when의 "모델이 없으면 재정렬 없이 답하고 경고"와 맞는다.

### X14. fastembed 0.8.0의 교차 인코더 지원
- source: .venv/lib/python3.12/site-packages/fastembed/rerank/cross_encoder/onnx_text_cross_encoder.py:18-62,86-145,159-198; .venv/lib/python3.12/site-packages/fastembed/rerank/cross_encoder/text_cross_encoder.py:136-156; docs/specs/2026-11-11-search-and-memory-quality-2/spec.md:147-152@40065d0; docs/ARCHITECTURE.md:206@40065d0
- basis:
설치된 fastembed 0.8.0에는 `TextCrossEncoder`가 있고 `rerank`, `rerank_pairs`, `add_custom_model`, `specific_model_path`, `lazy_load`를 받는다. 기본 목록은 ms-marco MiniLM(영어), `BAAI/bge-reranker-base`, jina v1(영어), `jina-reranker-v2-base-multilingual`(cc-by-nc-4.0)이다.
spec 4.2.3은 후보를 `bge-reranker-v2-m3`(Apache-2.0)로 두고 직접 등록해야 한다고 적었다. ARCHITECTURE는 제공자·모델 경로·오프라인 정책의 구체 구성을 `interface/composition/adapters/`에 둔다. 재정렬 구현도 포트는 retrieval 쪽, fastembed 연결은 adapters에 두는 것이 기존 구조다.

## 평가 도구

### X15. 층1과 검색 p95
- source: tests/benchmarks/evaluate_search.py:1-17,101-128,164-179,206-211,240-247@40065d0; docs/specs/2026-11-11-search-and-memory-quality-2/tasks/7-s3b-layer1-questions.md:13@40065d0; docs/design/reports/2026-11-single-query-options.md:70-72@40065d0
- basis:
명령은 `uv run --python 3.12 --all-packages --all-extras python -m tests.benchmarks.evaluate_search --questions <q.json> --graph-home <복사본> --out-dir <밖> [--split dev|test] [--vault-id ...]`이다. 기본 Graph Home은 거부하고, 층1 질문 파일과 출력은 저장소 밖이어야 한다. 층1 질문 원문은 저장소에 없고 세션 임시 폴더에 있다.
읽기 전용 팩토리로 서비스를 열고, 모델을 올리는 untimed 검색 한 번 뒤 문항마다 `limit=20`, `trace=True`로 한 번 검색한다. `RetrievalService.search` 벽시계 시간으로 p50·p95를 `summary.json`에 적는다(목표8의 측정값).

### X16. 층2와 비교 도구
- source: tests/fixtures/eval_layer2/README.md:12-40@40065d0; tests/benchmarks/compare_search_eval.py:1-23@40065d0; tests/fixtures/eval_layer1_baseline/all/summary.json@40065d0
- basis:
층2는 저장소 안 가상 Vault(`tests/fixtures/eval_layer2/vault`)와 `questions.json`(210문항, 채점 180)이다. 새 Graph Home에 `vg init --vault-id eval2`, `vg index` 뒤 `evaluate_search --vault-id eval2`로 돈다.
`compare_search_eval --baseline <dir> --current <dir>`가 두 실행의 종류별 recall@5·recall@10·MRR과 문항별 좋아짐·나빠짐을 센다. 채택 규칙은 층1 test split 개선, 층3 1점 이내, 목표4·5 유지다. 저장소의 층1 기준값은 숫자만 있다.

### X17. 순위 손실과 후보 손실의 정의
- source: tests/benchmarks/eval_scoring.py:9-13,59-109@40065d0
- basis:
`hit`은 첫 정답이 5위 안, `rank_loss`는 적중이 아니지만 정답 조각이 어떤 신호의 후보 목록에 있음, `candidate_loss`는 어느 신호에도 없음이다. `results.jsonl`에 문항별 `keyword_rank`, `vector_rank`, `fused_rank`, `document_rank`, `final_rank`, `outcome`이 남는다.
평가는 `limit=20`이라 신호 목록이 80개(refill 시 320개)다. 그래서 `rank_loss`에는 상위 30~50 문서 재정렬로 닿지 않는 깊은 순위도 섞인다. 재정렬 대상 판정에는 `document_rank`(slice 전 문서 순위)를 함께 봐야 한다.

### X18. LongMemEval과 켜고 끄기 비교
- source: tests/benchmarks/longmemeval_run.py:1-29,383-392,424-452,507-512@40065d0; tests/fixtures/longmemeval_baseline.json@40065d0
- basis:
명령은 `python -m tests.benchmarks.longmemeval_run --data <longmemeval_s_cleaned.json> --vault-builder <checkout> --work-dir <빈 폴더> --out-dir <밖> [--limit 150]`이다. 문항마다 새 Graph Home을 `vg setup`으로 만들고 `vg search --mode evidence --limit 5`를 하위 프로세스로 부른다. 데이터 파일은 저장소 밖에서 받아야 한다.
지금 재정렬 설정이 없으니 켜고 끄기 비교는 코드 변경 없이는 안 된다. 재정렬이 Graph Home 설정을 읽게 만들면 층1·층2는 측정용 Graph Home 설정만 바꿔 `evaluate_search`와 `compare_search_eval`로 비교할 수 있다. LongMemEval은 매번 새 Graph Home을 만들므로 기본값을 바꾸거나 실행기에 설정을 넘기는 변경이 필요하다.

## 제약과 남은 실패

### X19. 재정렬이 지켜야 할 제약과 지금 남은 실패
- source: AGENTS.md:5-6,23-25@40065d0; docs/SPEC.md:32,59@40065d0; docs/ARCHITECTURE.md:266,274@40065d0; docs/DECISIONS.md:315-335,538-546@40065d0; docs/specs/2026-11-11-search-and-memory-quality-2/spec.md:73,193,277,302,323,325@40065d0; docs/specs/2026-11-11-search-and-memory-quality-2/tasks/21-s10a-reranker.md:30-34@40065d0; docs/design/reports/2026-11-single-query-options.md:3,48,58,134-172@40065d0
- basis:
제약: 로컬 우선, 일반 조회는 모델 내려받기를 하지 않음, 가져오기만으로 네트워크·모델 준비 금지, 모델이 없으면 다른 모델로 몰래 바꾸지 않고 경고와 함께 낮춘 결과, 테스트는 모델을 내려받지 않음. 목표8은 모델 적재 뒤 한 프로세스 p95 1초 이하이고 결정18·A-13은 남은 실패가 주로 6~30위 순위 손실이고 p95 1초 이하일 때만 넣게 한다. 최종 p95는 0.41초다.
남은 실패: arctic-m 최종 코드의 문항별 순위 손실·후보 손실 분류는 저장소에 없다. 8.3은 목표별 개수만, 8.4는 "지식 실패 12문항 중 7문항" 같은 집계만 있다. 저장소의 층1 손실 분류(순위 29, 후보 11)는 e5-small `08af575` 기준값이다.

### X40. 회상은 검색하지 않고, context pack은 검색을 거친다
- source: src/vault_graph/context/pack/recall.py:3@40065d0; src/vault_graph/context/pack/context_pack_builder.py:143@40065d0
- basis:
세션 시작 회상(`recall`)은 문서 메타데이터만 읽고 검색을 부르지 않는다고 모듈 설명에 적혀 있다. 그래서 재정렬은 회상 내용과 지연을 바꾸지 않는다.
`build_context_pack`은 `retrieval_service.search`를 부른다. 재정렬을 켜면 context pack 결과도 바뀌므로 목표4(`build_context_pack` 적중, 지금 0.92)도 재야 한다.
