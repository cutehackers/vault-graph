# 외부 조사: 한국어 질의로 영어 위키를 찾는 방법

조사일: 2026-11-12. 웹 조사 결과를 요약했다. 초록이나 검색 요약만 본 항목은 그렇게 적었다.

### X-21
- source: https://qdrant.tech/blog/shift-multilingual-rag/ , https://arxiv.org/abs/2004.05484
- basis: 없음

같은 언어 편향(same-language bias)은 알려진 현상이다. XRAG에서 multilingual-e5-small은 같은 언어 정답을 상위 10에 61% 넣지만, 다른 언어 정답은 8%만 넣는다. 내부 측정 X-2, X-3과 같은 현상이다.

### X-22
- source: https://qdrant.tech/blog/shift-multilingual-rag/ , https://arxiv.org/abs/2606.18801 (초록만), https://aclanthology.org/2022.emnlp-main.379
- basis: X-21

SHIFT: 번역 쌍 수백 개로 언어별 평균 차이 벡터를 구해 문서와 질의 벡터에서 뺀다. LLM이나 재학습이 필요 없다. e5-small에서 교차 언어 Recall@10이 XRAG 0.083→0.240, XQuAD 0.752→0.955로 올랐고, 같은 언어 Recall@10은 0.608→0.488로 내려갔다. LSAR(언어 부분공간을 SVD로 찾아 제거)도 같은 계열이다(효과 수치 미확인).

### X-23
- source: https://arxiv.org/abs/2507.07543 (초록), https://arxiv.org/html/2601.02956v1 , https://arxiv.org/html/2504.16264v1
- basis: 없음

질의 번역: 교차 언어 검색이 병목이며, 질의 번역이나 언어별로 같은 수를 뽑는 방법이 크게 돕는다는 보고가 있다(수치는 초록에 없음). 한국어를 포함한 bge-m3 실험에서 영어 번역 질의가 원어 질의보다 정답률이 7~9점 높았다. 반대로 과학 문서 벤치마크(CLIRudit)에서는 번역 효과가 작거나 해로운 경우도 있었다.

### X-24
- source: https://arxiv.org/html/2402.03216 , https://huggingface.co/nlpai-lab/KURE-v1
- basis: 없음

MKQA 한국어 질의 → 영어 문단 Recall@100: BM25 27.9, mE5-large 68.1, bge-m3 71.6. 큰 모델로 바꿔도 mE5-large 대비 3.5점 차이다. e5-small, arctic-l-v2, Qwen3-0.6B, KURE-v1의 한→영 수치는 찾지 못했다. KURE-v1은 bge-m3(568M)를 한국어로 미세 조정한 모델이다.

### X-25
- source: https://jina.ai/news/jina-reranker-v2-for-agentic-rag-ultra-fast-multilingual-function-calling-and-code-search , https://huggingface.co/onebrain-ai/onebrain-rerank-v1
- basis: 없음

다국어 재순위 모델: jina-reranker-v2-multilingual(278M, CC-BY-NC, 업체 주장), bge-reranker-v2-m3(568M, int8 ONNX 약 569MB), Qwen3-Reranker-0.6B. Apple Silicon CPU에서 후보 20~50개 지연 시간은 공개된 수치가 없다. 직접 재야 한다.

### X-26
- source: https://www.anthropic.com/engineering/writing-tools-for-agents
- basis: 없음

Anthropic의 에이전트 도구 작성 지침: 도구 설명에 올바른 입력 예시와 질의 형식을 명시하고, 넓은 검색 하나보다 좁은 검색 여러 개를 권한다. 설명 문구 하나를 고쳐 에이전트의 잘못된 질의 습관을 고친 사례가 있다. 질의 언어는 다루지 않는다.
