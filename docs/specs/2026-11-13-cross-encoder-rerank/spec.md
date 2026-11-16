# cross-encoder 재정렬로 검색 순위 개선 계획

<!-- bake: index -->
| ID | title | status | relations | covered by | area | hash | tasks |
|---|---|---|---|---|---|---|---|
| I1 | 재정렬은 순서만 바꾼다 |  | basis X1, X2 | A3 | 검색 | 117d099e | 2-reranker-core.md |
| I2 | 검색은 모델을 내려받지 않고 다른 모델로 바꾸지 않는다 |  | basis X12, X19, X38 | A8 | global | 7199d118 | 4-text-cross-encoder-adapter.md |
| I3 | 꺼져 있으면 지금과 같다 |  | basis X1, X2 | A2 | 검색 | 99d8582c | 5-factory-wiring-warnings.md |
| I4 | 재정렬은 아무것도 쓰지 않는다 |  | basis X19 | A12 | global | c7857e04 | 2-reranker-core.md |
| I5 | 순위 번호는 최종 순서를 따른다 |  | basis X5 | A3 | 검색 | ded23404 | 2-reranker-core.md |
| I6 | 재정렬 입력을 위해 저장소를 더 읽지 않는다 |  | basis X4, X7 | A5 | 검색 | 537966d6 | 2-reranker-core.md |
| D1 | 검색 순위 개선에 cross-encoder 재정렬을 쓴다 | decided | basis X17 | A15 | global | adf71878 | 7-effect-measurement-adoption.md |
| D2 | 코드보다 측정을 먼저 한다 | proposed | basis X17, X19, X31; depends D1 | A1 | 측정 | 8220ab04 | 1-measurement-gates.md |
| D3 | 관문1: 남은 실패가 주로 6~30위 순위 손실이어야 한다 | proposed | basis X15, X17, X19; depends D2 | A1 | 측정 | 320c91f7 | 1-measurement-gates.md |
| D4 | 관문2: 이 Mac에서 30쌍 재정렬 p95가 0.5초 이하여야 한다 | proposed | basis X15, X19, X31, X32; depends D2, D5 | A1, A14 | 측정 | 528addfe | 1-measurement-gates.md |
| D5 | 모델은 mmarco-mMiniLMv2-L12-H384-v1 arm64 int8로 한다 | proposed | basis X22, X23, X31, X33, X36 | A14 | 모델 | 71aebb98 | 3-reranker-config.md |
| D6 | refill 뒤, slice 앞에서 상위 30개만 다시 정렬한다 | proposed | basis X1, X2, X6, X40, I1; depends D4 | A3, A20 | 검색 | c24ba5f6 | 2-reranker-core.md |
| D7 | 재정렬 입력은 frontmatter title·summary와 가장 높은 조각 전문이다 | proposed | basis X3, X4, X7, X8, X32, X37, I6 | A5 | 검색 | 32c9d0e3 | 2-reranker-core.md |
| D8 | 재정렬 순위를 기존 순위와 RRF로 섞는다 | proposed | basis X5, X37, I1; depends D6 | A4, A15 | 검색 | 0bf9d49a | 2-reranker-core.md |
| D9 | 설정은 Graph Home `configs/reranker.json`, 모델은 preset으로 고정한다 | proposed | basis X9, X10, X11, X38 | A8 | 설정 | e63d5a21 | 3-reranker-config.md |
| D10 | 모델 내려받기는 `vg reranker use`에서만 한다 | proposed | basis X12, X19, I2; depends D9 | A8 | 설정 | 4b8859ea | 3-reranker-config.md |
| D11 | 재정렬이 안 되면 재정렬 없이 답하고 경고 하나를 붙인다 | proposed | basis X13, X19, I2, I3; depends D9 | A7 | 검색 | c49afdc7 | 5-factory-wiring-warnings.md |
| D12 | 세션 검색(evidence 모드)에도 같이 적용하고 효과는 따로 잰다 | proposed | basis X7, X18; depends D6, D7 | A11, A17, A18 | 검색, 측정 | cfccc8cf | 2-reranker-core.md |
| D13 | `stage_trace`에 재정렬 전후 순위를 남긴다 | proposed | basis X2, X5, X17; depends D6 | A10 | 검색, 평가 | 019679c0 | 2-reranker-core.md |
| D14 | 포트는 retrieval, fastembed 연결은 adapters에 둔다 | proposed | basis X10, X14, X36, X37 | A9 | 구조 | f52584d7 | 4-text-cross-encoder-adapter.md |
| D15 | 평가 도구는 Graph Home 설정으로 켜고 끈다 | proposed | basis X15, X16, X18; depends D9 | A13 | 평가 | 853a65cf | 6-longmemeval-preset-arg.md |
| D16 | 채택 기준은 기존 목표를 그대로 쓰고, 시험용은 마지막에 한 번만 본다 | proposed | basis X15, X16, X18, X19, X40 | A15, A16, A17, A20 | global | ce030c2d | 7-effect-measurement-adoption.md |
| D17 | 기본값은 꺼짐으로 둔다 | decided | basis I3; depends D16 | A2 | 설정 | 5e674677 | 5-factory-wiring-warnings.md |
| D18 | bge-reranker-v2-m3는 이번 범위에서 뺀다 | decided | basis X20, X21, X29, X31; depends D5 | A19 | 모델 | 5154de3d | 3-reranker-config.md |
| D19 | 측정 단계에서는 mmarco 파일(약 120MB)만 내려받는다 | decided | basis X11, X23, X38; depends D4, D18 | A1 | 측정 | 5ffd9c9b | 1-measurement-gates.md |
| F1 | 켜져 있는데 모델 파일이 없다 |  | basis D11, I2 | A7 |  | 2d068dcd | 5-factory-wiring-warnings.md |
| F2 | 재정렬 실행 중 오류가 난다 |  | basis D11, D14 | A7 |  | 22c68447 | 5-factory-wiring-warnings.md |
| F3 | 설정 파일이 깨졌거나 모르는 preset을 가리킨다 |  | basis D9, D11 | A7 |  | a1439808 | 5-factory-wiring-warnings.md |
| F4 | 결과가 1개 이하다 |  | basis D6 | A3 |  | a6798952 | 2-reranker-core.md |
| F5 | 결과 수가 N보다 적거나 많다 |  | basis D6, I1 | A3 |  | 82325f37 | 2-reranker-core.md |
| F6 | 질의나 조각이 길다 |  | basis D7 | A6 |  | cec6bc04 | 4-text-cross-encoder-adapter.md |
| F7 | 첫 재정렬이 느리다 |  | basis D4, D14 | A14 |  | b35fe385 | 7-effect-measurement-adoption.md |
| F8 | 한 프로세스에서 어댑터를 여러 번 만든다 |  | basis D14 | A9 |  | f6207343 | 4-text-cross-encoder-adapter.md |
| F9 | 여러 Vault의 결과가 섞여 있다 |  | basis D6 | A3 |  | 94111a42 | 2-reranker-core.md |
| F10 | 정확한 제목 질의에서 모델이 정답을 내린다 |  | basis D8 | A4 |  | faa42623 | 2-reranker-core.md |
| R1 | mmarco의 한국어 재정렬 품질을 모른다 |  | basis X22, X34, X35, D5 |  |  | 640b5ba6 |  |
| R2 | 관문2 지연 추정이 두 배 넘게 틀릴 수 있다 |  | basis X29, X30, X31, D4 |  |  | e4389138 |  |
| R3 | arm64 int8 파일과 fp32 파일의 점수 차이를 모른다 |  | basis X23, D5 |  |  | f590994d |  |
| R4 | 관문1을 통과하지 못할 수 있다 |  | basis X17, X19, D3 |  |  | ea9e20bf |  |
| R5 | 평소 slice 전 문서 결과 수를 모른다 |  | basis X6, D6 |  |  | 8eb6de17 |  |
| R6 | 256 토큰 자르기를 fastembed 밖에서 해야 한다 |  | basis X32, X37, D7 |  |  | f3ce2b87 |  |
| R7 | arm64 전용 파일이 다른 기기에서 동작하는지 모른다 |  | basis X23, D5 |  |  | 58b11352 |  |
| R8 | MRR 여유가 0.004뿐이다 |  | basis X19, D8 |  |  | a0112df9 |  |
| R9 | 개발용 96문항에 섞기 값을 맞추면 과적합될 수 있다 |  | basis D16 |  |  | 262f4a70 |  |
| A1 | 측정 보고서가 두 관문의 판정을 적는다 |  | covers D2, D3, D4, D19 |  |  | 59faad81 | 1-measurement-gates.md |
| A2 | 재정렬이 꺼져 있으면 결과가 이 변경 전과 같다 |  | covers I3, D17 |  |  | eb18657c | 5-factory-wiring-warnings.md |
| A3 | 재정렬은 순서만 바꾸고 순위 번호를 새 순서에 맞춘다 |  | covers I1, I5, D6, F4, F5, F9 |  |  | 0adfb2a3 | 2-reranker-core.md |
| A4 | RRF 섞기가 정한 식과 동점 규칙을 따른다 |  | covers D8, F10 |  |  | 19c3d86d | 2-reranker-core.md |
| A5 | 재정렬 입력은 이미 읽은 텍스트로 만든다 |  | covers D7, I6 |  |  | 95d55ce0 | 2-reranker-core.md |
| A6 | 질의와 텍스트 쌍이 256 토큰 안으로 잘린다 |  | covers F6 |  |  | 56f82249 | 4-text-cross-encoder-adapter.md |
| A7 | 모델 없음·실행 실패·설정 오류는 경고 하나와 기존 순서로 답한다 |  | covers D11, F1, F2, F3 |  |  | 112e31d1 | 5-factory-wiring-warnings.md |
| A8 | 검색과 테스트는 모델을 내려받지 않고, `vg reranker use`만 받는다 |  | covers I2, D9, D10 |  |  | 50173bb0 | 4-text-cross-encoder-adapter.md |
| A9 | fastembed 등록은 프로세스당 한 번이다 |  | covers D14, F8 |  |  | 7a7a1280 | 4-text-cross-encoder-adapter.md |
| A10 | `stage_trace`에 재정렬 전후 순위가 남는다 |  | covers D13 |  |  | 3a979014 | 2-reranker-core.md |
| A11 | evidence 모드 세션 결과도 재정렬된다 |  | covers D12 |  |  | e9503d76 | 2-reranker-core.md |
| A12 | 재정렬은 아무것도 쓰지 않는다 |  | covers I4 |  |  | b679cbd1 | 2-reranker-core.md |
| A13 | 평가 도구로 켜고 끈 결과를 비교할 수 있다 |  | covers D15 |  |  | 1cf27e21 | 6-longmemeval-preset-arg.md |
| A14 | 재정렬을 켠 검색 p95가 1초 이하다 |  | covers D4, D5, F7 |  |  | 51ff93ba | 7-effect-measurement-adoption.md |
| A15 | 개발용에서 wiki recall@5와 MRR이 오르고 title은 1.00이다 |  | covers D1, D8, D16 |  |  | e231e7af | 7-effect-measurement-adoption.md |
| A16 | 층2 recall@5가 0.95 이상이다 |  | covers D16 |  |  | 9f36d81b | 7-effect-measurement-adoption.md |
| A17 | LongMemEval이 회귀하지 않는다 |  | covers D12, D16 |  |  | b07e4619 | 7-effect-measurement-adoption.md |
| A18 | 세션 recall@5를 따로 적고 목표3을 지킨다 |  | covers D12 |  |  | 583af332 | 7-effect-measurement-adoption.md |
| A19 | preset 목록에는 mmarco 하나만 있다 |  | covers D18 |  |  | 9804423c | 3-reranker-config.md |
| A20 | `build_context_pack` 적중이 회귀하지 않는다 |  | covers D6, D16 |  |  | fd9187d2 | 7-effect-measurement-adoption.md |
| O1 | 1초 예산을 넘는 고품질 모델 bge-reranker-v2-m3를 이번 범위에서 뺄까요? |  | decides D18 |  |  | 93a362cc |  |
| O2 | 측정 단계에서 mmarco 모델 파일(약 120MB)을 `~/llm/models`에 내려받아도 될까요? |  | decides D19 |  |  | a1ef231a |  |
| O3 | 측정을 통과하면 재정렬 기본값을 켜짐으로 바꿀까요? |  | decides D17 |  |  | 280a0520 |  |
| X20 | bge-reranker-v2-m3 기본 정보 |  | basis X34 |  |  | b7a91621 |  |
| X21 | bge-reranker-v2-m3 ONNX 파일 |  |  |  |  | 6befe23c |  |
| X22 | mmarco-mMiniLMv2-L12-H384-v1 기본 정보 |  |  |  |  | a6cd2b09 |  |
| X23 | mmarco-mMiniLMv2-L12-H384-v1 ONNX 파일 |  | basis X36 |  |  | 707dd1ef |  |
| X24 | gte-multilingual-reranker-base |  |  |  |  | a7381397 |  |
| X25 | jina-reranker-v2-base-multilingual 라이선스 |  |  |  |  | 6168df2a |  |
| X26 | mixedbread mxbai-rerank 계열 |  | basis X37 |  |  | 6f10c8a8 |  |
| X27 | KURE-Reranker-nano (한국어 특화) |  |  |  |  | 06f5740e |  |
| X28 | 그 밖의 한국어 재정렬 모델 |  | basis X31 |  |  | 9e4973cc |  |
| X29 | CPU 지연 시간 실측 (x86 노트북) |  |  |  |  | b26b08be |  |
| X30 | 그 밖의 지연 시간 보고 |  | basis X29 |  |  | 1d8f517b |  |
| X31 | 30쌍 지연 시간 추정 |  | basis X29, X32 |  |  | bd4f2ad9 |  |
| X32 | 시퀀스 길이와 패딩 영향 |  |  |  |  | 06ad2770 |  |
| X33 | 다국어 재정렬 품질 수치 |  |  |  |  | a5c88331 |  |
| X34 | 한국어 벤치마크 수치 |  |  |  |  | 10629f63 |  |
| X35 | 한국어 질의로 영어 문서 찾기 |  | basis X33 |  |  | 0b27aa9a |  |
| X36 | fastembed 0.8에 사용자 ONNX 모델 등록 |  |  |  |  | 6392e5a7 |  |
| X37 | fastembed 등록 시 주의점 |  |  |  |  | 73fb94f9 |  |
| X38 | 캐시 위치 |  |  |  |  | c6673c27 |  |
| X39 | Hindsight의 재정렬 사용 |  |  |  |  | c9dd9ee9 |  |
| X1 | 재정렬이 들어갈 자리 |  |  |  |  | ddb1c3e6 |  |
| X2 | 후보 수 공식과 refill 규칙 |  |  |  |  | 352f6230 |  |
| X3 | RetrievalResult가 가진 텍스트 |  |  |  |  | 15a1816d |  |
| X4 | 전문은 resolve_results 안에 이미 있다 |  |  |  |  | 87ea526d |  |
| X5 | 지금의 문서 순위 계산 |  |  |  |  | b52e88fc |  |
| X6 | slice 전 문서 결과 수 |  |  |  |  | 8bb029ed |  |
| X7 | 세션 검색도 같은 경로다 |  |  |  |  | 74d05848 |  |
| X8 | 문서 조각 크기 |  |  |  |  | 2f7d5fa6 |  |
| X9 | 모델 preset 목록 |  |  |  |  | 0a2fdbe0 |  |
| X10 | 모델 적재 순서 |  |  |  |  | 1ca5eb48 |  |
| X11 | 모델 파일 위치와 설정 파일 |  |  |  |  | c430b7e7 |  |
| X12 | 검색은 내려받지 않는다 |  |  |  |  | 4f3d5332 |  |
| X13 | 모델 없음이 경고가 되는 길 |  |  |  |  | ffc7459c |  |
| X14 | fastembed 0.8.0의 교차 인코더 지원 |  |  |  |  | 38415443 |  |
| X15 | 층1과 검색 p95 |  |  |  |  | f48549c5 |  |
| X16 | 층2와 비교 도구 |  |  |  |  | 9352ad32 |  |
| X17 | 순위 손실과 후보 손실의 정의 |  |  |  |  | 31e3a413 |  |
| X18 | LongMemEval과 켜고 끄기 비교 |  |  |  |  | fe31fd6e |  |
| X19 | 재정렬이 지켜야 할 제약과 지금 남은 실패 |  |  |  |  | 11947ca2 |  |
| X40 | 회상은 검색하지 않고, context pack은 검색을 거친다 |  |  |  |  | 8eec129d |  |
<!-- bake: index end -->

## 1. Problem

지금 검색은 후보를 `fuse_candidates`로 합치고 `resolve_results`가 조각 점수로 문서 순위를 매긴다(X1, X5). 질의와 문서를 함께 읽고 관련도를 다시 판단하는 단계가 없어, 정답이 후보에 있는데 5위 밖으로 밀리는 순위 손실(`rank_loss`)이 생긴다(X17).

1. 최종 측정에서 wiki recall@5는 0.91, MRR은 0.784로 목표 0.78과 0.004 차이다. 검색 p95는 0.41초다(X19).
2. 기존 spec `2026-11-11-search-and-memory-quality-2`의 작업 21과 결정18은 "남은 실패가 주로 6~30위 순위 손실이고 p95 1초 이하일 때만" 재정렬을 넣게 했다. 판정에 쓸 arctic-m 기준 분류는 없고 e5-small 시절 값만 있다(X19).
3. 작업 21의 후보 `bge-reranker-v2-m3`는 30쌍에 4~9초로 추정된다. 예산 근처의 다국어 후보는 `mmarco-mMiniLMv2-L12-H384-v1` int8뿐이다(X22, X23, X31).
4. `RetrievalResult`에는 경로 제목과 240자 발췌만 있다. 조각 전문과 frontmatter는 `resolve_results` 안에서 읽고 버린다(X3, X4).
5. 재정렬 설정, 내려받기 명령, 모델 없음 경고가 없어 켜고 끄는 비교도 못 한다(X11, X13, X18).

확인 방법: 커밋 `40065d0`의 소스·평가 도구, fastembed 0.8.0 소스, 모델 카드를 읽었다. 모델은 받지 않았고 지연은 재지 않았다.

## 2. Intent

사용자는 Hindsight와 비교한 뒤 cross-encoder 재정렬을 골랐고 vault-graph에 맞게 적용할 계획을 요청했다("이걸 vault-graph에 적용할 수 있는 형태로 제안해줘요"). 구현은 승인 뒤 따로 한다.

1. 후보에 든 정답이 5위 안으로 더 올라와 wiki recall@5와 MRR이 오른다. [가정] 기존 목표를 성공 기준으로 쓴다.
2. 켜도 검색은 로컬에서 1초 안에 끝나고, 모델이 없으면 지금처럼 답하되 경고한다. [가정]
3. 측정으로 효과가 확인되기 전에는 기본 검색이 바뀌지 않는다. [가정] 결정18의 판정 규칙을 이어받는다.

## 3. Non-goals

1. 후보 손실 줄이기. 재정렬은 있는 후보의 순서만 바꾼다.
2. `fuse_candidates`, 조각 점수, 후보 수 공식, refill 규칙 변경.
3. LLM이나 원격 API 재정렬(`docs/SPEC.md` 원칙1).
4. 재정렬 점수를 저장하거나 회상 순위에 쓰는 일.
5. KURE-Reranker-nano, bge-reranker-v2-m3-ko, jina v2(CC-BY-NC-4.0) 등록.
6. x86용 ONNX 파일 선택. 이번에는 이 Mac(arm64)만 다룬다.

## 4. Design

1단계는 코드 변경 없는 측정이고, 두 관문을 통과해야 2단계 구현에 들어간다. 결과는 `docs/design/reports/2026-11-reranker-measurement.md`에 적는다.

2단계 검색 흐름:

1. `RetrievalService._search_request`가 지금처럼 후보를 모으고 `resolve_results`로 결과를 만든 뒤 refill 판단을 끝낸다.
2. `resolve_results`는 결과마다 내부 전용 재정렬 텍스트를 함께 돌려준다. `RetrievalResult`에는 넣지 않는다.
3. 켜져 있으면 slice 앞에서 상위 N개(초안 30)를 `Reranker`에 넘기고 기존 순위와 RRF로 섞는다. `rank`, `result_id`를 다시 매기고 `results[: request.limit]`로 자른다.
4. `stage_trace`에 재정렬 전후 순위를 남긴다.

경계:

- 포트 `retrieval/search/reranker.py`의 `Reranker`: `rerank(query: str, passages: Sequence[str]) -> list[int]`. 실패는 `RerankError`.
- 어댑터 `interface/composition/adapters/text_cross_encoder.py`: fastembed `TextCrossEncoder`를 고정 revision 스냅숏으로 만들고 256 토큰으로 자른다.
- 설정 Graph Home `configs/reranker.json`, preset `RERANK_PRESETS`, 내려받기 `vg reranker use <preset>`.
- 읽기 전용 팩토리와 CLI 검색이 설정을 읽어 `Reranker`를 넘긴다. 꺼져 있으면 넘기지 않는다.

`build_context_pack`도 같은 검색을 부르므로 함께 바뀐다. 세션 시작 회상은 검색을 부르지 않아 바뀌지 않는다(X40).

### I1. 재정렬은 순서만 바꾼다
- by: 가정 (brief 가정4, 5에서 도출)
- area: 검색
- basis: X1, X2

결과를 더하거나 빼지 않고 후보 수와 refill 판단도 그대로다. 상위 N개 밖 결과는 원래 상대 순서로 뒤에 붙는다. `limit` slice는 재정렬 뒤에 한다.

### I2. 검색은 모델을 내려받지 않고 다른 모델로 바꾸지 않는다
- by: 가정 (brief 가정6과 기존 제약)
- area: global
- basis: X12, X19, X38

검색 경로 어댑터는 `local_files_only=True`로만 모델을 찾고, 없으면 다른 preset이나 fastembed 기본 모델로 바꾸지 않는다. 테스트도 내려받지 않는다.

### I3. 꺼져 있으면 지금과 같다
- by: 가정 (brief 가정6)
- area: 검색
- basis: X1, X2

설정이 없거나 꺼져 있으면 결과 순서, `rank`, `result_id`, 경고, `stage_trace`가 변경 전과 같다.

### I4. 재정렬은 아무것도 쓰지 않는다
- by: 가정 (AGENTS.md Project Boundary)
- area: global
- basis: X19

검색 중 재정렬은 Vault, Graph Home, 모델 폴더에 쓰지 않는다. 점수는 응답 안에서만 쓴다. 설정과 모델 파일은 `vg reranker use`만 쓴다.

### I5. 순위 번호는 최종 순서를 따른다
- by: 가정 (X5에서 도출)
- area: 검색
- basis: X5

순서가 바뀌면 `rank`를 1부터 다시 매기고 `result_id`의 `rank-N`도 맞춘다.

### I6. 재정렬 입력을 위해 저장소를 더 읽지 않는다
- by: 가정 (brief 가정4)
- area: 검색
- basis: X4, X7

입력은 `resolve_results`가 이미 읽은 조각 전문과 frontmatter로만 만든다. `resolve_chunk`를 다시 부르거나 세션의 다른 창을 읽지 않는다.

## 5. Decisions

### D1. 검색 순위 개선에 cross-encoder 재정렬을 쓴다
- by: 사람 (brief "사람의 말": "cross-encoder 재정렬 이것정도가 괜찮아 보인다")
- status: decided
- area: global
- basis: X17

사용자가 Hindsight와 비교해 고른 기법이다. Hindsight 자료는 효과 수치가 없고 모델이 영어 전용이라 근거로 쓰지 않는다.

### D2. 코드보다 측정을 먼저 한다
- by: 가정 (brief 가정2)
- status: proposed
- area: 측정
- basis: X17, X19, X31
- depends: D1

1단계에서 남은 실패의 종류(관문1)와 이 Mac의 재정렬 시간(관문2)을 잰다. 하나라도 못 넘으면 보고서에 사유를 적고 작업을 닫는다. 지금 분류는 e5-small 시절 값이고 지연은 추정뿐이다.

### D3. 관문1: 남은 실패가 주로 6~30위 순위 손실이어야 한다
- by: 가정 (brief 가정2, 기존 결정18의 판정 규칙)
- status: proposed
- area: 측정
- basis: X15, X17, X19
- depends: D2

arctic-m 최종 코드로 층1 개발용 96문항을 다시 돌리고, 실패마다 `document_rank`로 6~30위 순위 손실, 31위 밖 순위 손실, 후보 손실로 나눈다. 6~30위가 절반 이상이면 통과다. 평가는 `limit=20`이라 `rank_loss`에 재정렬이 닿지 않는 깊은 순위도 섞이므로 `rank_loss`만 세지 않는다.

### D4. 관문2: 이 Mac에서 30쌍 재정렬 p95가 0.5초 이하여야 한다
- by: 가정 (brief 가정2. 0.5초는 손실 분류 보고서 4절 기준)
- status: proposed
- area: 측정
- basis: X15, X19, X31, X32
- depends: D2, D5

D5의 모델로 개발용 질의마다 상위 30개 문서 쌍을 256 토큰으로 잘라 재정렬하고, 적재 뒤 p50·p95와 최대 메모리를 잰다. 저장소 밖 일회용 스크립트로 잰다. 검색 p95 0.41초에 0.5초를 더해도 목표8(1초) 안이다.

### D5. 모델은 mmarco-mMiniLMv2-L12-H384-v1 arm64 int8로 한다
- by: 가정 (brief 가정3)
- status: proposed
- area: 모델
- basis: X22, X23, X31, X33, X36

`onnx/model_qint8_arm64.onnx`(119MB, Apache-2.0)를 쓴다. 공식 저장소에 fastembed가 요구하는 파일이 모두 있다. 예산 근처에 드는 유일한 다국어 후보이고 MKQA 점수가 bge-reranker-v2-m3와 1점 차이다. 작업 21의 bge는 추정 지연이 예산의 10배 안팎이라 1순위에서 내린다.

### D6. refill 뒤, slice 앞에서 상위 30개만 다시 정렬한다
- by: 가정 (brief 가정4)
- status: proposed
- area: 검색
- basis: X1, X2, X6, X40, I1
- depends: D4

`_search_request`의 refill 루프 뒤, `results[: request.limit]` 앞에 둔다. refill 판단과 `_expand_context`는 바뀌지 않는다. N은 관문2에서 잰 크기와 같아야 하고, 키우면 관문2를 다시 잰다. 이 자리라 `build_context_pack` 결과도 바뀐다.

### D7. 재정렬 입력은 frontmatter title·summary와 가장 높은 조각 전문이다
- by: 가정 (brief 가정4)
- status: proposed
- area: 검색
- basis: X3, X4, X7, X8, X32, X37, I6

문서 결과는 frontmatter `title`, `summary`(있을 때), 가장 높은 조각 전문을 잇는다. 그 조각이 `page_card`면 조각 전문만 쓴다. 세션 결과는 인용한 창(약 96 단어)이다. 어댑터가 쌍을 256 토큰으로 자른다. fastembed는 512로만 자르고 배치 최장 쌍에 맞춰 패딩하기 때문이다.

### D8. 재정렬 순위를 기존 순위와 RRF로 섞는다
- by: 가정 (brief 가정5)
- status: proposed
- area: 검색
- basis: X5, X37, I1
- depends: D6

점수는 `1/(k + 기존 순위) + w/(k + 재정렬 순위)`, 동점이면 기존 순위가 앞선다. 순위만 쓰므로 logit 보정이 필요 없다. 통째로 맡기지 않는 이유는 title 질의와 MRR을 지키기 위해서다. `k`(10·60), `w`(0.5·1·2)와 "재정렬 순서 그대로"를 개발용에서 비교해 코드 상수로 고정한다.

### D9. 설정은 Graph Home `configs/reranker.json`, 모델은 preset으로 고정한다
- by: 가정 (brief 가정6)
- status: proposed
- area: 설정
- basis: X9, X10, X11, X38

키는 `version`, `enabled`, `model`이고 파일이 없으면 꺼짐이다. `embedding.json`과 나눠 재색인 흐름과 섞이지 않게 한다. `RERANK_PRESETS`는 `EmbeddingPreset`과 같은 모양(repo, 고정 revision, 파일 목록, 크기)이다. 모델 폴더는 `embedding.json`의 `models_dir`(기본 `~/llm/models`)를 같이 쓴다.

### D10. 모델 내려받기는 `vg reranker use`에서만 한다
- by: 가정 (brief 가정6, `vg embedding use`와 같은 방식)
- status: proposed
- area: 설정
- basis: X12, X19, I2
- depends: D9

`vg reranker use <preset>`이 파일을 받고 성공하면 설정에 켜짐과 preset을 쓴다. `vg reranker off`는 `enabled`만 끈다. 검색, 색인, 서버 시작, 모듈 가져오기는 받지 않는다.

### D11. 재정렬이 안 되면 재정렬 없이 답하고 경고 하나를 붙인다
- by: 가정 (brief 가정6, 작업 21 done-when)
- status: proposed
- area: 검색
- basis: X13, X19, I2, I3
- depends: D9

기존 순서로 답하고 경고 하나를 붙인다. `reranker_unavailable`은 모델 파일 없음, `rerank_failed`는 실행 중 `RerankError`, `reranker_config_invalid`는 설정을 못 읽거나 모르는 preset이다. 모델 확인은 첫 재정렬 때 한 번 하고, 실행 실패는 그 질의에만 적용한다.

### D12. 세션 검색(evidence 모드)에도 같이 적용하고 효과는 따로 잰다
- by: 가정 (brief 가정7)
- status: proposed
- area: 검색, 측정
- basis: X7, X18
- depends: D6, D7

세션 교환도 같은 `_search_request`를 거치므로 모드별로 나누지 않는다. 세션 recall@5와 LongMemEval은 문서 검색과 따로 보고해 한쪽 개선이 다른 쪽 회귀를 가리지 않게 한다.

### D13. `stage_trace`에 재정렬 전후 순위를 남긴다
- by: 가정 (brief 가정8)
- status: proposed
- area: 검색, 평가
- basis: X2, X5, X17
- depends: D6

`document_ranks`는 재정렬 뒤 순서다. 재정렬이 돌면 `rerank` 항목에 대상 수, 결과별 전 순위와 모델 순위, 시간, preset을 적는다. 꺼져 있으면 항목이 없다.

### D14. 포트는 retrieval, fastembed 연결은 adapters에 둔다
- by: 가정 (ARCHITECTURE의 기존 구조)
- status: proposed
- area: 구조
- basis: X10, X14, X36, X37

포트, RRF 섞기, 순위 재부여는 `retrieval/search/reranker.py`, `TextCrossEncoder` 생성·등록·자르기는 `adapters/text_cross_encoder.py`에 둔다. 같은 이름 재등록은 `ValueError`이므로 프로세스당 한 번 잠금 아래 등록한다. 적재는 lazy다.

### D15. 평가 도구는 Graph Home 설정으로 켜고 끈다
- by: 가정 (X18에서 도출)
- status: proposed
- area: 평가
- basis: X15, X16, X18
- depends: D9

층1·층2는 측정용 Graph Home 두 개(꺼짐, 켜짐)를 `evaluate_search`와 `compare_search_eval`로 비교하고 도구는 바꾸지 않는다. `longmemeval_run`에는 preset 선택 인자를 더해 만든 Graph Home마다 설정을 쓴다. 인자가 없으면 지금과 같다.

### D16. 채택 기준은 기존 목표를 그대로 쓰고, 시험용은 마지막에 한 번만 본다
- by: 가정 (brief 가정1)
- status: proposed
- area: global
- basis: X15, X16, X18, X19, X40

섞기 값과 N은 개발용 96문항으로만 정하고, 시험용 96문항은 고정 뒤 한 번만 잰다. 지킬 값은 p95 1초(목표8), title 1.00, 층2 recall@5 0.95(목표11), LongMemEval 회귀 없음(목표9), context pack 적중 회귀 없음(목표4), wiki recall@5·MRR 상승(목표1·2)이다.

### D17. 기본값은 꺼짐으로 둔다
- by: 사람 (spec gate 2026-11-13: "꺼짐 유지")
- status: decided
- area: 설정
- basis: I3
- depends: D16

설정이 없으면 꺼져 있고 사용자가 `vg reranker use`로 켠다. 켜짐을 기본으로 하면 `vg setup`이 모델을 받아야 해서 설치 크기와 시간이 는다.

### D18. bge-reranker-v2-m3는 이번 범위에서 뺀다
- by: 사람 (spec gate 2026-11-13: "뺀다")
- status: decided
- area: 모델
- basis: X20, X21, X29, X31
- depends: D5

preset은 mmarco 하나다. bge는 한국어 근거가 가장 많지만 30쌍 추정 4~9초이고 571MB를 받아야 하며, 배치 축 고정 주장도 확인되지 않았다. 나중에 preset 항목 하나로 더할 수 있다.

### D19. 측정 단계에서는 mmarco 파일(약 120MB)만 내려받는다
- by: 사람 (spec gate 2026-11-13: "mmarco만 받는다")
- status: decided
- area: 측정
- basis: X11, X23, X38
- depends: D4, D18

관문2에는 모델 파일이 필요하다. 승인 뒤 측정 스크립트가 고정 revision의 arm64 int8 ONNX와 토크나이저 파일을 `~/llm/models`에 한 번 받는다. bge는 받지 않는다. 2단계의 `vg reranker use`는 이 파일을 그대로 쓴다.

## 6. Failure and boundary behavior

### F1. 켜져 있는데 모델 파일이 없다
- basis: D11, I2

기존 순서로 답하고 `reranker_unavailable`을 붙인다. 내려받거나 다른 모델로 바꾸지 않는다. 경고는 `vg reranker use <preset>`을 안내한다.

### F2. 재정렬 실행 중 오류가 난다
- basis: D11, D14

ONNX·토크나이저·추론 오류는 `RerankError`가 되고, 기존 순서와 `rerank_failed`로 답한다. 다음 질의는 다시 시도한다.

### F3. 설정 파일이 깨졌거나 모르는 preset을 가리킨다
- basis: D9, D11

JSON 오류, `version` 불일치, 목록에 없는 `model`이면 재정렬을 끄고 `reranker_config_invalid`를 붙인다. 검색은 실패하지 않는다.

### F4. 결과가 1개 이하다
- basis: D6

모델을 부르지 않는다. 경고도 `rerank` trace 항목도 없다.

### F5. 결과 수가 N보다 적거나 많다
- basis: D6, I1

적으면 있는 것만, 많으면 상위 N개만 재정렬하고 나머지는 원래 순서로 뒤에 붙인다.

### F6. 질의나 조각이 길다
- basis: D7

쌍이 256 토큰을 넘으면 텍스트를 먼저 자른다. 질의가 256을 넘으면 질의를 128 토큰으로 자른다. 긴 쌍 하나가 배치 패딩을 늘리지 않게 한다.

### F7. 첫 재정렬이 느리다
- basis: D4, D14

첫 질의에서 모델을 적재하므로 느리다. 시간 제한으로 끊지 않는다. 목표8은 적재 뒤 p95이고, 적재 시간은 보고서에 따로 적는다.

### F8. 한 프로세스에서 어댑터를 여러 번 만든다
- basis: D14

`add_custom_model`은 잠금 아래 한 번만 불려 `ValueError`가 나지 않는다.

### F9. 여러 Vault의 결과가 섞여 있다
- basis: D6

한 목록으로 다루고 결과의 Vault 이름과 종류는 그대로 둔다(SPEC 결정13).

### F10. 정확한 제목 질의에서 모델이 정답을 내린다
- basis: D8

RRF가 기존 순위를 함께 보므로 크게 떨어지지 않는다. title 1.00이 깨지는 섞기 값은 고르지 않는다.

## 7. What could be wrong

### R1. mmarco의 한국어 재정렬 품질을 모른다
- basis: X22, X34, X35, D5

학습 데이터와 한국어 벤치마크에 이 모델이 없다. 품질은 2단계 개발용 측정에서야 드러나고, 개선이 없으면 작업을 닫는다.

### R2. 관문2 지연 추정이 두 배 넘게 틀릴 수 있다
- basis: X29, X30, X31, D4

x86 노트북 한 곳의 3회 측정에 Apple Silicon 배율을 곱한 추정이다. 실측이 0.5초를 넘으면 관문2에서 멈춘다.

### R3. arm64 int8 파일과 fp32 파일의 점수 차이를 모른다
- basis: X23, D5

품질이 기대에 못 미치면 fp32(471MB)와 비교하는 측정이 더 필요하다.

### R4. 관문1을 통과하지 못할 수 있다
- basis: X17, X19, D3

arctic-m 뒤 분포를 모른다. 남은 wiki 실패가 12문항 안팎이라 절반 판정이 1~2문항에 흔들린다.

### R5. 평소 slice 전 문서 결과 수를 모른다
- basis: X6, D6

결과가 30개보다 훨씬 적으면 N=30은 전부를 보고, 훨씬 많으면 정답이 31위 밖에 남는다. 관문1의 `document_rank` 분포로 확인한다.

### R6. 256 토큰 자르기를 fastembed 밖에서 해야 한다
- basis: X32, X37, D7

공개 절단 인자가 없어 `tokenizer.json`으로 직접 세는 방식을 가정했다. 내부 속성을 건드려야 하면 fastembed를 올릴 때 깨질 수 있다.

### R7. arm64 전용 파일이 다른 기기에서 동작하는지 모른다
- basis: X23, D5

preset은 `model_qint8_arm64.onnx` 하나다. x86 기기에서 켜면 느리거나 점수가 다를 수 있는데 확인하지 않았다. 그때는 x86용 파일을 preset으로 더해야 한다.

### R8. MRR 여유가 0.004뿐이다
- basis: X19, D8

섞기 값이 1위를 자주 바꾸면 MRR이 목표 0.78 아래로 내려갈 수 있다.

### R9. 개발용 96문항에 섞기 값을 맞추면 과적합될 수 있다
- basis: D16

1~2문항 차이로 값이 갈린다. 시험용이 개발용보다 크게 낮으면 기본값을 켜지 않는다.

## 8. Acceptance criteria

### A1. 측정 보고서가 두 관문의 판정을 적는다
- covers: D2, D3, D4, D19
- check: 수동: 층1 개발용 96문항 `evaluate_search`와 저장소 밖 30쌍 지연 스크립트를 돌린 뒤 `docs/design/reports/2026-11-reranker-measurement.md`를 읽는다
- evidence: 수동: 층1 개발용 96문항 `evaluate_search`와 저장소 밖 30쌍 지연 스크립트를 돌린 뒤 `docs/design/reports/2026-11-reranker-measurement.md`의 §2~§7을 읽는다. 지금 보고서에는 관문1 5/8, 관문2 p95 0.349초, 파일과 revision, 적재 0.32초, 메모리 2,793MB가 적혀 있다.

실패별 `document_rank`와 세 분류 개수, 30쌍 p50·p95, 적재 시간, 최대 메모리, 받은 파일과 revision, 관문별 판정이 있다. 못 넘으면 닫은 사유가 있다.

### A2. 재정렬이 꺼져 있으면 결과가 이 변경 전과 같다
- covers: I3, D17
- check: tests/test_retrieval_service_search.py, tests/test_reranker_config.py
- evidence: tests/test_retrieval_service_search.py "test_search_without_reranker_keeps_the_search_order", tests/test_reranker_config.py "test_search_gets_no_reranker_without_settings"와 "test_search_gets_no_reranker_when_turned_off". 바뀌지 않은 기존 검색 테스트도 `bake-verify.log`(3349 passed)에서 통과한다.

설정 파일 없음과 `enabled: false`에서 순서, `rank`, `result_id`, 경고, `stage_trace`가 변경 전과 같다.

### A3. 재정렬은 순서만 바꾸고 순위 번호를 새 순서에 맞춘다
- covers: I1, I5, D6, F4, F5, F9
- check: tests/test_reranker.py
- evidence: tests/test_reranker.py "test_one_result_or_none_does_not_ask_the_model", "test_fewer_results_than_depth_are_all_reranked_by_the_rrf_formula", "test_results_beyond_depth_keep_their_order_after_the_reranked_ones", "test_mixed_vault_results_keep_their_vault"

가짜 `Reranker`로 결과 0개, 1개, N 미만, N 초과, 여러 Vault 혼합을 본다. 집합이 같고, N 밖은 원래 순서로 뒤에 붙고, `rank`·`result_id`가 새 순서를 따르고, Vault 이름·종류가 그대로이고, 1개 이하면 모델을 부르지 않는다.

### A4. RRF 섞기가 정한 식과 동점 규칙을 따른다
- covers: D8, F10
- check: tests/test_reranker.py
- evidence: tests/test_reranker.py "test_blend_follows_the_rrf_formula_and_keeps_search_order_on_ties", "test_exact_title_query_follows_the_rrf_formula_when_the_model_reverses"

순서를 뒤집는 가짜 `Reranker`에서 고정한 `k`, `w`로 계산한 순서가 나오고 동점이면 기존 순위가 앞선다.

### A5. 재정렬 입력은 이미 읽은 텍스트로 만든다
- covers: D7, I6
- check: tests/test_reranker.py, tests/test_retrieval_service_search.py
- evidence: tests/test_reranker.py "test_rerank_passages_use_text_already_read", tests/test_retrieval_service_search.py "test_reranked_search_reads_no_extra_chunks"

문서 입력에 title·summary와 조각 전문이 들고 `page_card`면 겹치지 않으며, 세션 입력은 인용 창이다. 켠 검색의 `resolve_chunk` 호출 수가 꺼진 검색과 같고 `RetrievalResult` 필드는 그대로다.

### A6. 질의와 텍스트 쌍이 256 토큰 안으로 잘린다
- covers: F6
- check: tests/test_text_cross_encoder.py
- evidence: tests/test_text_cross_encoder.py "test_long_text_is_cut_first_and_the_query_is_kept", "test_long_query_is_cut_to_128_tokens", "test_long_query_and_long_text_both_fit", "test_query_that_fills_the_budget_is_kept_whole"

긴 텍스트, 긴 질의, 둘 다 긴 경우에 쌍이 256 토큰 이하이고 질의는 128 토큰보다 짧게 잘리지 않는다.

### A7. 모델 없음·실행 실패·설정 오류는 경고 하나와 기존 순서로 답한다
- covers: D11, F1, F2, F3
- check: tests/test_reranker.py, tests/test_reranker_config.py
- evidence: tests/test_retrieval_service_search.py "test_reranker_failure_keeps_the_search_order_with_one_warning", "test_reranker_config_error_searches_without_reranking_and_warns", tests/test_reranker_config.py "test_broken_settings_turn_reranking_off_with_a_reason", "test_cli_search_reads_the_settings_file_and_warns_when_broken"

예외 없이 기존 순서가 나오고 경고가 `reranker_unavailable`, `rerank_failed`, `reranker_config_invalid` 중 정확히 하나다. 실행 실패 뒤 다음 질의는 다시 시도한다.

### A8. 검색과 테스트는 모델을 내려받지 않고, `vg reranker use`만 받는다
- covers: I2, D9, D10
- check: tests/test_reranker_config.py
- evidence: tests/test_reranker_config.py "test_search_adapter_without_model_files_does_not_download_or_fall_back", "test_use_downloads_pinned_files_into_embedding_models_dir_then_turns_on", "test_off_turns_off_only_enabled", "test_importing_reranker_modules_does_not_load_model_libraries"

검색 어댑터는 `local_files_only=True`로만 찾고 다른 모델로 바꾸지 않는다. `vg reranker use`는 고정 revision 파일을 `models_dir`에 받은 뒤 설정을 쓰고, `off`는 `enabled`만 끈다. 테스트는 네트워크 없이 통과한다.

### A9. fastembed 등록은 프로세스당 한 번이다
- covers: D14, F8
- check: tests/test_text_cross_encoder.py
- evidence: tests/test_text_cross_encoder.py "test_many_encoders_register_once", "test_encoders_built_on_many_threads_register_once", "test_fastembed_is_imported_only_in_adapters"

여러 번, 여러 스레드에서 만들어도 `add_custom_model`은 한 번 불린다. fastembed 가져오기는 adapters 안에만 있다.

### A10. `stage_trace`에 재정렬 전후 순위가 남는다
- covers: D13
- check: tests/test_retrieval_service_search.py
- evidence: tests/test_retrieval_service_search.py "test_reranking_reorders_before_the_limit_and_trace_follows_the_final_order", "test_search_without_reranker_keeps_the_search_order"

재정렬한 검색에 `rerank` 항목이 있고 `document_ranks`는 재정렬 뒤 순서다. 꺼진 검색에는 항목이 없다.

### A11. evidence 모드 세션 결과도 재정렬된다
- covers: D12
- check: tests/test_retrieval_service_search.py
- evidence: tests/test_retrieval_service_search.py "test_evidence_mode_reranks_session_exchanges_by_their_quoted_window"

`evidence` 모드에서 세션 결과가 같은 경로로 재정렬되고 입력은 인용 창이다.

### A12. 재정렬은 아무것도 쓰지 않는다
- covers: I4
- check: tests/test_reranker.py
- evidence: tests/test_reranker.py "test_reranked_search_writes_nothing"

켠 검색 전후로 Vault, Graph Home, 모델 폴더의 파일 목록과 수정 시각이 같다.

### A13. 평가 도구로 켜고 끈 결과를 비교할 수 있다
- covers: D15
- check: tests/test_longmemeval_run_reranker.py
- evidence: tests/test_longmemeval_run_reranker.py "test_prepare_with_a_preset_writes_the_reranker_config", "test_prepare_without_a_preset_writes_no_reranker_config"

`longmemeval_run`에 preset 인자를 주면 Graph Home마다 `configs/reranker.json`이 생기고, 안 주면 생기지 않는다.

### A14. 재정렬을 켠 검색 p95가 1초 이하다
- covers: D4, D5, F7
- check: 수동: 재정렬을 켠 측정용 Graph Home에서 층1 192문항 `evaluate_search`를 돌려 `summary.json`의 p95를 본다
- evidence: 수동: 재정렬을 켠 측정용 Graph Home에서 층1 `evaluate_search`를 돌려 `summary.json`의 p95를 본다. 보고서 §8.6에 켜짐 p95 0.778초, §4.2에 적재 0.32초가 적혀 있다.

목표8 방식(적재 뒤 한 프로세스)으로 p95가 1초 이하다. 적재 시간은 따로 적는다.

### A15. 개발용에서 wiki recall@5와 MRR이 오르고 title은 1.00이다
- covers: D1, D8, D16
- check: 수동: 층1 개발용을 꺼짐·켜짐으로 돌려 `compare_search_eval`로 비교하고, 값 고정 뒤 시험용을 한 번 잰다
- evidence: 수동: 층1 개발용을 꺼짐과 켜짐으로 돌려 `compare_search_eval`로 비교하고, 시험용은 값을 고정한 뒤 한 번 잰다. 보고서 §8.2와 §8.3에 개발용 MRR 0.735→0.848, wiki recall@5 60/66→64/66, title 1.00이 적혀 있다.

개발용 wiki recall@5와 MRR이 꺼짐보다 높고 MRR 0.78 이상, title 1.00이다. 시험용은 고정 뒤 한 번 잰 값으로 적는다.

### A16. 층2 recall@5가 0.95 이상이다
- covers: D16
- check: 수동: `eval2` Graph Home에서 재정렬을 켜고 `evaluate_search --vault-id eval2`를 돌린다
- evidence: 수동: `eval2` Graph Home에서 재정렬을 켜고 `evaluate_search --vault-id eval2`를 돌린다. 보고서 §8.4에 recall@5 0.989가 적혀 있다.

목표11을 지킨다.

### A17. LongMemEval이 회귀하지 않는다
- covers: D12, D16
- check: 수동: `longmemeval_run --limit 150`을 재정렬 preset 인자와 함께 돌린다
- evidence: 수동: `longmemeval_run --limit 150 --reranker mmarco`를 돌린다. 보고서 §8.7에 recall_all@5 0.80, recall_any@5 0.98이 적혀 있다.

recall_all@5 0.77 이상(목표9), recall_any@5 0.9667 이상이다.

### A18. 세션 recall@5를 따로 적고 목표3을 지킨다
- covers: D12
- check: 수동: 층1 개발용 꺼짐·켜짐 결과에서 세션 종류만 떼어 본다
- evidence: 수동: 층1 개발용 꺼짐과 켜짐 결과에서 세션 문항만 떼어 본다. 보고서 §8.2와 §8.3에 개발용 세션 0.867, 시험용 세션 0.933이 문서 검색과 따로 적혀 있다.

세션 recall@5가 0.85 이상이고 변화가 문서 검색과 따로 적혀 있다.

### A19. preset 목록에는 mmarco 하나만 있다
- covers: D18
- check: tests/test_reranker_config.py
- evidence: tests/test_reranker_config.py "test_presets_hold_only_mmarco_arm64_int8_at_a_pinned_revision"

`RERANK_PRESETS`에 mmarco의 `onnx/model_qint8_arm64.onnx` 항목 하나만 있고 고정 revision을 가진다.

### A20. `build_context_pack` 적중이 회귀하지 않는다
- covers: D6, D16
- check: 수동: 목표4 질문 37문항을 재정렬 꺼짐·켜짐으로 `build_context_pack`에 돌려 적중 수를 비교한다
- evidence: 수동: 목표4 질문 37문항을 재정렬 꺼짐과 켜짐으로 `build_context_pack`에 돌려 적중 수를 비교한다. 보고서 §8.5에 꺼짐 34/37, 켜짐 35/37이 적혀 있다.

켜짐의 적중이 꺼짐(지금 0.92, 34/37)보다 낮지 않다.

## 9. Open decisions

### O1. 1초 예산을 넘는 고품질 모델 bge-reranker-v2-m3를 이번 범위에서 뺄까요?
- decides: D18

배경: 1순위 mmarco(119MB)는 1초 안으로 추정되지만 한국어 품질 수치가 없다. bge는 한국어 근거가 가장 많지만 질의당 4~9초로 추정되고 파일이 571MB다.

바뀌는 것:
1. 빼면 모델 선택지는 mmarco 하나다.
2. 선택 모드로 두면 켠 사용자의 검색 한 번에 수 초가 걸릴 수 있다.

위험: 빼면 mmarco 한국어 품질이 부족할 때 바로 바꿀 대안이 없다. 넣으면 측정·유지할 모델이 둘이 되고 570MB를 더 받는다.

권장: 뺀다. 1초를 넘는 검색은 목표8과 맞지 않고 나중에 preset 하나로 더할 수 있다. 답에 따라 preset 목록과 측정 대상이 바뀐다.

### O2. 측정 단계에서 mmarco 모델 파일(약 120MB)을 `~/llm/models`에 내려받아도 될까요?
- decides: D19

배경: 지연은 추정뿐이고, 이 Mac에서 재려면 모델 파일이 있어야 한다. 지금 그 폴더에는 임베딩 모델만 있다.

바뀌는 것:
1. 모델 폴더가 약 120MB 늘어난다.
2. 구현 뒤 `vg reranker use`가 같은 파일을 다시 받지 않는다.

위험: 승인하지 않으면 관문2를 잴 수 없어 구현 여부를 정할 수 없다.

권장: mmarco만 받는다. bge(약 570MB)는 범위에서 빼길 권장하므로 받지 않는다. 답에 따라 1단계 진행 여부가 정해진다.

### O3. 측정을 통과하면 재정렬 기본값을 켜짐으로 바꿀까요?
- decides: D17

배경: 이 spec은 꺼짐을 기본으로 두고 사용자가 명령으로 켜게 한다. 통과 뒤 기본으로 켜면 모든 사용자가 효과를 받는다.

바뀌는 것:
1. 켜짐이면 `vg setup`이 약 120MB를 더 받고 첫 검색이 적재로 느려진다.
2. 꺼짐이면 사용자가 `vg reranker use`를 한 번 실행해야 한다.

위험: 시험용 결과가 개발용보다 크게 낮은데 켜면 모든 사용자의 검색 순위가 나빠질 수 있다.

권장: 이번에는 꺼짐으로 두고 시험용 결과와 실제 사용을 본 뒤 다시 정한다. 개발용만으로 고른 값이라 과적합 위험이 있다. 답에 따라 `vg setup` 내려받기 크기와 기본 검색 순위가 바뀐다.
