# Vault Graph Specification: Local-Graph

- 상태: 활성 제품 계약
- 시작: 2026-10-29 (결정4 옵션1, [DECISIONS](DECISIONS.md))
- 상세 설계: [spec 2026-10-29-local-graph-memory-layer](specs/2026-10-29-local-graph-memory-layer/spec.md)
- 보관 문서: [SPEC v1.2](archive/SPEC-v1.2.md), [SPEC v5.0 Software Invariant Engine](archive/SPEC-v5.0.md)

## 목차

1. 제품 정의와 원칙
2. 역할 분담
3. 가치
4. 읽기·쓰기 경계
5. 인터페이스
6. 외부 계약
7. Context Pack 계약
8. 독립 모듈 5개
9. 단계
10. 보관 문서

## 1. 제품 정의와 원칙

vault-graph는 Vault 위에서 도는 로컬 검색·회상 계층이다. Vault 원문, wiki, 코드를 읽어 색인하고, 에이전트가 필요한 기억을 출처와 함께 토큰 예산 안에 돌려준다. Vault는 vault-graph 없이도 동작한다.

방향 이름은 Local-Graph다. 핵심은 Local이고, Graph(관계 추적)는 보조 가치다.

1. 원칙1 Local: 모든 처리가 이 컴퓨터 안에서 끝난다. 호스팅 서비스, API 키, LLM 호출이 없다(결정7). 질의 답변, 요약, 사실 추출을 vault-graph 안에서 생성하지 않는다. 추론은 호출한 에이전트가 한다.
2. 원칙2 원본은 Vault: 기억의 원본은 Vault의 Markdown 파일이다. vault-graph 색인은 지워도 다시 만들 수 있는 파생 데이터이며 지식 원본이 아니다.
3. 원칙3 `wiki/`는 검증 경로로만 바뀐다: Vault `wiki/`는 Vault 도구의 검증 경로(publish-draft 등)를 거쳐서만 바뀐다.
4. 원칙4 vault-graph는 Vault 파일을 직접 쓰지 않는다: vault-graph 프로세스는 Vault 파일을 직접 만들거나 고치거나 이름을 바꾸거나 지우지 않는다. Vault에 쓰는 길은 하나이며, remember가 Vault 도구의 publish-draft를 실행해 그 검증을 거치게 하는 것이다(결정8).
5. 원칙5 `raw/`에 쓰지 않는다: vault-graph는 어떤 경로로도 Vault `raw/`에 쓰지 않는다.
6. 원칙6 연결 정보는 `vault-map.json` 하나: 프로젝트와 Vault의 연결 정보는 사용자 범위의 `vault-map.json`이 원본이고, vault-graph는 이 파일을 읽기만 한다(결정9).

## 2. 역할 분담

| 영역 | Vault (llm-wiki) | 사용자 범위 (vault-builder가 설치) | vault-graph |
|---|---|---|---|
| 저장 | 기억 원본 Markdown | 없음 | 없음. 색인은 지워도 다시 만든다 |
| 쓰기 | `wiki/`는 publish-draft 등 검증 경로로만. `raw/`는 사람이 요청할 때만(Vault `AGENTS.md` 규칙1) | 없음 | remember가 기록을 publish-draft에 맡긴다(결정8). 직접 쓰는 곳은 Graph Home뿐이다 |
| Vault·프로젝트 연결 | 자기 폴더 하나만 다룬다 | `vault-map.json`, llm-wiki router. vault-builder가 install·link·unlink로 고친다 | `vault-map.json`을 읽기만 한다(결정9) |
| 검색 | `wiki/`만. 질의마다 파일을 다시 읽고 한국어 조사를 뗀다 | router가 연결된 Vault 전체에 검색을 보낸다 | `raw/`·`wiki/`·`docs/`·`scratch/reports/`를 상시 색인하고 키워드·의미·그래프 후보를 합친다 |
| 회상 | 없음 | `recall.sh`: 고정 섹션 3개, 1,500토큰 | 세션 시작 회상. vault-graph가 없으면 훅이 `recall.sh`를 쓴다(결정10) |
| 코드 | 없음 | 없음 | 심볼, 호출, 영향 범위와 결정 기록을 연결한다 |
| LLM | 정리 스킬에서 쓴다 | 없음 | 부르지 않는다(결정7) |

## 3. 가치

| 코드 | 가치 | Vault만으로는 | vault-graph 현재 | 남은 일 |
|---|---|---|---|---|
| 가치1 | 대량 원문 검색: 세션 원문 수천 개에서 찾기 | `wiki/`만 찾고 매번 전체를 다시 읽는다 | 구현. `raw/` 포함 상시 색인, 증분 색인 | 세션 수집(의존2, 의존3)이 먼저 있어야 성립한다. 규모 측정 |
| 가치2 | 의미 검색: "인증 실패"로 "로그인 오류" 찾기 | 없음 | 구현. 다국어 MiniLM 임베딩 | 한국어 품질 측정(n차-4). 한국어 키워드는 지금 Vault 검색이 낫다(1차-5에서 보강) |
| 가치3 | 코드 위키: 코드와 결정·작업 기록을 함께 조회 | 코드를 읽지 않는다 | 일부. Python·Dart 코드 투영, `explore_project`. 검색 색인과 분리 | `explain_symbol`, 질의 하나로 코드와 기억 찾기(n차-3) |
| 가치4 | 관련 기억만 담은 회상 | `recall.sh`는 고정 섹션만 출력한다 | 구현. context pack(기본 8,000토큰 예산) | 세션 시작 회상(1차-3) |
| 가치5 | 문단 단위 근거: 중복 제거, 인용 검증 | 페이지 단위 결과 | 구현. 문단 조각, provenance 묶음, 인용 검증 | 대체된 claim 제외를 Vault와 맞추기(n차-1) |
| 가치6 | 관계 추적(보조) | 링크와 지도만 있다 | 구현. `find_related`, `get_decision_trace` | 없음 |

가치가 아닌 것:

- 세션 수집 자체. Vault 도구의 몫이다.
- `wiki/`만 대상으로 한 "빠른 검색". `wiki/` 126쪽 규모에서는 측정 전이고 근거가 약하다.
- 쓰기, 검증, 여러 Vault 연결. Vault와 vault-builder의 몫이다.

가치1과 가치2는 아직 숫자로 확인되지 않았다. 측정1(6절)로 확인한다.

## 4. 읽기·쓰기 경계

읽는 대상:

- Vault의 `raw/`, `wiki/`, `docs/`, `scratch/reports/` (기본 색인 범위 `DEFAULT_CONTENT_SCOPES`). 검토 대기열 `scratch/review/`는 색인하지 않는다(결정6).
- 등록한 코드 저장소의 소스.
- 사용자 범위의 `vault-map.json`.

쓰는 대상:

- Graph Home(`$HOME/.vault-graph` 등) 아래의 파생 데이터와 설정. 명시적 명령(setup, index, watch, MCP 등록 등)에서만 기록한다. 정상 조회는 색인·설정을 기록하지 않는다. 예외는 세션 시작 회상과 MCP 페이지 리소스 읽기가 Graph Home `usage/`에 사용 기록을 덧붙여 쓰는 것 하나다.
- remember를 통한 Vault 도구 publish-draft 실행. 이것이 Vault에 쓰는 유일한 길이다. 일반 조회·색인·watch와 다른 MCP 도구는 publish-draft를 실행하지 않는다.

쓰지 않는 대상:

- Vault 파일을 직접 만들거나 고치거나 이름을 바꾸거나 지우지 않는다.
- Vault `raw/`에는 어떤 경로로도 쓰지 않는다.
- 코드 저장소 소스와 `vault-map.json`은 고치지 않는다.

이 경계는 `AGENTS.md` Project Boundary, [ARCHITECTURE.md](ARCHITECTURE.md) §4, [VG-MOD](design/specs/2026-10-15-vault-graph-modular-architecture-ko.md) INV-01·INV-02·INV-04와 같은 원칙이다.

## 5. 인터페이스

유지한다:

- 기존 CLI 명령(`vg setup`, `vg vault add`, `vg index`, `vg watch`, `vg search`, `vg ask`, `vg context`, `vg status` 등)의 이름·인자·응답 형식.
- MCP 도구 11개: `ask_vault`, `search_vault`, `build_context_pack`, `find_related`, `get_decision_trace`, `check_index_status`, `explain_result`, `summarize_project_memory`, `get_open_questions`, `get_recent_changes`, `explore_project`. 이름과 입력·출력 스키마를 바꾸지 않는다.
- MCP 리소스와 로컬 HTTP(FastAPI) 응답.
- `project-bindings.json`, `vg setup --vault`, `vg vault add`는 1차에서 지우지 않는다. 제거는 n차-7이다.

추가한다(1차):

- CLI `vg hook session-start [--graph-home PATH] [--vault-map PATH] [--max-tokens N]`. 표준 입력으로 Claude Code SessionStart 훅 JSON을 받아 회상 묶음(Markdown)을 표준 출력에 낸다. 종료 코드 0은 "처리함"(출력이 비어 있을 수 있음), 3은 "회상할 수 없음"이다. 세부는 상세 설계 4.2.3.
- MCP 도구 `remember`. 에이전트가 넘긴 필드로 draft를 만들어 Vault 도구의 publish-draft를 실행한다. 결과는 `published`, `rejected`, `error` 중 하나다. MCP 도구는 12개가 된다. 세부는 상세 설계 4.2.4.

## 6. 외부 계약

1. `vault-map.json` version 2 읽기
   - 기본 경로 `$HOME/.claude/vault-builder/vault-map.json`. CLI `--vault-map PATH`와 환경 변수 `VAULT_GRAPH_VAULT_MAP`으로 바꿀 수 있다.
   - 형식: `vaults`는 이름 → `{path, role}`, `projects`는 프로젝트 id → `{root, vaults: [Vault 이름…], remote}`.
   - 프로젝트 찾기 규칙은 llm-wiki router(`find_project`)가 소유하고, vault-graph는 같은 규칙을 따른다.
   - `version`이 2가 아니거나 형식이 깨졌으면 쓰지 않고 경고한다. 파일을 고치거나 만들지 않는다.
2. publish-draft 호출과 draft 형식
   - Vault 루트를 작업 디렉터리로 하여 `<vault-graph의 Python> -I -B tools/wiki/cli.py publish-draft <draft_path>`를 실행한다. `--report`는 주지 않는다. 시간 제한은 120초다.
   - draft는 에이전트가 넘긴 필드만으로 결정적으로 만들고 Vault 도구의 draft 형식을 따른다. Vault와 Graph Home 밖의 임시 디렉터리에 만들고 실행 뒤 지운다.
   - draft 형식의 버전 표시는 아직 없다(의존6).
3. Vault 검색과의 비교 방법(측정1)
   - 같은 질문 20개를 Vault 검색(`tools/wiki/cli.py search <질문> --limit 5`)과 `vg search`(기본 모드, 상위 5개)에 넣어 실제 대기 시간과 상위 5개 적중률을 비교한다.
   - 조건A는 지금 Vault, 조건B는 세션 원문이 쌓인 Vault다.
   - 성공 기준: 두 조건 모두에서 `vg search`의 상위 5개 적중률이 Vault 검색보다 높다.
   - 질문과 질문별 결과는 저장소 밖에 두고, 합계만 `docs/design/reports/`에 커밋한다.

## 7. Context Pack 계약

보관본 [SPEC v5.0](archive/SPEC-v5.0.md) §9.6 "기존 Context Pack 호환성 계약"을 그대로 옮긴다. 이 절의 JSON은 `tests/test_context_pack_docs_contract.py`가 DTO와 비교한다.

1단계(공존 단계)에서 기존 Vault Graph 컨텍스트 팩 빌더 및 회귀 테스트 스위트와의 100% 하위 호환성을 보장하기 위해 유지되는 Context Pack JSON 규격입니다:

Minimum JSON shape:

```json
{
  "context_pack_schema_version": "context-pack-v1",
  "pack_id": "sha256-of-canonical-pack-identity",
  "goal": "Implement GraphRAG MVP",
  "scope": {
    "requested": {
      "vault_ids": ["main"],
      "content_scopes": ["wiki", "docs"],
      "include_cross_vault": false
    },
    "actual_scopes": [
      {
        "vault_ids": ["main"],
        "content_scopes": ["wiki", "docs"],
        "include_cross_vault": false,
        "scope_key": "main:wiki,docs:local"
      }
    ]
  },
  "vaults": [
    {
      "vault_id": "main",
      "display_name": "Main Vault"
    }
  ],
  "vault_revisions": [
    {
      "vault_id": "main",
      "revision": "git-sha-or-file-snapshot-id",
      "revision_kind": "git"
    }
  ],
  "backend": {
    "metadata_store": {
      "name": "sqlite",
      "used": true
    },
    "keyword_index": {
      "name": "sqlite-fts5",
      "used": true
    },
    "vector_store": {
      "name": "chroma",
      "used": true
    },
    "graph_store": {
      "name": null,
      "used": false
    },
    "graph_projection": {
      "name": null,
      "used": false
    }
  },
  "retrieval_policy_version": "retrieval-policy-v1",
  "budget": {
    "max_tokens": 8000,
    "max_evidence_items": 24,
    "max_excerpt_tokens": 320,
    "used_tokens": 0,
    "omitted_items": 0
  },
  "store_revisions": [
    {
      "kind": "metadata",
      "revision": "metadata-revision-id",
      "vault_id": "main",
      "scope_key": "main:wiki,docs:local"
    },
    {
      "kind": "keyword",
      "revision": "keyword-revision-id",
      "vault_id": "main",
      "scope_key": "main:wiki,docs:local"
    },
    {
      "kind": "vector",
      "revision": "vector-revision-id",
      "vault_id": "main",
      "scope_key": "main:wiki,docs:local"
    }
  ],
  "generated_at": "2026-06-04T00:00:00+09:00",
  "current_state": [],
  "relevant_pages": [],
  "relevant_sources": [],
  "decisions": [],
  "constraints": [],
  "open_questions": [],
  "warnings": [],
  "evidence": []
}
```

## 8. 독립 모듈 5개

보관본 [SPEC v5.0](archive/SPEC-v5.0.md) §10~12를 그대로 옮긴다. 이미 구현된 패키지(`graph_search`, `graph_document`, `text_embeddings`, `vector_search`, `vector_index`)의 계약이기 때문이다. 아래 본문의 §10은 8.1절을 가리키고, §1.7·§7.1·§9.3은 보관본 SPEC v5.0의 절을 가리킨다.

### 8.1 Independent Graph Search Design Proposal

**Status:** Proposed supplementary design. Implementation and default-engine
replacement are not approved or completed by this documentation addition.

독립적으로 설치·호출 가능한 `graph_search`의 상세 계약과 검증 계획은
[GS-20261003: 독립 graph_search 상세 설계](design/specs/2026-10-03-graph-search-ko.md)에,
기존 시스템과 연결하는 계층은
[GS-20261003-INTEGRATION: 연동 설계](design/specs/2026-10-03-graph-search-integration-ko.md)에
정의한다. 연동 설계는 같은 부모 계약의 보조 문서다.

코어는 노드·간선 ID와 끝점만 받고, 대표 최단 경로 탐색과 제한된 단순 경로
열거를 별도 API로 제공한다. Vault ID, 신뢰도, 관계 종류, 근거, 리비전,
저장소와 CLI/MCP/HTTP는 코어의 계약에 포함하지 않는다.

연동 어댑터는 기존 `GraphProjection` 입출력을 유지하며 필터·간선 상한,
ID 대응, 복수 경로 점수·순위, 빌드 ID, 근거 연결을 보존한다.
대표 경로만으로 기존 복수 경로 결과를 대체하지 않는다. 순환을 피해 탐색이
종료되는 동작은 §7.1과 §9.3의 전역 SCC 검증을 대체하지 않는다.

설계 문서의 완성, 모듈 구현, 실제 연동, production-ready 검증은 각각
구분한다. 모듈의 FA-01–FA-11과 연동의 IT-01–IT-12, 독립 wheel 설치,
공개 조회 경로의 회귀, 운영 부하·메모리 측정 증거가 해당 완료 판단의 기준이다.
미확정 운영 상한과 v1 호환성 보정은 새 설계의 Open Decisions에 유지한다.
기존 Phase 3C 계약과 본 문서의 승인된 제품 경계는 이번 추가로 변경하지 않는다.


### 8.2 Independent Graph Document Design Proposal

독립 문서 그래프 패키지의 상세 제안은
[DG-20261004: graph_document](design/specs/2026-10-04-graph-document-ko.md)에,
기존 Vault 기능 재사용과 호환성 경계는
[DG-20261004-INTEGRATION](design/specs/2026-10-04-graph-document-integration-ko.md)에 정의한다.
연동 문서는 같은 부모 계약의 보조 설계다.

패키지는 일반 문서의 구조에서 항목·관계·근거를 추출하고, 문서별 기여와 SQLite 파생 상태를 관리한다.
경로 계산은 §10의 graph_search를 사용한다. 기본 추출은 규칙 기반이며 의미 추출은 외부 스키마 제한
추출기로 연결하는 대안과 검증 gate를 부모 §15에 기록한다.

새 설계는 기존 graph_search 계약, Vault ID·근거·scope·순위, sqlite-graph-v2와 기본 factory를 변경하지 않는다.
독립 package 구현, 기존 공개 경로의 전환, 운영 준비 완료는 DG-FA·DG-IT 실행 증거와 별도 gate로 판정한다.
이 추가는 설계 문서 제출이며 데이터 이전이나 모듈 구현을 완료했다는 의미가 아니다.


패키지별 독립 사용을 먼저 검증하고 연동을 단계적으로 구현하는 순서는
[graph_search·graph_document 구현 순서](design/plans/2026-10-04-graph-modules-implementation-order-ko.md)에 정리한다.
이는 실행 순서 제안이며 기존 네 설계 계약의 범위·승인 상태를 변경하지 않는다.

### 8.3 Independent Embedding And Vector Modules

사용자가 승인한 2차 리팩터링의 책임·입출력·삭제 범위·실패 처리·호환성 계약은
[임베딩·벡터 모듈 계약](design/specs/2026-10-06-vector-modules-ko.md)에 정의한다.
`text_embeddings`, `vector_search`, `vector_index`는 Vault와 그래프 모듈에 의존하지 않는다.
Vault 전용 정책과 기존 저장 형식의 변환은 `vault_graph.indexing.vector_index_adapter` 등 Vault Graph의 책임별 어댑터에서 수행한다([ARCHITECTURE.md](ARCHITECTURE.md) §2).
이 분리는 §1.7의 포트·어댑터 경계를 따르며 불변성 엔진의 기능이나 정책을 변경하지 않는다.

## 9. 단계

상세 계약, 실패 동작, 수용 기준은 [spec 2026-10-29-local-graph-memory-layer](specs/2026-10-29-local-graph-memory-layer/spec.md)에 있다. 이 절은 요약이다.

### 9.1 1차 작업

| 단계 | 내용 | 선행 |
|---|---|---|
| 1차-0 | 제품 계약 문서 정리(이 SPEC, v5.0 보관, 경계 문서 원칙 통일) | 없음 |
| 선행 | 모듈화 보완1(기능 간 가져오기 방향 테스트)·보완5(M12↔M17 binding 순환)는 1차-2 전에, 보완6은 1차-3 전에. 나머지 보완은 1차와 나란히 또는 1차 뒤 | 1차-0 |
| 1차-1 | 측정1 기준선(변경 전) | 1차-0 |
| 1차-2 | `vault-map.json` 읽기(결정9) | 보완1, 보완5 |
| 1차-3 | 세션 시작 회상 `vg hook session-start`(결정10) | 1차-2 |
| 1차-4 | MCP `remember`(결정8)와 README 수정 | 1차-2 |
| 1차-5 | 한국어 조사 처리(색인 때 조사를 뗀 별도 열) | 1차-1 |
| 1차-6 | 측정1 재측정, 결과 기록 | 1차-5 |

### 9.2 n차 로드맵 (1차 이후)

각 항목은 시작 전에 별도 spec으로 승격한다. 1차에서는 구현하지 않는다.

| 코드 | 내용 | 선행 |
|---|---|---|
| n차-1 | 대체된 claim을 기본 결과와 회상에서 빼고 최근 기억에 가중치를 준다. Vault `supersede-claim` 결과를 읽는다 | 의존4, 의존5 |
| n차-2 | 기억 frontmatter(`peer`, `kind`, `observed_at`, claim 상태) 해석과 프로필 조회 `get_profile`. 모르는 스키마 버전은 경고한다 | 의존5 |
| n차-3 | 코드와 기억을 질의 하나로 찾는다. MCP `explain_symbol`, 코드 청크 색인 여부 결정 | 1차 완료 |
| n차-4 | 임베딩 모델 교체를 측정1과 같은 방법으로 비교한 뒤 정한다 | 측정1 |
| n차-5 | 폴링 watch를 파일 변경 이벤트(`watchfiles`) 기반으로 바꾼다 | 없음 |
| n차-6 | `raw/sessions/<agent>/`를 수집 대상별(Claude Code, Codex, ChatGPT)로 역할 분류하고 evidence 모드에서 찾는다 | 의존2 |
| n차-7 | `project-bindings.json`과 자체 Vault 등록을 `vault-map.json` 읽기로 대체하고 정리한다 | 1차-2 |
| n차-8 | MCP `recall` 도구와 질문 기반 회상 | 1차-3 |
| n차-9 | 측정1 조건B를 실제 수집기 결과로 다시 측정한다 | 의존2 |
| n차-10 | `vg memory review`(읽기 전용): 사용 기록으로 고정·정리·모순 후보를 보인다 | 1차-3, 사용 기록 2주 운영 |
| n차-11 | 첫 사용자 프롬프트로 검색해 본문 상위 몇 개를 넣는 회상(UserPromptSubmit 훅) | 측정1, 의존1 확장 |
| n차-12 | `raw/sessions/` 대화 기록에서 `m:` ID 언급을 세어 사용 집계를 보강한다 | 의존2 |

### 9.3 Vault·vault-builder 쪽 의존성 (미구현 표시)

vault-graph는 아래 항목을 만들지 않는다. 소유한 쪽이 구현한다.

| 코드 | 의존 | 소유 | 상태 | vault-graph에 미치는 영향 |
|---|---|---|---|---|
| 의존1 | SessionStart 훅 스크립트 분기. vg가 있으면 `vg hook session-start`에 훅 입력을 넘기고, 종료 코드 0이면 표준 출력을 그대로 쓴다. 0이 아니면 `recall.sh`를 쓴다 | vault-builder(사용자 범위 훅) | 미구현 | 1차-3 결과가 실제 세션에 들어가려면 필요하다 |
| 의존2 | 세션 수집기와 `raw/sessions/`(결정5) | Vault 도구, vault-builder 템플릿 배포 | 미구현 | 측정1 조건B, 가치1, n차-6·9·12 |
| 의존3 | Vault `AGENTS.md` 규칙1 예외: 수집기가 `raw/sessions/`에 새 파일을 추가하는 것만 허용(결정11) | Vault, vault-builder | 미구현. 요청1로 전달 | 의존2의 전제 |
| 의존4 | 정리 스킬, 자동 기억 확정 규칙(결정6) | Vault 도구 | 미구현 | n차-1 |
| 의존5 | 기억 frontmatter 스키마 `vault-memory/v1`. `pin: true`와 `memory_kind: rule\|correction\|decision\|preference`를 포함해 달라고 요청한다. `supersedes`·`superseded_by`는 이미 있다 | vault-builder가 Vault 도구에 담아 배포 | 미구현 | 회상 구획A(필드 전까지 비어 있음), 구획B 유형, n차-1, n차-2 |
| 의존6 | publish-draft 명령과 draft 형식의 버전 표시 | Vault 도구 | 명령은 있음, 버전 표시는 미구현 | 1차-4 remember |
| 의존7 | `vault-map.json` version 2 형식 유지 | vault-builder | 구현됨 | 1차-2 |

vault-builder 요청 문서: vault-builder 저장소 `docs/superpowers/specs/2026-10-29-vault-graph-requests-ko.md`(커밋 전). 요청1=의존3, 요청2=의존2, 요청3=의존1, 요청4=의존6, 요청5=의존7, 요청6=의존5, 요청7=의존4.

## 10. 보관 문서

- [SPEC v1.2](archive/SPEC-v1.2.md): Vault 위 읽기 전용 검색 계층 시기의 계약. 현재 코드 대부분이 이 시기에 만들어졌다.
- [SPEC v5.0](archive/SPEC-v5.0.md): Software Invariant Engine. 2026-10-29에 보관했다. VS-1~6은 구현하지 않는다.

보관 문서는 고치지 않는다. 과거 설계 문서가 `docs/SPEC.md`의 절을 가리키면 해당 시기의 보관본에서 찾는다.
