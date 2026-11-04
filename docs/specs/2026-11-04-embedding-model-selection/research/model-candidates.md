# 임베딩 모델 후보

조사일: 2026-11-04. fastembed 0.8.0(`uv.lock`)으로 직접 돌려 보았고, Hugging Face 모델 카드와 공개 한국어 리더보드를 함께 확인했다. 한국어 점수는 공식 MTEB 실행 결과가 아니라 커뮤니티 표에서 가져왔다.

## 확인한 사실

- fastembed 0.8.0에 기본으로 들어 있는 다국어 모델은 MiniLM-L12(지금 모델), mpnet-base-v2, multilingual-e5-large, jina-embeddings-v3 네 개다.
- 목록에 없는 ONNX 모델도 `TextEmbedding.add_custom_model(model, pooling, normalization, sources, dim, model_file, ...)`로 쓸 수 있다. `Xenova/multilingual-e5-small`(MEAN pooling)과 `Snowflake/snowflake-arctic-embed-l-v2.0`(CLS pooling)으로 0.8.0에서 실제로 동작하는 것을 확인했다.
- 지금 모델은 조각마다 앞 128토큰만 읽는다. fastembed 설명에 적혀 있고 직접 확인했다. 우리 조각의 평균 길이는 13~104토큰이라 대부분은 잘리지 않지만, 긴 조각은 뒷부분이 버려진다.
- jina-embeddings-v3는 CC-BY-NC(비상업) 라이선스라 후보에서 뺀다.
- 코드 식별자, 경로, 셸 명령으로 한국어 검색 품질을 잰 공개 자료는 찾지 못했다. 아래 점수는 모두 한국어 문장 질의응답 기준이다.

## 비교

한국어 점수 A는 7개 과제의 NDCG@10 평균이다([dragonkue/multilingual-e5-small-ko](https://huggingface.co/dragonkue/multilingual-e5-small-ko)). C는 [ko-embedding-leaderboard](https://github.com/OnAnd0n/ko-embedding-leaderboard) 점수다.

| 모델 | fastembed | 차원 | 받는 크기 | 최대 토큰 | 라이선스 | 접두어 | 한국어 A | 속도(조각/초, 405토큰) |
|---|---|---|---|---|---|---|---|---|
| paraphrase-multilingual-MiniLM-L12-v2 (지금) | 기본 | 384 | 220MB | 128 | Apache-2.0 | 없음 | 0.410 | 126 |
| multilingual-e5-small (int8, Xenova) | 사용자 등록 | 384 | 118MB | 512 | MIT | `query: ` / `passage: ` | 0.671 | 54 |
| multilingual-e5-large | 기본 | 1024 | 2.24GB | 512 | MIT | `query: ` / `passage: ` | 0.722 | 측정 안 함 |
| bge-m3 (fp32) | 사용자 등록 | 1024 | 2.27GB | 8192 | MIT | 없음 | 0.724 (C 79.30) | 측정 안 함 |
| snowflake-arctic-embed-l-v2.0 (int8) | 사용자 등록 | 1024 | 570MB | 8192 | Apache-2.0 | 질의에만 `query: ` | 0.724 (C 80.00) | 9 |

- 속도는 이 Mac에서 32개 조각으로 한 번 잰 값이다. 실제 조각은 더 짧으므로 실제 속도는 이보다 빠르다.
- 전체 26k조각을 다시 임베딩하는 시간을 이 속도로 계산하면 MiniLM 약 3.5분, e5-small 약 8분, arctic-l int8 약 48분이다. 실제로는 이보다 짧을 것으로 본다(추정).
- 벡터가 1024차원이면 Chroma 저장소가 384차원보다 약 2.7배 커진다.

## 조사 에이전트의 추천

- 기본: snowflake-arctic-embed-l-v2.0 int8. 한국어 점수는 bge-m3와 같고, Apache-2.0이며, 받는 크기는 bge-m3의 4분의 1이다.
- 작고 빠른 것: multilingual-e5-small int8. 한국어 점수가 지금보다 0.26 높고, 받는 크기는 118MB다.
- 크고 좋은 것: bge-m3 fp32, 또는 ONNX로 변환한 한국어 미세조정 모델(KURE-v1 등).

## 출처

- [dragonkue/multilingual-e5-small-ko](https://huggingface.co/dragonkue/multilingual-e5-small-ko)
- [nlpai-lab/KoE5](https://huggingface.co/nlpai-lab/KoE5)
- [ko-embedding-leaderboard](https://github.com/OnAnd0n/ko-embedding-leaderboard)
- [nlpai-lab/KURE-v2](https://huggingface.co/nlpai-lab/KURE-v2)
- [Snowflake Arctic Embed 2.0](https://snowflake.com/engineering-blog/snowflake-arctic-embed-2-multilingual)
- [Xenova/multilingual-e5-small](https://huggingface.co/Xenova/multilingual-e5-small), [BAAI/bge-m3](https://huggingface.co/BAAI/bge-m3), [Snowflake/snowflake-arctic-embed-l-v2.0](https://huggingface.co/Snowflake/snowflake-arctic-embed-l-v2.0)
