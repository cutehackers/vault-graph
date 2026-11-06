# vg 검색 품질: 측정1에서 Vault 검색에 지는 원인과 고칠 곳

조사일 2026-11-07. 코드 기준 `feat/jh/session-memory-indexing` HEAD `61011ed`. 재현은 실제 Graph Home 복사본(scratchpad `gh-real`)에서 `vg search --format json`으로 했다. 읽기만 했다.

## 결론

측정1 차이(Vault 0.95 대 vg 0.55)는 순위 계산보다 결과 거르기에서 생긴다. 같은 20개 질문을 personal Vault 하나에서 모드만 바꿔 다시 쟀다.

| 실행 | hit@5 | 1위 적중 |
|---|---|---|
| `--vault-id personal --mode knowledge` (기본 모드) | 0.55 | - |
| `--vault-id personal --mode all` | 1.00 | 19/20 |

`--mode all`은 적중률이 오르지만 상위 5개 중 평균 약 3칸을 같은 문서의 다른 조각이 차지하고 `wiki/log.md`가 끼어든다. 그래서 모드만 바꾸면 안 된다. 결과 단위를 문서로 바꾸고, 역할은 거르기 대신 순위 가중치로 쓰고, 파일 종류마다 색인 단위를 다르게 해야 한다.

이 질문 세트는 질문이 곧 제목이라 `--mode all`에서 이미 포화된다. 아래 원인5~8의 효과는 이 세트로 잴 수 없다. 의역 질문, 한국어 조사 질문, MRR, 상위 5개의 서로 다른 문서 수를 더해야 한다(제안 측정 참고).

## 원인 (영향 큰 순)

### 원인1. 기본 knowledge 모드가 `wiki/sources/`를 버린다 (측정1 실패 9개 중 8개)

- `SEARCH_MODE_ROLES["knowledge"]`는 `canonical_knowledge` 하나다. `src/vault_graph/retrieval/search/retrieval_service.py:43-57@61011ed`
- `wiki/sources/`와 `type: source`는 `source_manifest`가 된다. `src/vault_graph/indexing/ingestion/document_authority.py:41-42@61011ed`
- 역할 필터는 키워드 SQL(`src/vault_graph/storage/local/sqlite_keyword_index.py:70,82@61011ed`)과 벡터 조건(`src/vault_graph/storage/local/vector_store_adapter.py:103-106@61011ed`) 양쪽에서 후보 단계에 걸린다. 걸러진 페이지는 순위에 오를 기회가 없다.
- CLI 기본값 `src/vault_graph/interface/cli/main.py:869@61011ed`, MCP `search_vault` 기본값 `src/vault_graph/interface/mcp/mcp_tools.py:106,850@61011ed`가 모두 knowledge다. 에이전트도 같은 이유로 source 페이지를 못 본다.
- Vault 검색(`$HOME/vault/tools/wiki/lib/search.py`)은 `wiki/` 전체를 보고 `log`, `map`, `index` 유형만 뺀다.
- 재현: "Hobby concept preview hobby-05"는 knowledge에서 `hobby-service-ideas.md`가 1위이고 정답이 없다. all에서는 `wiki/sources/hobby-05.md`가 키워드 1위, 벡터 1위로 1위다. m1-07, m1-17도 같은 양상이다.

고칠 것

- 기본 모드의 후보 역할에 `source_manifest`를 넣는다. `raw_evidence`(세션 포함)는 넣지 않는다. curate_memory 프롬프트의 "세션 파일은 기본 knowledge 모드 검색에는 나오지 않는다"(`src/vault_graph/interface/mcp/mcp_prompts.py:251-254@61011ed`)는 그대로 참이다.
- 역할을 거르기 대신 순위 가중치로도 쓴다. 예: `canonical_knowledge` 1.0, `source_manifest` 0.8. 같은 주제의 정리된 페이지가 있으면 정리된 페이지가 위에 오고, 출처 페이지 제목을 그대로 물으면 출처 페이지가 나온다.
- 효과: 측정1 0.55 → 약 0.95~1.0(위 표). 결정성 영향 없음.
- 위험: 모드와 역할의 대응표는 spec·문서에 적힌 계약이다. 바꾸려면 결정 기록이 필요하다. source 페이지가 짧은 조각이라(원인7) 다른 질의의 상위를 차지할 수 있으므로 원인3·7과 같이 넣는다.

### 원인2. provenance family가 서로 다른 페이지를 하나로 묶어 정답을 지운다 (m1-14)

- knowledge 모드는 같은 family의 결과를 하나만 남긴다. `src/vault_graph/retrieval/search/candidate_ranking.py:72-82@61011ed`
- family는 provenance 필드(`canonical_source`, `derived_from`, `supersedes`, `redirects`)가 가리키는 경로로 union-find를 한다. `src/vault_graph/indexing/ingestion/document_authority.py:16,66-72@61011ed`
- personal Vault의 정리 페이지 6개가 모두 `derived_from: ["AGENTS.md"]`라 한 family(`3c827a55…`)가 됐다: `compiled-knowledge.md`, `llm-maintained-wiki.md`, `source-of-truth.md`, `use-markdown-for-compiled-knowledge.md`, `ingest-new-source.md`, `wiki-linting.md`. 공통 출처 하나가 형제 페이지를 묶는다. personal의 canonical 66개가 family 45개로 줄어, 21개 페이지가 다른 페이지 뒤에 숨을 수 있다.
- 재현: "Compiled Knowledge"(personal, knowledge)에서 `compiled-knowledge.md`는 상위 10개 어디에도 없다. 키워드 후보에는 13위로 있지만 같은 family의 `use-markdown-for-compiled-knowledge.md`가 먼저 자리를 잡아 지워졌다.

고칠 것

- 접는 조건을 "같은 family"에서 "한 결과가 다른 결과의 provenance 대상이다"(직접 조상·자손)로 좁힌다. 형제는 접지 않는다.
- 또는 `derived_from`은 접기에서 빼고 `supersedes`, `redirects`, `canonical_source`만 쓴다. `derived_from`은 근거 연결(`supporting_evidence`)에만 쓴다.
- 효과: 측정1 m1-14 회복. 같은 주제 페이지가 숨는 일이 사라진다. 결정성 영향 없음.
- 위험: `result_family_duplication` 값이 바뀐다. quick refresh가 family를 같이 읽는 규칙(`docs/SPEC.md:112`, 2026-11-03 발견13)은 색인 쪽이라 그대로 둘 수 있다.

### 원인3. 결과 단위가 조각이다 (문서 하나가 상위 5칸 중 3칸을 차지)

- 융합(`candidate_ranking.py:26-56@61011ed`)과 결과 조립은 `(vault_id, chunk_id)` 단위다. 조각을 문서로 묶는 것은 세션의 `parent_key`뿐이다. `src/vault_graph/retrieval/search/evidence_result_assembly.py:173-191@61011ed`
- knowledge 모드에서는 원인2의 family 접기가 우연히 문서 중복을 없애 주지만, 다른 모드에는 아무 장치가 없다. `--mode all` 측정에서 20개 중 19개 질문이 상위 5개에 같은 문서를 2~4번 담았다.
- 문서 점수도 없다. 조각 여러 개가 맞은 문서와 조각 하나만 맞은 문서를 구별하지 못한다.

고칠 것

- 일반 문서도 결과 단위를 묶는다. `_group_by_parent`의 묶음 키를 "세션은 `parent_key`, 그 밖은 `document_id`"로 일반화한다. 결과에는 가장 좋은 조각을 인용하고 맞은 조각 수를 붙인다(세션 `parent_grouped`와 같은 형식).
- 문서 점수는 가장 좋은 조각 점수에 나머지 조각을 작게 더한다(예: 최고값 + 0.1×나머지 합, 상위 3개까지). 고정된 식이라 결정적이다.
- 파일 종류별 단위: 정리 페이지와 source 페이지는 페이지 하나, 세션은 교환 하나(지금), 긴 raw 파일은 문서 하나로 묶되 맞은 구간 위치를 여러 개 보여 준다.
- 위험: 근거 id와 인용은 조각 그대로이므로 근거 검증 규칙은 바뀌지 않는다. 결과 수가 줄어 `candidate_limit = max(limit*4, 20)`(`retrieval_service.py:123@61011ed`)이 모자랄 수 있으니 묶은 뒤 개수로 다시 맞춘다.

### 원인4. Vault마다 순위를 1부터 다시 매기고, 같은 페이지가 Vault마다 따로 나온다

- 키워드와 벡터 후보를 Vault(범위)마다 따로 구하고 이어 붙인다. 각 목록의 순위가 1부터 다시 시작한다. `retrieval_service.py:238-248,268-281@61011ed`
- RRF는 순위만 쓰므로(`candidate_ranking.py:12-13,41@61011ed`) Vault 6개의 1위가 모두 같은 점수가 된다.
- 재현: "Compiled Knowledge" `--all-vaults`에서 1~5위가 모두 템플릿에서 복사된 `wiki/decisions/use-markdown-for-compiled-knowledge.md`다(981park, bake, sgp-981-app, vault-builder, vault-graph). 점수도 같다(keyword 2위, vector 4위).
- 측정1도 이 영향을 받았다. 측정 스크립트는 `vg search`를 Vault 지정 없이 불러(`tests/benchmarks/measure_vault_search_parity.py:121-131@61011ed`) 기본 범위의 여러 Vault를 찾고, Vault 검색은 personal 하나만 찾는다. 기록된 결과에 같은 경로가 두 번 나오는 이유다.

고칠 것

- 키워드는 범위 전체를 쿼리 하나로 찾는다. 키워드 표는 메타데이터 DB 하나에 있어 bm25 통계가 이미 전체 기준이다. `vault_id IN (...)`과 범위 조건을 OR로 묶으면 된다.
- 벡터는 코사인 점수가 Vault 사이에서 비교되므로 범위별 결과를 점수로 합쳐 다시 순위를 매긴다.
- 내용이 같은 문서(같은 `content_hash`)는 Vault가 달라도 한 결과로 보이고 "다른 Vault에도 있음"을 붙인다. 정렬 키에 vault_id가 이미 있어 결정적이다.
- 측정1은 `--vault-id personal`로 돌려야 Vault 검색과 같은 범위를 비교한다.
- 위험: 범위 지정 규칙(scope rule)은 바뀌지 않는다. 중복 접기는 보여 주는 방식만 바꾼다.

### 원인5. 키워드 점수가 제목을 특별히 보지 않고, 한 신호만 강한 결과는 RRF에서 진다

- FTS5 열은 `path`, `section`, `title`, `frontmatter`, `text`이고 `bm25(keyword_chunks)`를 열 가중치 없이 쓴다(모두 1.0). `sqlite_keyword_index.py:38-47,76@61011ed`
- 질의는 낱말을 모두 OR로 잇는다. 구(phrase) 일치나 모든 낱말 일치에 더 주는 점수가 없다. `sqlite_keyword_index.py:264-272@61011ed`
- `title`은 문서 제목을 모든 조각에 똑같이 넣는다(`:233,358-360`). `frontmatter`는 frontmatter 전체 JSON이다(`:240-249`). `"type": "source"` 같은 키·값이 모든 페이지에 들어가 잡음이 된다.
- 재현: "Compiled Knowledge"에서 키워드 1~12위가 `retrieval-augmented-compiled-knowledge.md`와 `use-markdown-for-compiled-knowledge.md`의 조각이고, 제목이 질문과 똑같은 `compiled-knowledge.md`는 13위다. `--mode all`에서도 5위에 그친다.
- RRF k=60이라 키워드 1위만 받은 결과(1/61 ≈ 0.0164)는 키워드 38위·벡터 15위를 받은 `wiki/overview.md` 조각(0.0102 + 0.0133 = 0.0235)보다 낮다. 제목이 정확히 맞아도 두 신호에 걸친 허브 조각에 진다.
- Vault 검색은 페이지 단위로 제목 6, 요약 3, 태그 3, 본문 1(본문은 10회까지)로 센다.

고칠 것

- 열 가중치를 준다: `bm25(keyword_chunks, 2.0, 2.0, 8.0, 3.0, 1.0)`(path, section, title, frontmatter, text). 숫자는 측정으로 정한다.
- `frontmatter` 열을 JSON 전체 대신 `summary`, `tags`, `aliases` 값만 담는다. 세션 `keyword_metadata` 줄은 그대로 둔다.
- 문서 단위 "제목 일치" 신호를 새로 둔다. 질문을 소문자·공백 정리한 뒤 문서 제목, 별칭, 파일 이름(slug를 공백으로)과 비교해 완전 일치, 모든 낱말 포함 순으로 순위를 매기고 RRF에 세 번째 목록으로 넣는다(가중치 1.0 이상). 계산은 문서 표만 읽으므로 결정적이다.
- 위험: 키워드 스키마 버전을 올려 키워드 표를 다시 만들어야 한다(임베딩은 다시 만들지 않는다). spec 4.2.9 표의 "FTS 스키마(열 다섯 개)"는 열 개수는 같고 열 내용과 가중치가 바뀐다. 결정성 시험의 키워드 기대값을 다시 만들어야 한다.

### 원인6. 한국어 조사를 처리하지 않는다

- 토크나이저는 `unicode61`(`sqlite_keyword_index.py:46@61011ed`)이고 질의 토큰은 정규식 `[\w가-힣]+`로 자를 뿐이다(`:271-272`). 저장소 어디에도 조사 처리 코드가 없다.
- 재현(personal 키워드 직접 질의): "아이디어"는 15개 이상 맞고 "아이디어를"은 3개만 맞는다. 본문의 "아이디어를"도 질문 "아이디어"와 맞지 않는다.
- spec 4.2.9 표는 "한국어 조사 처리"가 바뀌지 않는다고 적었지만 처리 자체가 없다. 그 칸은 사실과 다르다.
- Vault 검색은 질의 낱말 끝의 조사를 떼고 부분 문자열로 맞춘다.

고칠 것

- 질의 쪽: 한글 낱말 끝 조사를 떼고(Vault 검색과 같은 목록) 한글 낱말은 앞부분 일치(`"아이디어"*`)로 찾는다. 색인을 다시 만들지 않는다.
- 문서 쪽까지 하려면 한글용 `trigram` 열을 더하는 방법이 있다. 키워드 표 크기가 커지므로 질의 쪽을 먼저 하고 한국어 질문 세트로 잰다.
- 위험: 앞부분 일치는 짧은 낱말에서 결과가 늘어난다. 두 글자 이하는 앞부분 일치를 하지 않는다.

### 원인7. 허브 페이지와 템플릿 구역 조각이 많은 질의의 상위를 차지한다

- 일반 조각기는 제목(heading)마다 자른다(`src/vault_graph/indexing/ingestion/document_chunking.py:151-153@61011ed`). 정리 페이지는 H2마다 4~54단어짜리 조각이 된다. 예: `compiled-knowledge.md` 280단어가 조각 11개, 그중 첫 조각은 0단어(제목만)다.
- personal 기준 조각 평균: canonical 50.7단어(빈 조각 60개), source 6.5단어(빈 조각 49개).
- 모든 페이지에 같은 템플릿 구역이 있다. canonical 조각 중 "Claim Evidence" 46개, "Summary" 20개, "Sources" 10개. 짧고 형태가 같아 벡터가 서로 비슷하다. 재현: "Rail Historical Plan 2026 04 15 …"(knowledge)의 1~5위가 모두 서로 다른 페이지의 "Claim Evidence" 구역이다.
- `wiki/overview.md`(조각 9개, 여러 페이지 이름을 나열)와 `wiki/inbox.md`는 role이 canonical이고 낮추는 장치가 없다. 기존 측정1 결과에서 overview가 20개 중 17개 질문의 상위 5개에 나왔다(inbox는 7개).

고칠 것 (파일 종류별)

- 정리 페이지(`wiki/concepts|decisions|systems|workflows|…`): 대부분 512토큰보다 짧으므로 페이지 전체를 한 조각으로 둔다. 길 때만 H2로 나눈다. 템플릿 구역(Claim Evidence, Change Notes, Related, Supporting Sources, Sources)은 벡터 입력에서 빼고 키워드에만 낮은 가중치로 남긴다.
- source 페이지(`wiki/sources/`): 짧으므로 페이지 하나를 한 조각으로 둔다. "Registration", "Durable Knowledge Links" 구역은 벡터 입력에서 뺀다.
- 허브 페이지(`type: overview`, `inbox`, 그리고 다른 페이지 링크가 본문 대부분인 페이지): role을 `generated_view`로 두거나 순위 가중치를 0.5로 낮춘다. 제목을 그대로 물으면 원인5의 제목 신호로 여전히 1위가 된다(m1-19).
- raw 원문(긴 문서): 지금처럼 구역·창 단위로 자르고 원인3으로 문서 하나로 묶는다.
- 세션(`raw/sessions/`): 지금의 v2 교환 창 그대로. 창 크기는 별도 결정(위험A4)이다.
- 코드: `vg search`에 들어오지 않는다. 코드는 별도 심볼 FTS(`src/vault_graph/storage/local/sqlite_code_projection_store.py:622-660@61011ed`)와 `explore_project`로 찾는다. 이번 문제와 관계없다.
- 위험: 조각기 버전이 바뀌면 일반 문서 벡터를 모두 다시 만든다(spec 4.2.9 "일반 문서의 벡터는 바뀌지 않는다"와 충돌). 이 spec 밖의 다음 작업으로 둔다.

### 원인8. 문서 단위 표현이 없다

- 벡터는 조각마다 하나뿐이다. 임베딩 입력은 `Section path: H1 > H2` 한 줄과 본문이다(`document_chunking.py:173-179@61011ed`). frontmatter의 `title`, `summary`, `tags`는 임베딩에 들어가지 않는다. 제목만 담은 0단어 조각이 우연히 제목 벡터 역할을 한다.
- 길이 보정은 bm25의 열 길이 보정뿐이고 문서 길이 개념은 없다. 긴 페이지는 조각 수가 많아 후보 목록을 더 많이 차지한다(원인5 재현의 1~12위).

고칠 것

- 문서마다 "페이지 카드" 조각을 하나 더 만든다: 제목, 별칭, 요약, 태그, 파일 이름. frontmatter에서 기계적으로 만들므로 원칙1("요약을 vault-graph 안에서 생성하지 않는다")에 걸리지 않는다. 키워드와 벡터 모두에 넣고, 맞으면 문서 결과로 묶인다(원인3).
- 세션은 교환의 첫 사용자 발화를 카드로 쓸 수 있다. 세션 MRR이 단계와 관계없이 약 0.70인 것은 맞는 창이 교환 안에서 여러 개로 흩어지고 점수가 합쳐지지 않기 때문일 가능성이 있다(검증 안 함). 원인3의 문서 점수 식을 교환에도 적용해 잰다.
- 위험: 조각 수가 문서 수만큼 늘고 임베딩을 다시 만든다.

## 확인한 것 중 원인이 아닌 것

- e5 머리말: 질의 `query: `, 문서 `passage: `를 바르게 붙인다. `src/vault_graph/interface/composition/adapters/text_embeddings.py:80-81,214-221@61011ed`
- 벡터 검색은 범위·역할로 거른 뒤 전부 비교한다(근사 검색으로 놓치지 않는다). `packages/vector-search/src/vector_search/sqlite_reader.py:133-170@61011ed`
- 질의 정규화는 앞뒤 공백 제거뿐이다(`retrieval_service.py:103`). FTS가 대소문자를 무시하므로 문제가 아니다.

## 고치는 순서 제안

| 단계 | 내용 | 다시 만들 것 | 기대 효과 |
|---|---|---|---|
| 1 | 원인1(기본 모드에 source 추가, 역할 가중치), 원인2(형제 접기 중단), 원인3(문서 단위 묶기), 원인4(범위 전체 순위, 중복 접기), 원인6 질의 쪽 | 없음 | 측정1 0.55 → 약 0.95 이상, 상위 5개가 서로 다른 문서 |
| 2 | 원인5(열 가중치, frontmatter 열 정리, 제목 신호) | 키워드 표 | 제목 질문 1위율, 허브 조각 밀어내기 |
| 3 | 원인7(종류별 조각 단위, 템플릿 구역 제외, 허브 가중치), 원인8(페이지 카드) | 일반 문서 벡터 | 의역 질문 품질 |

## 제안 측정

- 측정1을 `--vault-id personal`로 돌리고 hit@5와 함께 MRR, 상위 5개의 서로 다른 문서 수를 기록한다.
- 제목이 아닌 의역 질문 20개, 조사가 붙은 한국어 질문 10개를 더한다. 지금 세트는 `--mode all`만으로 1.0이 되어 원인5~8을 구별하지 못한다.
- 재현 스크립트와 결과: scratchpad `sq-run.py`, `sq-runs/m1-variants.json`.
