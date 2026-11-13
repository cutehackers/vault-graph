# 재정렬 모델 조사

조사일은 2026-11-13이다. 모델 가중치는 내려받지 않았다. 웹 문서와 설치된 `fastembed` 0.8.0 소스(`.venv`)만 읽었다. 지연 시간 추정은 직접 측정한 값이 아니다.

### X20. bge-reranker-v2-m3 기본 정보
- source: https://huggingface.co/BAAI/bge-reranker-v2-m3 , https://huggingface.co/onnx-community/bge-reranker-v2-m3-ONNX/raw/main/config.json
- basis: X34
라이선스는 Apache-2.0이고 파라미터는 568M(0.6B)이다. 구조는 `XLMRobertaForSequenceClassification`이며 24층, hidden 1024, 출력 레이블 1개다.
모델 카드는 다국어를 지원한다고만 적고 언어 목록은 주지 않는다. 한국어 성능은 X34의 한국어 벤치마크에서 확인된다.
카드 예제와 학습 설정은 `max_length=512`를 쓴다. 토크나이저의 `model_max_length`는 8192이다.
파라미터 568M 중 약 256M은 250k 어휘 임베딩이다. 실제 연산량은 나머지 약 300M 인코더가 정한다(추정).

### X21. bge-reranker-v2-m3 ONNX 파일
- source: https://huggingface.co/api/models/onnx-community/bge-reranker-v2-m3-ONNX?blobs=true , https://huggingface.co/newtechstudio/bge-reranker-v2-m3-onnx , https://huggingface.co/onebrain-ai/onebrain-rerank-v1
- basis:
가장 많이 내려받힌 변환본은 `onnx-community/bge-reranker-v2-m3-ONNX`(약 9만 회)다. `onnx/model.onnx`는 657KB 그래프이고 가중치는 `onnx/model.onnx_data`(2.27GB)에 따로 있다. int8 단일 파일은 `onnx/model_int8.onnx`(571MB)이며 `model_quantized.onnx`와 크기가 같다.
newtechstudio 카드는 이 변환본의 배치 축이 8로 고정돼 있다고 주장한다. 직접 확인하지 못했다. 고정이라면 30쌍이 4번에 나뉘어 실행된다.
`onebrain-ai/onebrain-rerank-v1`은 같은 모델의 동적 int8(569MB, onnxruntime 1.27) 변환본이다. 입력은 `input_ids`와 `attention_mask`이고 출력 `logits`는 `[batch, 1]`이다. fp32 대비 시그모이드 점수 차이는 최대 0.0046이지만 검증 쌍이 5개뿐이다.

### X22. mmarco-mMiniLMv2-L12-H384-v1 기본 정보
- source: https://huggingface.co/cross-encoder/mmarco-mMiniLMv2-L12-H384-v1 , https://huggingface.co/api/models/cross-encoder/mmarco-mMiniLMv2-L12-H384-v1 , https://huggingface.co/cross-encoder/mmarco-mMiniLMv2-L12-H384-v1/raw/main/tokenizer_config.json
- basis:
라이선스는 Apache-2.0이고 파라미터는 약 118M이다. 기반 모델은 `nreimers/mMiniLMv2-L12-H384-distilled-from-XLMR-Large`이다. 12층, hidden 384라서 인코더 연산량은 bge-reranker-v2-m3의 약 1/14이다(추정).
학습 데이터 mMARCO는 14개 언어로 기계 번역됐고 태그 목록에 한국어가 없다. 한국어 능력은 XLM-R 계열 사전학습에서만 온다. 한국어 재정렬 품질은 확인된 수치가 없다.
`model_max_length`는 512이다. 토크나이저는 `XLMRobertaTokenizer`이다.

### X23. mmarco-mMiniLMv2-L12-H384-v1 ONNX 파일
- source: https://huggingface.co/api/models/cross-encoder/mmarco-mMiniLMv2-L12-H384-v1?blobs=true
- basis: X36
공식 저장소에 ONNX가 함께 있다. `onnx/model.onnx`(471MB, fp32)와 최적화 단계별 변형, int8 양자화 변형이 있다.
Apple Silicon용으로 `onnx/model_qint8_arm64.onnx`(119MB)가 따로 있다. x86용은 `model_qint8_avx512.onnx`, `model_quint8_avx2.onnx`이다.
fastembed가 요구하는 `config.json`, `tokenizer.json`, `tokenizer_config.json`, `special_tokens_map.json`도 같은 저장소에 있다. 따라서 `model_file`만 바꾸면 그대로 등록할 수 있다(X36).
arm64 int8 파일과 fp32 파일의 점수 차이를 잰 자료는 찾지 못했다.

### X24. gte-multilingual-reranker-base
- source: https://huggingface.co/Alibaba-NLP/gte-multilingual-reranker-base , https://huggingface.co/api/models/onnx-community/gte-multilingual-reranker-base?blobs=true , https://arxiv.org/html/2407.19669
- basis:
라이선스는 Apache-2.0이고 파라미터는 306M(논문 표기 304M)이다. 70개 이상 언어와 최대 8192 토큰을 지원한다고 적혀 있다.
공식 저장소에는 ONNX가 없고 `trust_remote_code`가 필요한 자체 구조(`custom_code`)다.
`onnx-community/gte-multilingual-reranker-base`에 `onnx/model_int8.onnx`(341MB)가 있다. 이 변환본이 원본과 같은 점수를 내는지는 확인하지 못했다.
연산량은 XLM-R base 수준(12층, hidden 768)으로 bge-reranker-v2-m3의 약 1/3.5로 추정한다.

### X25. jina-reranker-v2-base-multilingual 라이선스
- source: https://huggingface.co/jinaai/jina-reranker-v2-base-multilingual
- basis:
라이선스는 CC-BY-NC-4.0이다. 카드는 연구와 평가 용도로만 허용하고 상업 사용은 Jina API나 클라우드 마켓을 쓰라고 안내한다.
파라미터는 278M, 문맥 길이는 1024 토큰이다. 예시 언어에 한국어가 없고 한국어 지원을 명시하지 않는다.
fastembed 목록에 이미 있지만 라이선스 때문에 기본 모델 후보에서 뺀다.

### X26. mixedbread mxbai-rerank 계열
- source: https://www.mixedbread.com/blog/mxbai-rerank-v2.md , https://www.mixedbread.com/docs/reranking/models/mxbai-rerank-base-v2
- basis: X37
v2(`mxbai-rerank-base-v2` 0.5B, `large-v2` 1.5B)는 Apache-2.0이고 100개 이상 언어를 지원한다고 적혀 있다. 한국어를 따로 명시하지는 않는다.
v2는 Qwen-2.5 기반이다. fastembed의 `TextCrossEncoder`는 인코더 출력의 첫 열을 점수로 읽는 구조라서 그대로는 쓸 수 없다고 판단한다(추정, X37).
NVIDIA 데이터센터 GPU에서도 base-v2가 질의당 0.67초다. CPU에서 30쌍을 0.5초 안에 처리하기는 어렵다고 본다(추정).
Mr.TyDi 다국어 평균은 base-v2 28.56, bge-reranker-v2-m3 30.99로 bge가 높다.

### X27. KURE-Reranker-nano (한국어 특화)
- source: https://huggingface.co/nlpai-lab/KURE-Reranker-nano , https://huggingface.co/skt/A.X-Encoder-base , https://huggingface.co/CreeJee/KURE-Reranker-nano-ONNX
- basis:
고려대 nlpai-lab 모델이고 Apache-2.0, 149M 파라미터, 한국어와 영어, 최대 8192 토큰이다. 기반은 `skt/A.X-Encoder-base`(ModernBERT 구조)다.
공식 저장소에는 safetensors만 있다. `CreeJee/KURE-Reranker-nano-ONNX`에 `onnx/model.onnx`(598MB fp32)와 `model_fp16.onnx`가 있으나 int8은 없다.
이 ONNX 저장소는 2026-11-06에 올라온 개인 변환본이다. 원본과 출력을 비교한 결과가 카드에 없다.
ModernBERT 구조라 입력에 `token_type_ids`가 없다. 인코더 연산량은 bge-reranker-v2-m3의 약 1/3로 추정한다.

### X28. 그 밖의 한국어 재정렬 모델
- source: https://huggingface.co/dragonkue/bge-reranker-v2-m3-ko , https://huggingface.co/Dongjin-kr/ko-reranker , https://huggingface.co/api/models?search=reranker&filter=ko&sort=downloads&limit=20
- basis: X31
`dragonkue/bge-reranker-v2-m3-ko`는 bge-reranker-v2-m3를 한국어로 미세조정한 모델이고 Apache-2.0이다. 한국어 태그 재정렬 모델 중 내려받기가 가장 많다.
`Dongjin-kr/ko-reranker`는 bge-reranker-large 기반이고 MIT, 최대 512 토큰이다.
두 모델 모두 568M급 XLM-R large 구조라서 연산량은 bge-reranker-v2-m3와 같다. 공식 ONNX 파일은 확인하지 못했다.
따라서 품질이 조금 높아도 지연 시간 문제(X31)는 그대로 남는다.

### X29. CPU 지연 시간 실측 (x86 노트북)
- source: https://github.com/rahulnitb/bge-reranker-api
- basis:
Intel Core i5-8250U(4코어, AVX2, Windows)에서 약 150단어 문서, 요청당 p50을 쟀다. 측정 반복은 칸마다 3회뿐이다.
문서 10개 기준으로 mmarco-mMiniLMv2-L12 int8 0.40초, jina v2 int8 1.6초, bge-reranker-v2-m3 int8 6.1초, Qwen3-Reranker-0.6B fp32 11.0초였다.
bge-reranker-v2-m3는 int8이 fp32보다 1.6배 빨랐다. 작은 검증 세트에서 PyTorch와의 Spearman 상관은 0.991이고 1위는 같았다.
Apple Silicon 실측은 찾지 못했다.

### X30. 그 밖의 지연 시간 보고
- source: https://huggingface.co/newtechstudio/bge-reranker-v2-m3-onnx , https://github.com/Muditkumar123/agentic-document-intelligence-platform/pull/8 , https://hindsight.vectorize.io/blog/2026/09/24/adding-jev-reranker-what-we-learned
- basis: X29
newtechstudio 카드는 bge-reranker-v2-m3 fp32로 30쌍을 한 배치에 600~800ms라고 적는다. 하드웨어와 문서 길이가 없어 X29와 10배 넘게 차이 나는 이유를 알 수 없다.
AMD EPYC 7452에서 ms-marco-MiniLM-L-6 int8, 512 토큰 절단, 4스레드 기준 질문당 p50은 864ms였다. 질문당 후보 수는 적혀 있지 않다.
Hindsight는 짧은 기억 문장 30개를 MiniLM으로 재정렬하는 데 질의당 0.12초가 걸렸다고 적는다. 하드웨어는 적혀 있지 않다.

### X31. 30쌍 지연 시간 추정
- source: https://github.com/rahulnitb/bge-reranker-api , https://huggingface.co/api/models/cross-encoder/mmarco-mMiniLMv2-L12-H384-v1
- basis: X29, X32
X29의 쌍당 시간(mmarco 40ms, bge 610ms, 약 200~250 토큰으로 추정)에 Apple Silicon이 2~4배 빠르다는 가정을 곱했다. 512 토큰은 256 토큰의 2.2~2.5배로 잡았다(X32).
mmarco-mMiniLMv2-L12 int8은 256 토큰에서 0.3~0.6초, 512 토큰에서 0.7~1.4초다. ms-marco-MiniLM-L-6은 그 절반이다.
bge-reranker-v2-m3 int8은 256 토큰에서 4~9초, 512 토큰에서 10~22초다. gte와 KURE-nano는 256 토큰에서 1.5~5초다.
신뢰도는 낮다(오차 2배 이내 수준). 결론의 방향, 즉 568M급은 예산의 10배 이상이고 MiniLM급만 예산 근처라는 점은 비교적 확실하다.

### X32. 시퀀스 길이와 패딩 영향
- source: https://github.com/microsoft/onnxruntime/issues/19494 , fastembed 0.8.0 `fastembed/common/preprocessor_utils.py` `load_tokenizer`, `fastembed/rerank/cross_encoder/onnx_text_model.py`
- basis:
fastembed는 토크나이저 절단 길이를 `tokenizer_config.json`의 `model_max_length`로 정한다. bge-reranker-v2-m3와 KURE-nano는 8192, mmarco는 512다.
패딩은 배치 안의 가장 긴 쌍에 맞춘다. 기본 `batch_size=64`이므로 30쌍이 한 배치이고, 긴 문서 하나가 30쌍 모두를 그 길이로 늘린다.
선형층 비용은 토큰 수에 비례하고 어텐션은 길이의 제곱에 비례한다. hidden 384 모델에서 512 토큰이면 어텐션이 약 20% 더 붙는다고 계산했다(추정).
따라서 문서를 미리 256 토큰 안팎으로 잘라 넣는 것이 지연 시간을 가장 크게 줄인다.

### X33. 다국어 재정렬 품질 수치
- source: https://huggingface.co/jinaai/jina-reranker-v2-base-multilingual , https://arxiv.org/html/2407.19669 , https://www.mixedbread.com/blog/mxbai-rerank-v2.md
- basis:
Jina 표(nDCG@10): MKQA는 bge-reranker-v2-m3 54.17, mmarco-mMiniLMv2-L12 53.37, jina v2 54.83이다. BEIR은 각각 53.65, 45.40, 53.17이다. MLDR은 59.73, 28.91, 68.95이다.
mGTE 논문 표: MIRACL nDCG@10은 bge-reranker-v2-m3 72.6, gte-multilingual-reranker-base 68.5, jina v2 65.8이다. BEIR은 54.6, 55.4, 49.7이다.
mxbai 블로그의 Mr.TyDi 다국어 평균은 bge-reranker-v2-m3 30.99다.
mmarco는 짧은 다국어 질의(MKQA)에서는 bge와 1점 차이지만 영어(BEIR)와 긴 문서(MLDR)에서는 크게 뒤진다.

### X34. 한국어 벤치마크 수치
- source: https://huggingface.co/nlpai-lab/KURE-Reranker-nano , https://huggingface.co/dragonkue/bge-reranker-v2-m3-ko
- basis:
KURE 카드의 MTEB 한국어 검색 9종 평균 nDCG@10은 KURE-Reranker-nano 0.8757, bge-reranker-v2-m3 0.8518이다. 이 중 AutoRAGRetrieval은 0.9741과 0.9663, MIRACL 한국어는 0.8400과 0.8129이다.
AutoRAG 금융 한국어 벤치마크 top-1 정확도는 bge-reranker-v2-m3-ko 0.9123, bge-reranker-v2-m3 0.8772, Dongjin-kr/ko-reranker 0.8509, jina v2 0.8070, gte-multilingual-reranker-base 0.7281이다.
두 표 모두 mmarco-mMiniLMv2-L12를 포함하지 않는다. mmarco의 한국어 수치는 찾지 못했다.

### X35. 한국어 질의로 영어 문서 찾기
- source: https://arxiv.org/html/2402.03216 , https://github.com/apple/ml-mkqa , https://huggingface.co/jinaai/jina-reranker-v2-base-multilingual
- basis: X33
BGE-M3 논문은 MKQA를 비영어 25개 언어 질의로 영어 위키백과 문단을 찾는 교차 언어 평가로 쓴다. MKQA 언어 목록에 한국어(ko)가 있다.
따라서 X33의 MKQA 점수가 한국어 질의와 영어 문서 조합을 가장 가깝게 대신한다. 다만 26개 언어 평균이고 한국어만 떼어 낸 재정렬 점수는 없다.
KURE와 AutoRAG 수치는 한국어 질의와 한국어 문서 조합이다. 한국어 질의로 영어 페이지를 찾는 경우의 품질은 vault-graph 자료로 직접 재야 한다.

### X36. fastembed 0.8에 사용자 ONNX 모델 등록
- source: fastembed 0.8.0 `fastembed/rerank/cross_encoder/text_cross_encoder.py` `add_custom_model`, `fastembed/common/model_management.py`, `fastembed/common/model_description.py`
- basis:
`TextCrossEncoder.add_custom_model(model="cross-encoder/mmarco-mMiniLMv2-L12-H384-v1", sources=ModelSource(hf="cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"), model_file="onnx/model_qint8_arm64.onnx", license="apache-2.0", size_in_gb=0.12)`로 등록한다. 이후 `TextCrossEncoder(model_name=..., cache_dir=...)`로 만든다.
내려받는 파일은 `config.json`, `tokenizer.json`, `tokenizer_config.json`, `special_tokens_map.json`, `preprocessor_config.json`에 `model_file`과 `additional_files`를 더한 것이다.
`load_tokenizer`는 앞의 네 파일이 없거나 `tokenizer_config.json`에 `model_max_length`나 `max_length`가 없으면 실패한다.
가중치가 `model.onnx_data`처럼 따로 있으면 `additional_files=["onnx/model.onnx_data"]`를 넣어야 한다(onnx-community bge 변환본이 해당).

### X37. fastembed 등록 시 주의점
- source: fastembed 0.8.0 `fastembed/rerank/cross_encoder/onnx_text_model.py` `_build_onnx_input`, `onnx_embed_pairs`, `onnx_text_cross_encoder.py` `_post_process_onnx_output`, `text_cross_encoder.py` `add_custom_model`
- basis:
`token_type_ids`는 ONNX 그래프 입력에 그 이름이 있을 때만 넣는다. 그래서 XLM-R나 ModernBERT 모델에서 입력 불일치 문제는 생기지 않는다.
점수는 첫 출력 텐서의 `[:, 0]`이다. `[batch, 1]` 모델은 맞지만, 레이블이 2개인 모델은 0번 열(보통 "무관")을 점수로 읽게 된다. 시그모이드를 적용하지 않은 원시 logit이 나온다.
같은 이름으로 `add_custom_model`을 두 번 부르면 `ValueError`가 난다. 프로세스 안에서 한 번만 등록하도록 막아야 한다.
절단 길이를 바꾸는 공개 인자는 없다. 문서를 미리 잘라 넣거나 내부 토크나이저의 `enable_truncation`을 다시 불러야 한다(내부 속성 접근, 추정).

### X38. 캐시 위치
- source: fastembed 0.8.0 `fastembed/common/utils.py` `define_cache_dir`, `fastembed/common/model_management.py`, vault-graph `src/vault_graph/operation/scope/embedding_selection.py`
- basis:
`cache_dir`를 주지 않으면 `FASTEMBED_CACHE_PATH` 환경 변수, 그다음 시스템 임시 폴더의 `fastembed_cache`를 쓴다. 임베딩과 재정렬 모델이 같은 함수를 쓴다.
HF 원본은 `<cache_dir>/models--<org>--<name>` 아래 HF 스냅숏 구조로 저장된다. 임베딩 모델과 같은 폴더 규칙이다.
vault-graph는 임베딩에 `DEFAULT_MODELS_DIR = ~/llm/models`를 명시해서 넘긴다. 재정렬 모델에도 같은 `cache_dir`를 넘겨야 같은 폴더에 쌓인다.
`local_files_only=True`면 네트워크 없이 스냅숏을 찾는다. 임베딩 쪽 오프라인 동작과 같은 방식으로 맞출 수 있다.

### X39. Hindsight의 재정렬 사용
- source: https://arxiv.org/html/2512.12818v1 , https://hindsight.vectorize.io/blog/2026/08/28/cross-encoder-reranking-agent-memory , https://hindsight.vectorize.io/blog/2026/09/24/adding-jev-reranker-what-we-learned , https://vectorize.io/models
- basis:
논문과 블로그 모두 기본 재정렬 모델을 `cross-encoder/ms-marco-MiniLM-L-6-v2`(영어 전용)로 적는다. RRF 융합 뒤 최대 300개 후보에 적용하고, 로컬 logit에 시그모이드를 씌운 뒤 최신성 등의 가중치를 곱한다.
논문에는 재정렬만 떼어 낸 ablation이 없다. 블로그도 끄면 "더 빠르고 덜 정확하다"고만 적는다.
유일한 수치는 JEV 글의 LoCoMo 비교다. 후보 30개에서 로컬 MiniLM은 recall@1 0.800, NDCG@10 0.850, 질의당 0.12초였다. 재정렬을 끈 기준선은 없다.
업체 페이지는 클라우드 1.2 이후 기본값이 자체 모델 `hs-rerank-1`(114M)이라고 적는다. 독립 검증은 없다.

## 추천

1순위는 `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1`의 `onnx/model_qint8_arm64.onnx`다. Apache-2.0이고 119MB이며, 공식 저장소에 fastembed가 요구하는 파일이 모두 있다. 30쌍 256 토큰 추정치(0.3~0.6초)가 예산에 맞는 유일한 다국어 후보다. 교차 언어 MKQA 점수도 bge-reranker-v2-m3와 1점 차이다. 다만 한국어 품질 수치가 없으므로 vault-graph의 한국어 질의 평가 세트로 재정렬 전후를 먼저 재야 한다. 대안은 `BAAI/bge-reranker-v2-m3`의 int8 변환본(`onnx-community/bge-reranker-v2-m3-ONNX`의 `onnx/model_int8.onnx`)이다. 한국어 벤치마크 근거가 가장 많고 Apache-2.0이지만, 30쌍에 수 초가 걸릴 것으로 추정되므로 1초 예산 밖의 선택형 고품질 모드로만 쓴다. `KURE-Reranker-nano`는 한국어 점수가 가장 높지만 ONNX가 검증되지 않은 개인 변환본이고 예산도 넘을 것으로 보여 지금은 후보에서 뺀다.
