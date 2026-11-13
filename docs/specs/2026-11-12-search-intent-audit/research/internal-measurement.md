# 내부 측정: 같은 의도를 한국어와 영어로 물었을 때의 검색 결과

조사일: 2026-11-12. 실제 Graph Home(`$HOME/.vault-graph`, 활성 세대 `b97b5cbf`, e5-small, `vector_stale_count: 0`)에서 `vg search --vault-id personal --limit 20 --format json`(기본 knowledge 모드)을 질문마다 실행했다. 질문 파일과 결과는 저장소 밖(세션 scratchpad)에 두었다.

## 방법

- 의도 20개. 각 의도를 한국어 한 문장, 영어 한 문장으로 썼다(총 40문항). 종류: 규칙 9, 결정 6, 방법 4, 개념 4(겹침 없음 기준 대표 종류 하나).
- 정답은 personal Vault `wiki/` 페이지 하나다. 정답 페이지 20개 중 17개는 영어, 3개는 영어 제목에 한국어가 섞인 페이지다.
- 질문은 에이전트가 실제로 던질 법한 형태로 썼다. 제목 단어를 그대로 쓰지 않았다.

## 사실

### X-1
- source: 세션 scratchpad `probe/results-knowledge.json`, 2026-11-12 측정
- basis: 없음

같은 의도 20개에서 영어 질문은 recall@1 0.90, recall@5 1.00, MRR 0.95다. 한국어 질문은 recall@1 0.25, recall@5 0.75, MRR 0.41이다. 한국어 질문 중 정답이 상위 20 밖인 것이 1개(청크 원문 저장소 결정), 10위 밖인 것이 3개다.

### X-2
- source: 세션 scratchpad `probe/results-knowledge.json`
- basis: X-1

한국어 질문 20개의 상위 3칸(60칸) 중 45칸을 질문과 무관한 한국어 페이지 3개(`wiki/concepts/hobby-service-ideas.md`, `wiki/concepts/development-service-ideas.md`, `wiki/systems/babywatcher.md`)가 차지한다. 영어 질문에서는 0칸이다. 이 3개는 personal 위키에서 본문이 한국어인 거의 유일한 페이지다.

### X-3
- source: `vg search` JSON의 signals, 질문 3개 직접 확인
- basis: X-2

벡터 신호의 원인: "정리해 달라고 하면 어디까지 지워야 해?"의 벡터 1위는 hobby-service-ideas(cosine 0.838), 2위 development-service-ideas(0.835)이고 정답 `cleanup-removes-every-trace.md`는 벡터 44위다. e5-small은 같은 언어라는 점을 주제보다 크게 본다.

### X-4
- source: `src/vault_graph/storage/local/sqlite_keyword_index.py:442-446@c2df3af`, `query_terms` 직접 실행
- basis: X-2

키워드 신호의 원인: 질의는 모든 단어를 OR로 묶는다. "청크 원문은 어느 저장소 하나만 들고 있어야 해?"는 `"청크" "원문" "어느" "저장소"* "하나" "들고" "있어야"* "해"`가 되고, 영어 정답 페이지에는 어느 단어도 없다. "하나", "어느", "해" 같은 기능어는 한국어 페이지에만 맞아 babywatcher가 키워드 1위가 된다. 한국어 질문 20개 중 정답이 키워드 상위 10에 든 것은 5개다(영어 20개 중 20개).

### X-5
- source: 세션 scratchpad 융합 시뮬레이션(한국어 결과와 영어 결과를 RRF k=60으로 합침)
- basis: X-1

한국어 질문과 그 영어 번역을 각각 검색해 합치면 recall@1 0.75, recall@5 0.95, MRR 0.83이다. 영어만 쓴 0.95보다 낮다. 한국어 결과 목록이 X-2의 한국어 페이지를 계속 끌어올리기 때문이다.

### X-6
- source: `src/vault_graph/interface/mcp/mcp_tools.py:843-864@c2df3af`, 실행 중인 MCP 서버의 도구 스키마
- basis: 없음

MCP 도구 `search_vault`, `build_context_pack`에 설명(description)이 없다. 에이전트는 매개변수 이름만 받는다. 어떤 언어로, 어떤 형태(키워드 대 문장)로 질의를 써야 하는지, `mode` 값이 무엇인지 알려 주는 문장이 없다.

### X-7
- source: `docs/specs/2026-11-04-embedding-model-selection/spec.md:17,183,195@c2df3af`, 같은 spec `research/measurement-and-data.md` "사용자 Vault 구성"
- basis: 없음

임베딩 모델은 공개 한국어 단일 언어 검색 점수(한국어 질의 → 한국어 문서, NDCG@10)로 골랐다. 같은 조사 문서는 "wiki 페이지는 거의 영어이고 질문은 주로 짧은 한국어"라고 적었다. 실제 사용 형태인 한국어 질의 → 영어 페이지(교차 언어) 점수는 비교하지 않았다.

### X-8
- source: `docs/design/reports/2026-11-search-quality.md@c2df3af`
- basis: 없음

이전 평가 세트(wiki 35문항)는 20문항이 제목 그대로다. 그 세트의 의역 질문 recall@5는 0.57, 방법 질문은 0.33이다. 질문 언어별 수치는 보고하지 않았다. 질문 세트는 저장소 밖에 있어 이번에 다시 쓰지 못했다.

### X-9
- source: `src/vault_graph/storage/local/usage_log.py@c2df3af`, `grep append_events src/`
- basis: 없음

사용 기록은 회상 이벤트와 MCP 리소스 읽기만 남긴다. 검색 질의 텍스트와 그 뒤에 에이전트가 연 페이지는 남기지 않는다. 그래서 실제 질의의 언어 비율과 성공률을 알 수 없다.

### X-10
- source: `src/vault_graph/context/answer/evidence_planner.py`, `src/vault_graph/context/pack/context_pack_builder.py`, `src/vault_graph/context/pack/recall.py:3@c2df3af`
- basis: X-1

`ask_vault`와 `build_context_pack`은 같은 `RetrievalService`를 쓴다. 그래서 X-1의 차이가 세 도구 모두에 그대로 있다. 세션 시작 회상은 검색을 쓰지 않고 메타데이터로 고르므로 영향이 없다.

### X-11
- source: `vg search` 5회 직접 실행, 2026-11-12
- basis: X-4

기능어를 뺀 한국어 키워드 질의("블록팟 로그 형식", "정리 요청 삭제 범위", "청크 원문 저장소 소유", "결정 요청 맥락 설명", "검증 명령 위험도 단계")도 5개 모두 상위 3칸에 X-2의 한국어 페이지가 2~3개 온다. 정답 영어 페이지는 1위에 오지 않는다. 한국어 불용어 처리만으로는 고쳐지지 않는다.

## 이번 측정의 한계

- 질문 40개는 한 사람(에이전트)이 썼다. 정답 페이지를 보고 썼으므로 영어 질문이 실제보다 쉬울 수 있다.
- personal Vault 하나만 쟀다. 세션 원문(한국어 비중이 큼)은 재지 않았다.
