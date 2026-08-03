# Vault Graph 다음 단계 방향 보고서

작성일: 2026-07-30

상태: 승인된 제품 방향

선행 조건:
[`2026-07-30-vault-projection-duplication-direction-report-ko.md`](2026-07-30-vault-projection-duplication-direction-report-ko.md)의
**Round 0 — Authority & Projection Hygiene** 완료

## 1. 결론

Vault Graph의 다음 목표는 Vault 전용 지식 검색을 넘어, **지속적인 프로젝트
지식과 현재 코드를 함께 탐색하는 읽기 전용 프로젝트 증거 계층**이 되는
것이다.

그러나 현재 Vault의 raw/wiki/index/report 역할과 Vault Graph의
metadata/keyword/vector/graph projection 사이의 물리적·논리적 중복을 먼저
해결해야 한다. Round 0 완료 게이트를 통과하기 전에는 아래 코드 인덱스와
하네스 라운드를 구현하지 않는다.

이 확장은 원본의 권한을 합치지 않는다.

- Vault는 결정, 설계, 조사, 운영 기록 등 지속적인 프로젝트 지식의 원본이다.
- 등록된 소스 저장소는 현재 실행 가능한 코드의 원본이다.
- Vault Graph는 두 원본을 읽고 파생 인덱스를 만들지만 어느 쪽도 수정하지
  않는다.

Round 0 이후 권장하는 2개 확장 라운드는 다음과 같다.

1. **Round 1 — Project Code Projection:** 결정적 코드 구조 인덱스와 최신성
   기반을 만든다.
2. **Round 2 — Harness-Native Project Context:** 코드와 Vault 지식을 한 번의
   고수준 MCP 호출로 조합하여 코딩 에이전트의 프롬프트와 탐색 호출을 줄인다.

## 2. 조사 범위와 기준

다음 자료와 현재 구현을 비교했다.

- Vault Graph의 `docs/SPEC.md`, `docs/DESIGN.md`, `docs/FEATURES.md`,
  `docs/CONVENTIONS.md`
- 현재 Markdown 전용 `VaultLoader`
- 현재 10개 MCP 도구, 7개 MCP 프롬프트, Codex MCP 등록 흐름
- [CodeGraph 공식 저장소](https://github.com/colbymchenry/codegraph)
- [Graphify 공식 개념 문서](https://graphify.com/concepts)
- [Graphify 공식 시작 문서](https://graphify.com/docs)

비교 기준은 기능 수가 아니라 다음 제품 문제를 얼마나 해결하는지다.

- 코드 구조를 문자열 검색보다 정확하게 탐색할 수 있는가
- 변경된 코드와 인덱스의 최신성 차이를 숨기지 않는가
- 에이전트가 사용자의 긴 도구 호출 지시 없이 올바른 진입점을 선택하는가
- 결과의 출처와 추론 여부를 확인할 수 있는가
- Vault Graph의 읽기 전용, 재구축 가능, 로컬 우선 원칙을 보존하는가

## 3. 현재 Vault Graph의 간극

### 3.1 코드 인덱스 부재

현재 `VaultLoader`는 등록된 Vault 범위 아래의 `*.md`만 읽는다. 따라서
함수, 클래스, 메서드, import, 호출, 상속, 구현, 테스트 관계를 구조적으로
표현할 수 없다.

기존 그래프는 Vault 문서에서 추출한 지식 그래프다. 코드 그래프에 필요한
심볼 정체성, 파일과 라인 범위, 결정적 구조 관계, 작업 트리 최신성은 별도
계약이 필요하다.

### 3.2 MCP 기능은 많지만 기본 경로가 깊다

현재 MCP는 다음 10개 도구를 제공한다.

- `ask_vault`
- `search_vault`
- `build_context_pack`
- `find_related`
- `get_decision_trace`
- `check_index_status`
- `explain_result`
- `summarize_project_memory`
- `get_open_questions`
- `get_recent_changes`

기능은 충분하지만 코딩 에이전트가 작업마다 어떤 도구를 어떤 순서로 호출할지
판단해야 한다. 7개 MCP 프롬프트가 이 순서를 안내하지만, 사용자가 프롬프트를
직접 선택하거나 에이전트가 여러 도구를 조합해야 하는 부담은 남아 있다.

현재 MCP 초기화 지침도 읽기 전용과 지속 지식 경계만 설명한다. “코드 작업은
먼저 어떤 도구를 사용해야 하는가”, “언제 결과를 신뢰하고 언제 원본 파일을
다시 읽어야 하는가”까지 안내하지 않는다.

### 3.3 Vault 중심 식별자가 코드까지 확장되기 어렵다

기존 검색과 그래프 레코드는 `vault_id`, 문서, 청크, Vault 경로를 중심으로
설계되었다. 코드 파일과 심볼을 Vault 문서로 가장하면 다음 문제가 생긴다.

- 코드 저장소를 Vault의 하위 개념으로 잘못 표현한다.
- 심볼 정체성과 파일·라인 증거가 문서 청크 계약에 묻힌다.
- 코드 변경 주기와 Vault 문서 변경 주기를 구분할 수 없다.
- 향후 언어별 파서가 Markdown ingestion 내부로 누출된다.

따라서 코드 인덱스는 기존 `VaultLoader`의 확장자가 아니라 별도의 깊은 모듈로
설계해야 한다.

## 4. 비교 제품에서 배울 점

### 4.1 CodeGraph

CodeGraph의 핵심은 단순히 AST를 만든다는 점이 아니다.

- tree-sitter 기반으로 심볼과 호출 관계를 결정적으로 추출한다.
- 로컬 SQLite와 FTS를 사용한다.
- MCP 연결 시 변경 파일을 다시 확인하고 파일 감시로 증분 동기화한다.
- 짧은 지연 구간에 오래된 파일이 결과에 포함되면 원본을 직접 읽으라는
  경고를 제공한다.
- 기본 MCP 표면을 `codegraph_explore` 하나로 줄인다.
- 한 호출에서 관련 소스, 호출 경로, 영향 범위를 함께 반환한다.
- MCP 초기화 응답과 에이전트 지침 파일을 통해 사용법을 하네스에 전달한다.

Vault Graph가 가져와야 할 핵심은 **하나의 강한 작업 진입점**, **최신성의
가시화**, **하네스가 스스로 선택할 수 있는 사용 지침**이다.

가져오지 말아야 할 부분은 코드만을 중심으로 제품 정체성을 바꾸거나, 기존
증거 기반 지식 기능을 코드 탐색의 부속 기능으로 축소하는 것이다.

### 4.2 Graphify

Graphify는 코드와 이질적인 자료를 하나의 그래프로 연결하는 방향에서 참고할
가치가 크다.

- 코드는 로컬 AST로 결정적으로 추출한다.
- 문서, PDF, 이미지 등은 별도의 의미 추출 경로를 사용한다.
- 관계를 `EXTRACTED`, `INFERRED`, `AMBIGUOUS`로 구분한다.
- 코드와 문서 사이의 예상 밖 연결과 커뮤니티를 찾는다.
- CLI, HTML, JSON, MCP 등 여러 소비 표면을 제공한다.

Vault Graph가 가져와야 할 핵심은 **자료 유형별 추출 경로 분리**, **관계
출처의 명시**, **코드와 지식 사이의 교차 연결**이다.

초기 라운드에서 가져오지 말아야 할 부분은 30개 이상의 언어, 미디어 입력,
시각화, PR 대시보드를 동시에 구현하는 것이다. 이는 코드 인덱스와 하네스
통합이라는 현재 문제를 흐린다.

## 5. 검토한 세 가지 방향

### 방향 A — 통합 프로젝트 증거 계층

Vault와 저장소를 서로 다른 원본 권한으로 등록하고, Vault Graph가 두 파생
프로젝션을 조합한다.

장점:

- 코드와 결정의 최신 원본을 각각 유지한다.
- 기존 Vault 기능을 보존하면서 코드 탐색을 추가할 수 있다.
- 코드 변경과 문서 변경의 최신성을 독립적으로 설명할 수 있다.
- Round 2에서 한 작업 응답으로 자연스럽게 합성할 수 있다.

단점:

- `vault_id` 중심 모델 위에 저장소 정체성과 프로젝트 범위를 추가해야 한다.
- 코드와 지식의 연결 규칙을 새로 정의해야 한다.

### 방향 B — Vault에 코드를 먼저 수집

코드 또는 코드 요약을 Vault에 넣은 뒤 기존 파이프라인으로 인덱싱한다.

장점:

- 현재 “Vault 위의 계층”이라는 정체성을 거의 바꾸지 않는다.
- 기존 검색과 저장소 계약을 더 많이 재사용할 수 있다.

단점:

- 현재 코드와 Vault 복사본이 쉽게 달라진다.
- 심볼, 호출, 상속, 파일·라인 구조가 문서 청크로 손실된다.
- Vault에 실행 코드의 두 번째 원본을 만들 위험이 있다.

### 방향 C — CodeGraph 또는 Graphify 연합

코드는 외부 도구가 인덱싱하고 Vault Graph는 MCP 또는 어댑터로 결과만
조합한다.

장점:

- 가장 빠르게 광범위한 언어 지원을 얻을 수 있다.
- 검증된 코드 파싱 기능을 재사용한다.

단점:

- 설치, 버전, 최신성, 오류, 증거 계약이 두 제품으로 분리된다.
- Vault Graph의 로컬 우선 기본 경로에 필수 외부 런타임이 생긴다.
- 한 번의 일관된 결과 설명과 재구축 계약을 보장하기 어렵다.

### 선택

사용자는 2026-07-30에 **방향 A — 통합 프로젝트 증거 계층**을 승인했다.
외부 제품은 설계 참고와 선택적 어댑터 후보로 남기고, 핵심 계약은 Vault
Graph가 소유한다.

## 6. 원본 권한과 중복 모델

### 6.1 중복은 세 종류로 구분한다

| 종류 | 정책 |
| --- | --- |
| 원본 권한 중복 | 금지한다. Vault와 저장소의 역할을 섞지 않는다. |
| 파생 저장 중복 | 허용한다. 텍스트, 임베딩, AST, 그래프는 삭제 후 재구축 가능해야 한다. |
| 의미 중첩 | 보존하고 연결한다. 같은 개념을 설명해도 증거 노드를 합치지 않는다. |

예를 들어 Vault에 `PaymentService` 설계 문서가 있고 저장소에
`PaymentService` 클래스가 있더라도 하나의 레코드로 병합하지 않는다.

```text
VaultDecision: "결제 승인 책임은 백엔드에 둔다"
    |
    | DOCUMENTS / CONSTRAINS
    v
CodeSymbol: PaymentService.confirm()
```

Vault 노드는 “왜 그렇게 설계했는가”의 증거이고, 코드 심볼은 “현재 무엇이
구현되어 있는가”의 증거다.

### 6.2 Vault 안의 코드 예시

Vault 문서의 코드 블록은 기본적으로 문서 증거다. 해당 코드가 현재
실행된다고 간주하거나 저장소 심볼로 승격하지 않는다. 저장소의 실제 심볼과
연결할 수 있지만, 동일성은 경로·심볼 해석·출처가 확인된 경우에만
`EXTRACTED` 또는 `INFERRED` 상태로 표시한다.

### 6.3 물리적 중복 제거와 논리적 출처

동일한 내용 해시를 가진 본문은 저장 공간 최적화를 위해 물리적으로 한 번만
보관할 수 있다. 그러나 다음 논리적 증거 정체성은 절대로 제거하지 않는다.

- `source_kind`: `vault` 또는 `repository`
- `source_id`: `vault_id` 또는 `repository_id`
- 원본 상대 경로
- 코드 심볼과 파일·라인 범위
- 원본 revision과 인덱스 revision
- parser 또는 extractor spec version

동일성 비교는 전역 본문 해시 하나가 아니라 최소한
`(source_kind, source_id, path, content_hash, extractor_spec_version)`를
기준으로 한다.

### 6.4 중복 등록 방지

- 정규화한 실제 경로가 같은 저장소를 두 번 등록하지 않는다.
- 부모·자식 저장소 루트를 동시에 등록할 때 중첩 범위를 명시적으로 거부하거나
  사용자가 하나를 선택하게 한다.
- vendored 코드나 생성물은 기본 제외한다.
- 서로 다른 저장소에 같은 파일이 있어도 저장소 namespace가 다르면 별도
  증거로 유지한다.

## 7. Round 1 — Project Code Projection

### 목표

등록된 소스 저장소를 읽기 전용으로 분석하여 코드 구조를 결정적이고
재구축 가능한 프로젝트 증거로 제공한다.

### 핵심 방향

- 기존 Vault ingestion을 일반화하지 않고 별도의 코드 프로젝션 모듈을 둔다.
- 파서 구현은 안정된 내부 인터페이스 뒤에 숨긴다.
- 첫 지원 순서는 Vault Graph 자체 검증을 위한 Python, 주요 사용자
  프로젝트를 위한 Dart로 한다.
- 언어 수보다 심볼 정체성, 관계 정확도, 파일·라인 근거, 증분 최신성을 먼저
  검증한다.

### 권장 깊은 모듈

```text
RepositoryCatalog
    |
    v
CodeProjectionService
    |
    +--> CodeParserAdapter
    +--> SymbolResolver
    +--> CodeProjectionStore
    +--> CodeFreshnessService
```

- `RepositoryCatalog`: 등록된 저장소, namespace, 루트, 제외 규칙을 소유한다.
- `CodeProjectionService`: 전체·증분 프로젝션의 단일 애플리케이션 경계다.
- `CodeParserAdapter`: 언어별 파서와 AST 세부사항을 숨긴다.
- `SymbolResolver`: import, 호출, 상속, 구현 관계를 파일 간에 해석한다.
- `CodeProjectionStore`: 코드 심볼과 구조 관계를 저장한다.
- `CodeFreshnessService`: 작업 트리와 인덱스 revision 차이를 설명한다.

초기에는 기존 Vault `GraphStore` 스키마를 억지로 일반화하지 않는다. 코드
프로젝션의 정체성과 최신성 계약이 안정된 뒤 Round 2의 조합 계층에서 함께
조회한다.

### 최소 코드 모델

노드:

- Repository
- SourceFile
- Function
- Method
- Class
- Interface
- Test

관계:

- `CONTAINS`
- `DEFINES`
- `IMPORTS`
- `CALLS`
- `EXTENDS`
- `IMPLEMENTS`
- `TESTS`

모든 심볼과 관계는 저장소 ID, 파일 경로, 라인 범위, 추출 방식, parser spec
version을 포함한다. 결정적으로 확인할 수 없는 동적 호출은 확정 관계로
만들지 않고 `AMBIGUOUS` 또는 경고로 남긴다.

### 범위 밖

- 코드 수정
- 자동 리팩터링
- LLM 기반 호출 관계 생성
- 30개 이상 언어의 동시 지원
- 코드 그래프 시각화
- PR 대시보드
- Vault와 코드 심볼의 자동 진실 병합

### 완료 기준

- 저장소 등록과 중복·중첩 루트 검증이 가능하다.
- Python과 Dart fixture에서 핵심 노드와 관계가 결정적으로 재현된다.
- 전체 재구축과 변경·삭제 파일 증분 반영이 같은 기능 결과를 만든다.
- 모든 결과가 저장소, 파일, 라인, revision으로 추적된다.
- 저장소에 쓰기가 발생하지 않는 경계 테스트가 통과한다.
- 오래된 코드 결과는 최신 결과처럼 조용히 반환되지 않는다.

## 8. Round 2 — Harness-Native Project Context

### 목표

사용자가 도구 호출 순서를 긴 프롬프트로 설명하지 않아도 코딩 에이전트가
현재 코드와 지속 지식을 함께 가져오게 한다.

### 하나의 기본 진입점

새 애플리케이션 경계와 MCP 도구를 제안한다.

```text
explore_project(
  task,
  project_path=None,
  max_tokens=None
)
```

이 도구는 프로토콜 내부에서 검색을 다시 구현하지 않는다.
`ProjectContextService`가 기존 Vault 서비스와 Round 1 코드 서비스를
조합하고 MCP는 이를 직렬화하는 얇은 어댑터로 남는다.

한 번의 응답은 다음을 포함한다.

- 작업과 직접 관련된 현재 코드
- 파일별 줄 번호가 포함된 심볼 본문
- 호출 또는 의존 경로
- 변경 영향 범위와 관련 테스트
- 관련 Vault 결정, 제약, 설계 문서
- 코드와 지식 사이의 명시적 또는 추론된 연결
- Vault와 코드 인덱스의 revision·최신성
- 누락, 충돌, 오래됨, 모호함 경고
- 각 항목의 출처와 설명

### 하네스 통합

- MCP 초기화 지침에서 코딩 작업의 기본 도구로 `explore_project`를 안내한다.
- 현재 프로젝트 경로에서 등록된 저장소와 연결된 Vault 범위를 자동
  선택한다.
- MCP 초기화 지침을 받지 못하는 서브에이전트나 CLI 하네스를 위해
  `AGENTS.md`, `CLAUDE.md` 등 지원 대상 지침 파일에 짧고 marker-fenced한
  사용 지침을 설치한다.
- 설치는 명시적 옵션에서만 파일을 수정하고, 기존 설정을 백업하며, 제거
  가능해야 한다.
- 기존 세부 MCP 도구는 호환성을 위해 유지하되 에이전트 기본 경로는 하나로
  만든다.

### 최신성 계약

CodeGraph의 장점을 참고하되 다음 Vault Graph 방식으로 제한한다.

1. MCP 연결 시 등록 저장소와 코드 인덱스 revision을 빠르게 비교한다.
2. 파일 감시가 켜져 있으면 변경을 debounce하여 증분 반영한다.
3. 동기화 대기 중인 파일이 결과에 포함되면 원본을 직접 읽으라는 경고를
   응답 상단에 표시한다.
4. 저장소가 등록되지 않았거나 코드 인덱스가 없으면 기존 파일 도구를
   사용하라는 복구 지침을 반환한다.
5. 최신성 불명 상태를 `fresh`로 추정하지 않는다.

### 프롬프트 절감 검증

“기능이 편해졌다”는 인상만으로 완료하지 않는다. 대표 작업 fixture를 만들고
기존 MCP 흐름과 비교한다.

- 구조 설명
- 버그 수정 범위 조사
- 변경 영향 분석
- 설계 결정과 구현 일치 검토
- 관련 테스트 선택

각 작업에서 다음을 기록한다.

- MCP 호출 횟수
- 에이전트가 읽은 응답 토큰
- fallback grep/read 호출 횟수
- 올바른 관련 파일·심볼·결정의 recall
- 오래된 결과를 최신으로 오인한 횟수

목표값은 baseline 측정 후 확정한다. 제품 완료 기준에는 최소한 호출 수와
프롬프트 지시량의 명확한 감소, 근거 정확도의 비열화, 최신성 경고 누락 0건이
포함되어야 한다.

### 범위 밖

- 에이전트의 코드 작성 또는 승인 자동화
- Vault에 결과 자동 게시
- 사용자 동의 없는 하네스 설정 변경
- 외부 SaaS 필수화
- 기존 세부 MCP 도구의 즉시 제거

### 완료 기준

- 하나의 `explore_project` 호출로 코드와 Vault 증거가 함께 반환된다.
- 프로젝트와 Vault 범위가 정상적인 하네스 실행에서 자동 해석된다.
- MCP 초기화 지침만으로 주 에이전트가 기본 도구를 올바르게 선택한다.
- 비-MCP 서브에이전트용 지침을 명시적으로 설치·제거할 수 있다.
- stale·missing·ambiguous 상태가 구조화된 경고로 전달된다.
- 대표 작업 benchmark가 기존 흐름보다 적은 호출과 프롬프트로 동등 이상의
  근거 품질을 보인다.

## 9. 권장 아키텍처

```text
Vault                              Registered Repository
durable project knowledge          current executable code
  |                                   |
  v                                   v
Vault Projection                  Code Projection
existing services                 deterministic parser/resolver
  |                                   |
  +----------------+------------------+
                   |
                   v
          ProjectContextService
        evidence selection + budget
        paths + impact + provenance
                   |
                   v
             CLI / MCP adapter
                   |
                   v
             Coding Harness
```

이 구조에서 가장 중요한 정보 은닉은 다음과 같다.

- Vault 서비스는 언어별 AST를 알지 않는다.
- 코드 프로젝션은 Vault frontmatter나 출판 워크플로를 알지 않는다.
- MCP는 검색과 그래프 조합을 소유하지 않는다.
- `ProjectContextService`는 두 서비스의 내부 저장소가 아니라 안정된
  애플리케이션 인터페이스에 의존한다.

## 10. 정체성 변경

기존 정체성:

> Vault 위의 읽기 전용, 재구축 가능한 지식 접근 및 추론 계층

승인된 정체성:

> Vault Graph는 지속적인 프로젝트 지식과 현재 코드를 연결하는 로컬 우선,
> 읽기 전용, 재구축 가능한 프로젝트 증거 및 추론 계층이다. Vault는 지속
> 지식의 원본이며, 등록된 소스 저장소는 현재 코드의 원본이다.

이 변경은 “Vault가 지식의 원본”이라는 원칙을 약화하지 않는다. 대신 코드의
권한을 Vault에 잘못 부여하지 않고 별도로 명시한다.

## 11. 주요 위험과 완화

| 위험 | 완화 |
| --- | --- |
| 기존 Vault 모델을 성급하게 일반화 | Round 1 코드 프로젝션을 별도 깊은 모듈로 시작 |
| 같은 개념의 문서·코드 병합으로 출처 손실 | 증거 노드를 분리하고 관계로 연결 |
| 동적 언어 호출 관계의 거짓 확정 | 추출 상태와 모호성 경고 보존 |
| 작업 트리와 인덱스 차이 | 연결 시 확인, watcher, 결과별 stale 경고 |
| MCP 도구 수 증가 | `explore_project`를 기본 진입점으로 사용 |
| 외부 제품 복제로 정체성 상실 | 증거 기반 Vault 지식과 코드의 결합에 집중 |
| 너무 많은 언어를 동시에 지원 | Python과 Dart에서 계약을 먼저 검증 |
| 저장소 또는 하네스에 숨은 쓰기 | 명시적 설치 옵션과 읽기 전용 경계 테스트 |

## 12. 다음 산출물 순서

이 보고서는 제품 방향을 확정한다. 구현 전에는 두 라운드를 각각 별도의
설계와 구현 계획으로 분리해야 한다.

1. Round 0 authority, role, single-body projection 설계
2. Round 0 migration 계획과 중복 baseline 측정
3. Round 0 완료 게이트 검증
4. Round 1 코드 프로젝션 설계
5. Round 1 구현 계획과 benchmark fixture
6. Round 1 완료 검증
7. Round 2 프로젝트 컨텍스트·하네스 설계
8. Round 2 구현 계획과 기존 MCP 호환성 검토
9. Round 2 프롬프트·도구 호출 benchmark

각 설계는 보안·읽기 전용, 성능·확장성, 테스트 가능성, 유지보수성·깊은 모듈,
에이전트 사용성 관점에서 검토해야 한다.
