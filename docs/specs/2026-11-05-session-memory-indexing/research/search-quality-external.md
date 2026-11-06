# 검색 품질 외부 조사: 로컬에서 돌릴 수 있는 개선 방법

조사일: 2026-11-07. 대상: vault-graph의 FTS5(bm25) + Chroma(`multilingual-e5-small`) + 링크 그래프 융합 검색.

읽는 법:
- 각 발견에는 출처 링크를 붙였다. "추론"이라고 쓴 문장은 출처가 직접 말하지 않고 이 문서가 출처를 우리 상황에 적용한 것이다.
- 2차 요약(emergentmind, liner 등)만 확인한 수치는 "2차 출처"라고 표시했다. 인용 전에 원문을 다시 확인해야 한다.
- 우리 측정값(제목 질의 hit@5 0.55 대 0.95, 세션 MRR 약 0.70, 512 토큰 초과 창 12%)은 이 저장소의 기존 보고서 값이다. 외부 출처가 아니다.

## 1. 필드 가중 키워드 순위와 질의 유형

- 발견1. FTS5 `bm25()`는 열마다 가중치를 받는다. 예: `bm25(ft, 10.0, 5.0)`는 첫 열 일치를 10배, 둘째 열을 5배로 센다. `INSERT INTO ft(ft, rank) VALUES('rank', 'bm25(10.0, 5.0)')`로 표 기본값을 정할 수 있고, `ORDER BY rank`가 `ORDER BY bm25()`보다 빠르다. k1=1.2, b=0.75는 고정이라 바꿀 수 없다. ([SQLite FTS5 §bm25](https://www.sqlite.org/fts5.html#the_bm25_function), [§rank 설정](https://www.sqlite.org/fts5.html#the_rank_configuration_option))
- 발견2. FTS5 가중치는 열별 빈도에 곱하는 방식이다. 정통 BM25F는 열별 빈도를 먼저 합친 뒤 포화를 한 번만 적용한다. 그래서 FTS5 열 가중치는 BM25F의 근사다. ([SQLite FTS5 §bm25](https://www.sqlite.org/fts5.html#the_bm25_function), [Robertson·Zaragoza 2009 BM25 개요](https://staff.city.ac.uk/~sbrp622/papers/foundations_bm25_review.pdf), [Terrier BM25F 문서](https://javadoc.io/static/org.terrier/terrier-core/5.6/org/terrier/matching/models/BM25F.html))
- 발견3. 정확한 제목 일치는 FTS5 구 질의와 열 필터로 따로 셀 수 있다. 예: `title : "세션 메모리 색인"`. 열 이름을 MATCH 왼쪽에 둬도 된다. ([SQLite FTS5 §구](https://www.sqlite.org/fts5.html#fts5_phrases), [§열 필터](https://www.sqlite.org/fts5.html#fts5_column_filters))
- 발견4. 제목 가중은 모든 질의에 이득이 아니다. ADCS 2016 연구는 평균적으로 제목 가중이 효과를 올리지 않았고 탐색형(navigational) 질의에서만 도움이 됐다고 보고했다. (검색 요약으로 확인, PDF 본문 미확인: [Koopman 외 ADCS 2016](https://bevankoopman.github.io/papers/adcs2016-titles.pdf))
- 발견5. 알려진 항목(entry page) 찾기에서는 내용 외 특징이 강하다. URL 형태 사전확률로 정답의 70% 이상을 1위에, 최대 89%를 상위 10위에 올렸다. 입력 링크 수도 사전확률로 쓰였다. (수치는 발표 자료 기준: [Kraaij·Westerveld·Hiemstra SIGIR 2002](https://research.utwente.nl/en/publications/the-importance-of-prior-probabilities-for-entry-page-search/))
- 추론. 우리 문제(제목 질의에서 키워드 0.95, 융합 0.55)는 융합이 키워드의 정답 1위를 묽게 만든다는 뜻이다. 제목 열 가중만으로는 부족하고, "질의가 제목과 정확히 또는 거의 일치하면 그 문서를 위로 올리는" 규칙을 융합 뒤에 두는 편이 직접적이다. 결정적이고 비용이 작다.

## 2. 융합: RRF 대 가중 점수 융합

- 발견6. RRF(k=60)는 TREC 실험에서 개별 시스템 최고값과 Condorcet보다 나았다(MAP .2145 대 .2016, .2074). k는 10~100에서 결과가 거의 같았다. ([Cormack 외 SIGIR 2009](https://plg.uwaterloo.ca/~gvcormac/cormacksigir09-rrf.pdf))
- 발견7. 점수 볼록 결합(CC, α·정규화 점수 합)은 도메인 안팎 모두 RRF보다 나았다. 정규화 방식 선택에 덜 민감했고, 소수의 예시로 α 하나를 맞출 수 있었다. RRF도 매개변수에 민감했다. ([Bruch·Gai·Ingber, ACM TOIS, arXiv 2210.11934](https://arxiv.org/abs/2210.11934))
- 발견8. 하이브리드가 단일 방식보다 나은 근거: 도메인이 다를 때 BM25+밀집 RRF가 밀집 대비 평균 20.4%, 어휘 대비 9.54% 상대 향상. 두 방식이 서로 다른 정답을 찾는다. ([Chen 외 ECIR 2022](https://arxiv.org/abs/2201.10582)) Anthropic 실험도 임베딩+BM25가 임베딩 단독보다 낫다고 결론냈다. ([Anthropic Contextual Retrieval](https://www.anthropic.com/news/contextual-retrieval))
- 발견9. 후보 깊이: Anthropic 실험은 1차 검색 150개, 재순위 후 20개를 썼다. ([Anthropic Contextual Retrieval](https://www.anthropic.com/news/contextual-retrieval))
- 추론. RRF는 순위만 보므로 키워드의 "압도적 1위" 신호를 잃는다. 제목 질의 손실(발견4~5)과 맞는다. 평가셋이 생기면(8절) CC로 α를 맞춰 RRF와 비교할 가치가 있다. 단, α를 평가셋에 맞추면 과적합되므로 개발용과 시험용을 나눠야 한다.

## 3. 로컬 재순위 모델

| 모델 | 크기 | 라이선스 | 길이 | 근거 |
|---|---|---|---|---|
| bge-reranker-v2-m3 | 약 0.6B, bge-m3 기반 | Apache-2.0 | 예시 코드가 512 토큰 절단 | [모델 카드](https://huggingface.co/BAAI/bge-reranker-v2-m3), [ONNX 변환](https://huggingface.co/onnx-community/bge-reranker-v2-m3-ONNX) |
| jina-reranker-v2-base-multilingual | 278M | CC-BY-NC-4.0 (연구·평가용) | 1024 토큰, 넘으면 미끄럼 창 | [모델 카드](https://huggingface.co/jinaai/jina-reranker-v2-base-multilingual) |
| mmarco-mMiniLMv2-L12-H384-v1 | 약 0.1B | Apache-2.0 | 카드에 없음 | [모델 카드](https://huggingface.co/cross-encoder/mmarco-mMiniLMv2-L12-H384-v1) |
| bge-reranker-v2-m3-ko | bge-reranker-v2-m3 미세조정 | 카드 확인 필요 | | [모델 카드](https://huggingface.co/dragonkue/bge-reranker-v2-m3-ko) |

- 발견10. jina 카드의 비교(nDCG@10): MKQA 54.83 대 bge 54.17, BEIR 53.17 대 53.65, CodeSearchNet MRR@10 71.36 대 62.86. 한국어 단독 수치는 없다. ([jina 카드](https://huggingface.co/jinaai/jina-reranker-v2-base-multilingual))
- 발견11. 한국어 금융 AutoRAG 벤치마크(게시자 자체 측정): Top-1 F1 bge-reranker-v2-m3 0.877, 한국어 미세조정판 0.912, jina 0.807. Top-5에서는 두 bge가 같았다. ([dragonkue 카드](https://huggingface.co/dragonkue/bge-reranker-v2-m3-ko))
- 발견12. mMARCO 미세조정 데이터는 14개 언어로 기계번역됐다. 한국어 포함 여부는 이 조사에서 확인하지 못했다. ([모델 카드](https://huggingface.co/cross-encoder/mmarco-mMiniLMv2-L12-H384-v1))
- 발견13. Apple Silicon 지연 시간 측정값은 찾지 못했다. CPU 수치는 서로 25배 차이 난다. 30쌍에 600~800ms(ONNX 한 배치)라는 보고와 30쌍·256토큰에 3~4초 이상이라는 보고가 있다. 둘 다 하드웨어 미표기. ([ONNX 변환 카드](https://huggingface.co/newtechstudio/bge-reranker-v2-m3-onnx), [개인 위키](https://myforgelabs.github.io/myforge-vault-1111/wiki/reranker-cost-optimization-not-size.en/))
- 발견14. 재순위는 큰 효과가 보고됐다. 실패율 5.7%에서 문맥 임베딩+BM25로 2.9%, 재순위까지 1.9%(67% 감소). 단, 외부 API 재순위 모델 기준이다. ([Anthropic Contextual Retrieval](https://www.anthropic.com/news/contextual-retrieval))
- 추론. 재순위는 효과가 크지만 지연 시간이 측정 전에는 모르는 값이고, 모델 파일 내려받기와 새 의존성이 생긴다. 우리 Mac에서 20~50쌍 지연을 먼저 재야 한다. 라이선스로는 bge-reranker-v2-m3가 가장 안전하다.

## 4. 한국어 키워드 검색

- 발견15. FTS5 unicode61은 문자·숫자 연속을 한 토큰으로 본다. 한글 어절 "규제를"은 통째 토큰이 되어 "규제"와 일치하지 않는다. 형태소 분할은 하지 않는다. (규칙은 문서 기준, 한글 적용은 그 규칙에서 추론: [SQLite FTS5 §unicode61](https://www.sqlite.org/fts5.html#unicode61_tokenizer))
- 발견16. trigram 토크나이저는 3글자 이상 부분 문자열을 맞춘다. 3글자 미만 질의는 일치가 없다. 한국어 두 글자 명사(예: "색인")는 trigram만으로는 못 찾는다. LIKE/GLOB도 색인을 탄다. ([SQLite FTS5 §trigram](https://www.sqlite.org/fts5.html#the_trigram_tokenizer))
- 발견17. Kiwi로 색인과 질의를 모두 정규화하면 "규제를" 같은 조사 붙은 질의가 맞는다. 형태소 분석 없이는 결과가 0건이었다. (489청크·12질의 실습: [wikidocs 389782](https://wikidocs.net/389782))
- 발견18. Kiwi 논문: 중의성 해소 정확도 평균 86.7%, 비교한 딥러닝 분석기는 50~70%. 미등록어와 방언에 약하다고 저자가 밝혔다. ([Lee, 디지털인문학 2024](https://accesson.kr/kjdh/v.1/1/109/43508))
- 발견19. Kiwi와 MeCab-ko의 BM25 품질을 직접 비교한 통제 실험은 찾지 못했다. 정성 비교로는 MeCab이 빠르지만 사용자 사전 관리가 필요하고, Kiwi는 신조어·고유명사를 잘 다룬다. ([maju-tech 블로그](https://maju-tech.blogspot.com/2026/05/rag-core-study-1126-sparse-retrieval.html), [Kiwi BM25 Retriever 튜토리얼](https://langchain-opentutorial.gitbook.io/langchain-opentutorial/10-retriever/10-kiwi-bm25-retriever))
- 발견20. 한국어에서 BM25 기준값: Mr.TyDi에서 multilingual-e5-small 한국어 MRR@10은 54.3으로 언어 중 가장 낮다. ([e5-small 카드](https://huggingface.co/intfloat/multilingual-e5-small)) NanoMIRACL-ko에서 BM25 nDCG@10 약 0.50, 밀집 약 0.70, 재순위 하이브리드 약 0.71. (리더보드: [NanoMIRACL/ko](https://hakari-bench-leaderboard.hf.space/docs/benchmark-tasks/NanoMIRACL/ko))
- 추론. 가장 싼 결정적 개선은 색인 시 Kiwi로 형태소(또는 어간)를 뽑아 별도 FTS 열에 넣고, 질의도 같은 방식으로 정규화하는 것이다. 원문 열은 영어·코드·식별자용으로 그대로 둔다. Kiwi 버전과 사전을 고정해야 같은 입력이 같은 토큰을 낸다.

## 5. 문서 단위와 허브 페이지

- 발견21. 긴 문서를 조각으로 나눌 때 문서 점수를 가장 높은 조각 점수로 두는 MaxP가 첫 조각(FirstP)·합(SumP)·평균보다 일관되게 나았다(재현 연구). ([Dai·Callan SIGIR 2019](https://arxiv.org/abs/1905.09217), [Lin 그룹 ECIR 2021 재현](https://cs.uwaterloo.ca/~jimmylin/publications/978-3-030-72240-1_11.pdf))
- 발견22. 검색 단위를 명제(작은 단위)로 바꾸면 비지도 검색기 Recall@5가 평균 +12.0(SimCSE), +9.3(Contriever) 올랐다. 지도 학습 검색기는 효과가 작았다. 명제 생성에 LLM이 필요하다. ([Dense X Retrieval, EMNLP 2024](https://arxiv.org/abs/2312.06648))
- 발견23. 질의마다 최적 조각 크기가 다르다. 작은 조각으로 찾고 그 조각을 포함한 큰 조각을 돌려주는 2단 구조가 제안됐다(라우터는 학습 필요). ([Mix-of-Granularity, COLING 2025](https://arxiv.org/abs/2406.00456))
- 발견24. 임베딩 공간의 허브(여러 질의의 최근접에 반복 등장하는 점)는 알려진 현상이다. CSLS는 원래 유사도에서 그 점의 k개 최근접 평균 유사도를 빼서 허브를 낮춘다. 대규모 밀집 검색 벤치마크에서의 효과는 확인하지 못했다. ([Conneau 외 2018, CSLS](https://arxiv.org/abs/1710.04087), [kiez CSLS 구현](https://kiez.readthedocs.io/en/latest/source/_autosummary/kiez.hubness_reduction.CSLS.html), [Schnitzer 외 JMLR 2012, mutual proximity](https://jmlr2020.csail.mit.edu/papers/volume13/schnitzer12a/schnitzer12a.pdf))
- 발견25. 입력 링크가 많은 문서는 알려진 항목 질의의 정답일 가능성이 높다(발견5, 발견33). 그래서 입력 링크 수로 일률 감점하면 탐색형 질의를 해칠 수 있다.
- 추론.
  - 짧은 위키 페이지는 문서 하나에 벡터 하나(제목+본문)로 충분하다. 긴 원본 문서는 "제목+요약 문서 벡터"와 "조각 벡터"를 함께 두고 문서 점수는 MaxP로 모은다.
  - 허브 문제는 두 원인을 나눠 봐야 한다. 그래프 신호가 허브를 올리면 그래프 가중을 입력 링크 수로 나누는(정규화) 것이 맞다. 벡터 검색이 허브를 올리면 CSLS 같은 보정 후보가 있으나, 질의마다 k개 이웃 계산이 더 필요하다. 감점은 정보형 질의에만 적용하고 제목 일치 질의에는 적용하지 않는다.
  - 두 Vault의 같은 페이지 중복은 순위 문제가 아니라 식별 문제다. 본문 해시나 정규화 경로로 결과를 접는 결정적 규칙이 필요하다.

## 6. 대화 기록(세션) 색인

- 발견26. LongMemEval: 세션을 라운드(사용자 한 번+응답 한 번) 단위로 나누면 GPT-4o 독해 QA가 크게 올랐다. 요약·사실로만 바꾸면 정보 손실로 대체로 나빠졌다(여러 세션 추론만 예외). 단 Recall@5는 세션 단위 K=V+fact 0.732가 라운드 단위 0.644보다 높았다. 검색 정확도와 QA 정확도의 최적 단위가 다를 수 있다. ([LongMemEval, ICLR 2025, §5.2·표3](https://arxiv.org/abs/2410.10813))
- 발견27. LongMemEval 키 확장: 값 자체를 키로 쓰는 것(K=V)이 강한 기준선이다. 요약·핵심구만 키로 쓰면 재현율이 오르지 않았다. 값에 추출 사실을 덧붙이면(K=V+fact) 라운드 단위 Recall@5가 0.582에서 0.644로 올랐다. 사실 추출에 LLM이 필요하다. ([LongMemEval §5.3](https://arxiv.org/abs/2410.10813))
- 발견28. LongMemEval 시간 인식 질의 확장은 강한 LLM(GPT-4o)에서만 효과가 있었고 Llama 3.1 8B에서는 Recall@5가 0.421에서 0.384로 떨어졌다. ([LongMemEval §5.4](https://arxiv.org/abs/2410.10813))
- 발견29. SeCom: 턴 단위는 너무 조각나고 세션 단위는 무관한 내용이 많다. 주제가 이어지는 구간(segment) 단위로 저장하고 잡음을 압축해 지우면 LOCOMO와 Long-MT-Bench+에서 턴·세션·요약 기준선보다 나았다. 구간 분할과 압축에 모델을 쓴다. ([SeCom, ICLR 2025](https://arxiv.org/abs/2502.05589))
- 발견30. LoCoMo: 대화를 화자에 대한 단언(observation) 데이터베이스로 바꾸면 RAG가 가장 잘 됐다. 단언 생성에 LLM이 필요하다. 세부 수치는 원문 미확인. ([LoCoMo, ACL 2024](https://arxiv.org/abs/2402.17753))
- 발견31. 조각 앞에 문서 맥락 문장(50~100토큰)을 붙여 임베딩과 BM25를 모두 만들면 실패율이 35~49% 줄었다. 맥락 문장은 LLM이 만든다. ([Anthropic Contextual Retrieval](https://www.anthropic.com/news/contextual-retrieval))
- 추론.
  - 도구 안에서 LLM을 부르지 않으므로 사실 추출(발견27, 30)과 LLM 맥락 문장(발견31)은 쓸 수 없다. 대신 결정적 머리글(프로젝트 이름, 세션 날짜, 세션 첫 사용자 요청, 창 안의 파일 경로)을 창 앞에 붙이는 방식은 같은 원리를 LLM 없이 흉내 낸다. 효과 크기는 측정해야 한다.
  - 창 경계는 공백 단어 수보다 "사용자 턴에서 시작해 그 응답으로 끝나는 라운드"가 근거에 가깝다(발견26). 라운드가 512 토큰을 넘으면 같은 라운드 안에서 토큰 수로 나누고 사용자 질문을 각 조각 머리에 반복한다.
  - 도구 출력·긴 코드 덤프는 잡음이다(발견29의 잡음 제거 결과). 색인 전에 결정적 규칙으로 줄이거나 별도 열로 분리하면 된다.
- MemoryBench류 연구는 이번 조사에서 확인하지 못했다.

## 7. 임베딩 모델 한계

- 발견32. multilingual-e5-small은 512 토큰을 넘으면 잘린다. 입력마다 "query: "/"passage: " 접두어가 필요하고, 빼면 성능이 떨어진다. 라이선스 MIT. ([e5-small 카드](https://huggingface.co/intfloat/multilingual-e5-small))
- 추론. 창 크기는 공백 단어가 아니라 모델 토크나이저로 세야 한다. 머리글과 "passage: " 접두어까지 포함해 512 미만으로 맞춘다. 현재 12% 초과 창은 뒷부분이 벡터에 반영되지 않는다.
- 나중 평가 후보(모델 선택은 스펙이 미룸, 기록만 함):
  - bge-m3 계열: KURE-v1이 bge-m3를 한국어로 미세조정했고, 자체 표에서 bge-m3와 multilingual-e5-large를 근소하게 앞선다. ([KURE-v1 카드](https://huggingface.co/nlpai-lab/KURE-v1))
  - Qwen3-Embedding-0.6B: 한 판매사 표에서 MTEB-ko 0.7017, bge-m3 0.7483. ([PIXIE-Rune 카드](https://huggingface-gw-kz.just-ai.com/telepix/PIXIE-Rune-v1.0))
  - e5-small과 EmbeddingGemma를 같은 한국어 검색 벤치마크에서 비교한 자료는 찾지 못했다.

## 8. 평가셋 만들기

- 발견33. 문서에서 자동으로 만든 알려진 항목 질의는 사람 질의보다 성능이 나쁘게 나오는 경향이 있었다. 원인은 너무 흔한 단어 선택과 정답 문서 선택 방식이다. 사람은 입력 링크가 많은 문서를 정답으로 고르는 경향이 있었고, 입력 링크 사전확률을 넣으면 일부 언어에서 사람 질의와 비슷해졌다. ([Azzopardi·de Rijke·Balog SIGIR 2007](https://dare.uva.nl/id/77a67e89-3f22-4ec5-a4aa-e3ede2fba889))
- 발견34. LLM이 만든 합성 질의는 실제 질의보다 길고, 시스템 점수를 실제보다 높게 만드는 경향이 있었다. LLM 판정자는 관대하다. ([Rahmani 외 2025](https://arxiv.org/abs/2506.10301), [Rahmani 외 SIGIR 2024](https://arxiv.org/abs/2405.07767))
- 발견35. 점수 결합 α는 소수 예시로 맞출 수 있다(발견7). 같은 평가셋으로 맞추고 보고하면 과대평가된다(추론).
- 지표: 정답이 하나인 알려진 항목 질의는 hit@k와 MRR, 정답이 여럿이고 등급이 있는 정보형 질의는 nDCG@10. ([Järvelin·Kekäläinen 2002, nDCG](https://dl.acm.org/doi/10.1145/582415.582418), [Cormack 외 2009](https://plg.uwaterloo.ca/~gvcormac/cormacksigir09-rrf.pdf)의 MAP 사용 예)
- 추론. 데이터 종류별 작은 평가셋 구성:
  1. 위키: 제목 그대로, 제목 일부, 제목을 다른 말로 바꾼 질의, 한↔영 교차 질의. 각 30개 내외. 입력 링크가 적은 페이지도 일부러 포함한다(발견33).
  2. 원본 문서: 본문 사실을 묻는 질의. 문서 단어를 그대로 복사하지 않고 바꿔 쓴다. 정답 문서 여러 개면 nDCG.
  3. 세션: 사람이 실제로 다시 찾았던 질문(지난 세션의 사용자 요청)을 쓴다. 문서에서 생성한 질의는 어휘 일치가 높아 BM25를 과대평가한다.
  4. 코드: 심볼 이름 질의와 동작 설명 질의를 나눈다.
  5. 개발용과 시험용을 나누고, 매개변수는 개발용으로만 맞춘다. 질의 작성 시 문서와 겹치는 단어 비율을 기록해 편향을 확인한다.

## 우선순위

기준: 효과 × 비용 × 결정성 위험. "결정성 위험"은 같은 입력이 같은 순위를 내지 못할 위험이다. 효과 크기 표기는 출처 수치가 있으면 붙이고, 없으면 "측정 필요"로 둔다.

### 지금 도입할 것

| 코드 | 대상 | 방법 | 효과 근거 | 비용 | 결정성 위험 |
|---|---|---|---|---|---|
| 권고1 | 위키 | 제목 정확·근접 일치 시 융합 결과 위로 올리기, FTS5 제목 열 가중과 `title : "..."` 구 일치 | 키워드 0.95 대 융합 0.55(우리 측정), 탐색형 질의에 제목 가중 효과(발견4~5) | 작음 | 없음 |
| 권고2 | 공통 | 두 Vault 중복 결과를 본문 해시나 경로로 접기 | 측정 필요 | 작음 | 없음 |
| 권고3 | 세션 | 창을 모델 토크나이저 기준 512 미만으로 자르기, 머리글과 접두어 포함 | 초과 12%의 뒷부분이 현재 무시됨(발견32) | 작음 | 없음 |
| 권고4 | 세션 | 창 경계를 라운드 단위로, 긴 라운드는 질문을 반복해 분할, 결정적 머리글 추가 | LongMemEval 라운드 분할(발견26), 맥락 머리글 원리(발견31) | 중간(재색인) | 없음 |
| 권고5 | 위키·원본 | 그래프 가중을 입력 링크 수로 정규화, 정보형 질의에만 허브 감점 | 허브 원인 분리 필요(발견24~25) | 작음 | 없음 |
| 권고6 | 공통 | 데이터 종류별 소규모 평가셋, 개발/시험 분리 | 편향 근거(발견33~35) | 중간(사람 작성) | 없음 |

### 평가셋이 생긴 뒤 도입할 것

| 코드 | 대상 | 방법 | 효과 근거 | 비용 | 결정성 위험 |
|---|---|---|---|---|---|
| 권고7 | 한국어 전체 | Kiwi 형태소 열 추가, 질의도 같은 정규화 | 조사 붙은 질의 0건 해소(발견17) | 중간(의존성, 재색인) | 낮음. Kiwi 버전·사전 고정 필요 |
| 권고8 | 공통 | RRF 대 점수 볼록 결합 비교, 신호별 후보 깊이 조정 | CC가 RRF보다 나음(발견7) | 작음 | 없음. 과적합 위험만 있음 |
| 권고9 | 원본 문서 | 문서 벡터(제목+요약 앞부분)와 조각 벡터 병행, MaxP로 모으기 | MaxP 우위(발견21) | 중간 | 없음 |
| 권고10 | 짧은 한국어 명사 | trigram 보조 열 | 3글자 미만은 못 찾음(발견16) | 작음 | 없음 |

### 나중에 검토할 것

| 코드 | 대상 | 방법 | 보류 이유 |
|---|---|---|---|
| 권고11 | 공통 | bge-reranker-v2-m3(Apache-2.0) 상위 20~50 재순위 | 효과 큼(발견14), Apple Silicon 지연 미측정(발견13), 모델 내려받기 필요 |
| 권고12 | 공통 | 임베딩 모델 교체 후보(bge-m3/KURE-v1, Qwen3-Embedding-0.6B) | 스펙이 모델 선택을 미룸. 재색인 비용 큼(기존 보고서 측정) |
| 권고13 | 벡터 | CSLS 허브 보정 | 대규모 검색 벤치마크 근거 없음(발견24) |
| 권고14 | 세션 | 사실 추출·구간 분할·단언 변환 | LLM 필요(발견27, 29, 30). 도구 안 LLM 호출 금지 원칙과 충돌 |

## 확인하지 못한 것

1. Kiwi 대 MeCab-ko BM25 통제 비교.
2. Apple Silicon에서 재순위 모델 20~50쌍 지연 시간.
3. mmarco-mMiniLMv2 학습 언어에 한국어가 포함되는지.
4. ADCS 2016 제목 가중 논문 본문 수치(PDF 텍스트 추출 실패).
5. LoCoMo 저장 방식별 정확 수치, MemoryBench류 연구.
6. e5-small과 EmbeddingGemma의 한국어 검색 비교.
