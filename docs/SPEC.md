# Vault Graph Specification: The Software Invariant Engine

**Version:** 5.1-premerge-preview
**Status:** Active Product Contract
**Author:** Jun Hyoung Lee
**Date:** 2026-09-06
**Predecessor Baseline:** [`docs/archive/SPEC-v1.2.md`](archive/SPEC-v1.2.md) (v1.2 Archived Product Contract)
**Change Note (v5.1):** Q1-Q6 결정(D1-D6) 반영. `virtual_stub` 명칭을 `premerge_contract_preview`로 교체. 서브시스템 A 읽기 전용 경계, 공유 식별자, 소비자 가져오기, 페이로드 불일치 거부, 캐시 지문, 래칫 예외 경로를 확정.

---

## 목차 (Table of Contents)

1. [Intent, Vision, and Core Identity](#1-intent-vision-and-core-identity)
   - 1.1 The Pivot and Core Identity (정체성 전환과 핵심 정체성)
   - 1.2 Direction & Vision (소프트웨어 아키텍처 불변성 엔진의 방향성)
   - 1.3 Intent (설계 의도: 자율 에이전트 엔트로피와 50년 불변 원칙)
   - 1.4 Goals (핵심 목표: 4대 불변 목표 및 통합 비전)
   - 1.5 Three Authority Domains (3대 권한 영역 모델)
   - 1.6 Mechanism vs. Policy Doctrine (기작과 정책의 분리 원칙)
   - 1.7 진화적 아키텍처 및 3단계 어댑터 마이그레이션
   - 1.8 영구 거버넌스 및 기준 문서의 지속성
2. [Four Subsystem Boundaries (4대 서브시스템 경계 및 무상태성 정립)](#2-four-subsystem-boundaries)
3. [Three-Tier Invariant Hierarchy & Core Values](#3-three-tier-invariant-hierarchy--core-values)
   - 3.1 3단계 불변식 계층 (Tier 0, Tier 1, Tier 2)
   - 3.2 4대 핵심 불변 가치 (The 4 Non-Negotiable Invariant Values)
4. [Repository Topology & Governance Ledgers](#4-repository-topology--governance-ledgers)
   - 4.1 저장소 구조 및 3대 실행 가능 실체 (The Executable Trinity)
   - 4.2 아키텍처 면제 장부 (`.vault-graph/exemptions.json`) 및 비가역 래칫
5. [SQLite WAL Coordination Store Architecture (서브시스템 B)](#5-sqlite-wal-coordination-store-architecture)
   - 5.1 상태 수명주기 분리 및 저장소별 해시 격리 (`<repo_hash>`)
   - 5.2 Connection PRAGMA 명세
   - 5.3 4대 테이블 표준 DDL 스키마
   - 5.4 동시성 프로토콜, 지수 백오프 재시도 및 `client_request_id` 멱등성
6. [Cross-Worktree Orchestration Protocol](#6-cross-worktree-orchestration-protocol)
   - 6.1 Concurrency Model: Physical Isolation vs. Logical Concurrency
   - 6.2 오케스트레이션 핵심 5대 기작
   - 6.3 프리머지 계약 미리보기 수명주기 (.pyi) 및 8줄 무결성 헤더
   - 6.4 위상 대기열, Wait-for Graph 및 교착 상태 방지
   - 6.5 2단계 프리머지 사전 중첩 검증 (Two-Stage Pre-merge Pre-check)
   - 6.6 데이터 계약 및 Python 데이터클래스 정의
7. [Vertical Slice Specifications (VS-1 ~ VS-6)](#7-vertical-slice-specifications)
   - 7.1 [VS-1] Topological Invariant Verification Slice
     - Git 트리 해시 내용 주소 지정형 캐시 모델
     - 전역 $O(V+E)$ Tarjan SCC 분석 및 2-hop 결함 반례 증명
     - 증분 도달 가능성 경로 분석 및 `if TYPE_CHECKING:` 분기 식별
     - 깊은 모듈 지수 ($DMI$) 정식 수식 및 3대 특수 모듈 면제
     - 다계층 지연시간 예산 SLA (Fast / Warm / Slow Path)
   - 7.2 [VS-2] Cross-Worktree Coordination & Pre-merge Contract Preview Slice
   - 7.3 [VS-3] Executable Conventions & Structural Linter Slice
     - 이원화된 구문 오류 분류 체계 (Level 1 Draft vs. Level 2 Fatal)
     - 정적 코딩 규약 정의
   - 7.4 [VS-4] Deterministic Test Contract & Verification Guard Slice
     - 최소 테스트 계약 도출 및 스테이징 델타($\Delta F$) 해시 불변 검증
   - 7.5 [VS-5] Constitutional Discovery & Synthesis Slice (Greenfield & Brownfield)
   - 7.6 [VS-6] Gradual Evolutionary Governance & Exemption Ratchet Slice
8. [Stateless MCP and CLI Interface Specification](#8-stateless-mcp-and-cli-interface-specification)
   - 8.1 완전 무상태 MCP 아키텍처 및 서브시스템 매핑
   - 8.2 핵심 7대 MCP 도구 상세 규격
   - 8.3 5단계 클라이언트 요청 멱등성 실행 알고리즘 (Python 참조 구현체)
   - 8.4 인간 중심 CLI 인터페이스
9. [Evolutionary Migration, Pruning & Verification Invariants](#9-evolutionary-migration-pruning--verification-invariants)
   - 9.1 점진적 어댑터 마이그레이션 로드맵 (Phase 1 ~ Phase 3)
   - 9.2 폐기 및 정리 대상 요소 (Pruned Elements)
   - 9.3 6대 결정론적 차단 게이트 (Hard CI Failure Gates)
   - 9.4 4대 통계적 성능 예산 목표 (Performance Benchmark Targets)
   - 9.5 1,188개 테스트 베이스라인 무회귀 보증
10. [Independent Graph Search Design Proposal](#10-independent-graph-search-design-proposal)
   - 도메인 독립 탐색 모듈의 상세 계약과 production-ready 검증 계획
   - 기존 Vault Graph 연동 어댑터의 별도 상세 설계 및 호환성 게이트
11. [Independent Graph Document Design Proposal](#11-independent-graph-document-design-proposal)
   - 일반 문서 그래프 패키지, 기존 기능 재사용·연동, 규칙 및 의미 추출 검증 설계

---

## 1. Intent, Vision, and Core Identity

### 1.1 The Pivot and Core Identity (정체성 전환과 핵심 정체성)
Vault Graph는 일회성 문서 RAG 챗봇과 일시적인 에이전트 러너 하네스 경쟁에서 완전히 벗어나, 다음과 같은 영구적 제품 정체성을 확립합니다:

> **The Software Invariant Engine (소프트웨어 아키텍처 불변성 엔진)**  
> *"AI 에이전트 모델과 하네스는 끊임없이 교체되고 폐기될지라도, 소프트웨어의 모듈화 경계, 설계 결정의 역사, 코딩 규약, 결정론적 테스트 계약은 절대로 훼손되지 않도록 보호하는 단 하나의 진실 원천"*

### 1.2 Direction & Vision (소프트웨어 아키텍처 불변성 엔진의 방향성)
Vault Graph는 유행성 프롬프트 래퍼나 대화형 에이전트 런타임 하네스를 지향하지 않습니다. 대신 Claude Code, Cursor, Codex 등 **어떤 자율 코딩 에이전트와 엔지니어라도 반드시 복종해야 하는 '로컬 아키텍처 기판(Local Substrate)'이자 '불변성 헌법 집행기(Invariant Enforcement Engine)'**로 방향을 확고히 고정합니다.

프로젝트 지식의 영구 권한 원천인 지식 저장소(Vault)와 실행 가능한 현재 소스 코드(Repository)를 단일한 증거 기판 위에서 융합하여, 아키텍처 엔트로피와 지식의 표류(Knowledge Drift)를 시스템적으로 방지합니다.

Vault Graph의 MCP 서버(`vg serve --mcp`)가 채택하는 무상태(stateless) 인터페이스는 Anthropic이 제안하여 SEP-2575(2026-07-28 확정, Final)에서 최종 확정된 "Make MCP Stateless" 규격에 정합합니다. 이 모델은 초기화 핸드셰이크를 제거하고 각 요청을 자체 완결(self-contained)시켜, 프로토콜 계층이 세션을 유지하지 않도록 합니다. Vault Graph는 이 프로토콜 계층의 무상태성을 보존하면서, 에이전트 간 시맨틱 임대·프리머지 계약·Wait-for Graph 등의 조율 상태를 서브시스템 B의 `coordination.db`(SQLite WAL) 트랜잭션으로 디스크에 지속합니다. 이는 SEP-2575 Rationale에서 명시된 "stateless 프로토콜 위에 stateful 애플리케이션을 구축할 수 있다"는 원칙과 동일한 구조입니다. 또한 요청 멱등성 처리(8.3절)는 SEP-3182(Request Idempotency)의 애플리케이션 계층 구현입니다.

### 1.3 Intent (설계 의도: 자율 에이전트 엔트로피와 50년 불변 원칙)
소프트웨어 공학의 역사는 복잡도(Complexity)와 엔트로피(Entropy)에 저항해 온 역사입니다. 생성형 AI와 자율 코딩 에이전트의 등장은 코드 작성 속도를 비약적으로 끌어올렸지만, 동시에 **시스템 아키텍처의 파편화, 암묵적 설계 결정의 무단 파괴, 코딩 컨벤션 붕괴, 의미론적 충돌(Semantic Drift)**이라는 중대한 위기를 초래했습니다.

프롬프트 엔지니어링, 대화 루프, 챗 UI, 임시 워크플로 러너는 일시적인 유행(Ephemeral Fashion)에 불과합니다. 기반 모델이 진화하고 새로운 도구가 등장하면 어제의 하네스는 즉시 버려집니다. 그러나 **존 폰 노이만과 에츠허르 데이크스트라부터 존 오스터하우트에 이르기까지 반세기에 걸쳐 정립된 '모듈화(Modularization)', '정보 은닉(Information Hiding)', '아키텍처 불변식(Invariants)', '결정론적 검증(Deterministic Verification)'의 원칙은 50년이 지나도 결코 변하지 않는 가치(Invariants)**입니다.

Vault Graph는 유행을 따르는 하네스 개발을 중단하고, 모든 에이전트와 엔지니어가 공유하는 불변성 집행 기판으로서 다음 4대 핵심 의도를 관철합니다:
1. **소프트웨어 엔트로피의 수학적 차단:** 자율 에이전트가 단기적 편의를 위해 순환 의존성을 만들거나 모듈 경계를 허무는 행위를 정적 그래프 수준에서 즉각 거부합니다.
2. **자족적 코드 불변성과 선언적 헌법 검증:** 문서를 또 다른 관리 및 유지보수의 대상으로 삼아 코드 심볼과 억지로 바인딩하지 않으며, 소스 코드 스스로가 실행 가능한 테스트 계약과 기계 헌법 매니페스트(`.vault-graph/invariants.yaml`)를 통해 구조적 불변성을 입증하도록 강제합니다.
3. **독립적 작업의 의미론적 조율:** 멀티 에이전트 병렬 작업 환경에서 물리적 파일 충돌뿐 아니라 의미론적 인터페이스 파괴(Semantic Collision)를 사전 차단합니다.
4. **절대적 재현성 보장:** 자연어 추론이나 확률적 환각에 판단을 맡기지 않고, 결정론적 정적 분석과 불변 테스트 계약을 통해 통과 여부를 검증합니다.

### 1.4 Goals (핵심 목표: 4대 불변 목표 및 통합 비전)

#### 4대 불변성 엔진 핵심 목표 (Core Invariant Goals)
1. **Zero-Mutation Safety (무변형 안전성):** 소스 코드와 지식 저장소(Vault)를 직접 수정하거나 임의로 변경하지 않으며, 완벽한 읽기 전용(Read-Only) 및 언제든 파기 후 재생성 가능한(Rebuildable) 프로젝션을 유지합니다.
2. **Deterministic Verification (결정론적 검증):** 자연어 해석이나 확률적 추론에 기대지 않고, Tree-sitter AST 구문 파싱과 rustworkx 유향 그래프 토폴로지 알고리즘을 통해 $O(V+E)$ 시간 복잡도 내에서 엄격한 수학적·구조적 불변식을 검증합니다.
3. **Vendor-Neutral Multi-Agent Coordination (벤더 중립적 에이전트 조율):** Claude Code, Cursor, Codex 등 다양한 에이전트 런타임이 공통의 표준 MCP(Model Context Protocol)와 CLI를 통해 단일 진실 원천을 조회하고, 의미론적 임대(Semantic Lease)와 프리머지 계약을 조율할 수 있도록 지원합니다.
4. **Self-Contained Code Invariance (자족적 코드 불변성):** 문서와 코드 간의 인위적 접점이나 추적성 유지보수 부담을 완전히 제거하고, 순수 코드 AST와 선언적 기계 헌법에 기반한 자족적 불변성 집행을 통해 아키텍처 엔트로피를 원천 차단합니다.

#### Vault Graph 통합 기반 비전 (Unified Evidence Substrate)
불변성 엔진은 기존 Vault Graph가 정립해 온 핵심 역량을 포트-어댑터 아키텍처 뒤로 온전히 계승합니다:
* **Project Memory Projection:** 지식 저장소(Vault)를 지속적이고 구조화된 프로젝트 기억 저장소로 투영합니다.
* **Context Packs & Evidence-First Retrieval:** 에이전트에게 필요한 최소 증거 블록을 압축하여 토큰 효율적인 컨텍스트 팩을 제공합니다.
* **GraphRAG & Impact Projection:** 엔티티와 관계 기반의 그래프 탐색 및 코드 변경 영향도 분석을 제공합니다.

### 1.5 Three Authority Domains (3대 권한 영역 모델)
Vault Graph는 세 가지 독립된 권한 영역을 엄격하게 구분하며, 권한 영역 사이의 직접적인 무단 쓰기를 엄격히 금지합니다:

```text
+------------------------------------+   +------------------------------------+
| [Domain 1] Vault Authority         |   | [Domain 2] Repository Authority    |
| (Durable External Knowledge)       |   | (Executable Code & Tests)          |
| - raw/, wiki/, docs/               |   | - src/, tests/, .vault-graph/      |
| - 읽기 전용 참조 (DocumentReader)  |   | - Tree-sitter AST / git worktree   |
+------------------------------------+   +------------------------------------+
                  │                                         │
                  │ (읽기 전용 추출)                         │ (읽기 전용 투영)
                  └────────────────────┬────────────────────┘
                                       ▼
+-----------------------------------------------------------------------------+
| [Domain 3] Vault Graph Runtime & Coordination Substrate                     |
|                                                                             |
| [소모성 분석 투영 (Disposable Projections)]                                  |
| - 메타데이터 저장소 (SQLite metadata-v3) & 불변 캐시 (.rx)                   |
| - 토폴로지 유향 그래프 (rustworkx PyDiGraph)                                |
|                                                                             |
| [내구성 동시성 조율 기판 (Durable Coordination Substrate)]                  |
| - 원자적 런타임 조율 저장소 (SQLite WAL coordination.db)                    |
| - 시맨틱 임대, 프리머지 계약 원장, 멱등성 원장, WFG 교착 상태 감시            |
|                                                                             |
| [인터페이스 어댑터]                                                         |
| - 무상태 표준 MCP (SEP-2575 Tri-Transport) 및 대칭형 인간 중심 CLI          |
+-----------------------------------------------------------------------------+
```

1. **Vault 권한 도메인:** 장기 지속적인 의사결정 기록, 기획 의도, 프로젝트 사양을 영구 보존하며, 코드와 억지로 결합하지 않는 독립된 참조 지식입니다.
2. **저장소 권한 도메인:** 실제 실행 가능한 최신 소스 코드, 단위 테스트 스위트, 기계 헌법(`.vault-graph/invariants.yaml`)을 관장하는 자족적 실행 기판입니다.
3. **불변성 엔진 도메인:** 읽기 전용 데이터를 분석하여 위상 불변식을 검증하고, 에이전트 간 동시성 임대 및 계약을 조율하는 무상태 런타임 기판입니다.

### 1.6 Mechanism vs. Policy Doctrine (기작과 정책의 분리 원칙)
- **엔진의 불변 메커니즘 (Mechanism):** 순환 참조 탐색 알고리즘, AST 패턴 매칭, 영향 반경 계산, 비가역적 래칫 기작은 엔진에 고정됩니다.
- **프로젝트의 다형적 정책 (Policy):** 프로젝트의 규모, 언어, 도메인에 따라 적용되는 계층 구조와 컨벤션은 선언적 헌법 매니페스트(`.vault-graph/invariants.yaml`)를 통해 다양성을 완벽히 수용합니다.

### 1.7 진화적 아키텍처 및 3단계 어댑터 마이그레이션 (Evolutionary Architecture)
기존 코드베이스와 지식 자산을 임의로 파괴하지 않고 안전하게 불변성 엔진으로 도약하기 위해 3단계 점진적 마이그레이션 전략을 준수합니다:
1. **1단계 (이중 코어 공존, Dual-Core Coexistence):** 불변성 엔진(`vault_graph.invariants`)을 기존 Vault 색인 및 답변 합성 모듈과 동등하게 병렬 통합합니다. 테스트 베이스라인은 수집 1,188개 기준 failures=0, errors=0을 보장합니다(조건부 스모크 1건 스킵 허용).
2. **2단계 (포트/어댑터 분리, Decoupled Port/Adapter Architecture):** 기존 Vault 접근 및 답변 합성 모듈을 명시적 포트-어댑터 인터페이스 뒤로 격리하여, 불변성 엔진의 핵심 분석 및 검증 로직이 외부 Vault 경로 없이 완전히 독립 구동되도록 분리합니다.
3. **3단계 (저장소 네이티브 기본 모드, Repo-Native Default):** 일반 Git 저장소에서는 외부 Vault 없이 순수 아키텍처 불변성 분석 엔진으로 기본 동작하며, `--vault-path` 매개변수 제공 시 기존 Vault 색인 및 질의 기능을 완벽하게 지원합니다.

#### Phase 1 종료 조건 (Phase 1 Exit Criteria)
Phase 1은 다음 조건이 모두 충족되고 `docs/DECISIONS.md`에 "Phase 1 Exit" 결정이 기록될 때 종료됩니다:

1. **불변성 엔진과 Vector/RAG 어댑터의 격리 확인:** `vault_graph.invariants` 및 `vault_graph.graph`에서 Chroma·FastEmbed·벡터/키워드 색인 코드를 직접 참조하지 않으며, 기존 Vault 접근 기능(컨텍스트 팩 빌더, 벡터/키워드 조회 등)은 `vault_graph.vault_adapter` 아래의 포트-어댑터 진입점에서만 지연 로딩(lazy import)됩니다.
2. **자연어 답변 합성 모듈의 포트-어댑터 분리:** `vault_graph.answer.*` 및 프롬프트 합성(`mcp_prompts.py`)이 Phase 2의 플러그형 어댑터 인터페이스 뒤로 이동 완료됩니다.
3. **문맥 팩 호환성(9.6절)** 하에서의 회귀 기준선 유지: 공존 단계의 기존 테스트 스위트와의 100% 하위 호환성을 유지하며, 1,188 테스트 베이스라인 failures=0, errors=0을 유지합니다(조건부 스모크 1건 스킵 허용).

### 1.8 영구 거버넌스 및 기준 문서의 지속성 (Durable Governance Preservation)
- `docs/archive/SPEC-v1.2.md`: v1.2 기준 제품 명세로서 영구 보존.
- `docs/DECISIONS.md`: 승인된 제품 및 아키텍처 결정 사항을 기록하는 유일한 원장으로 영구 유지.
- `docs/PATCH_LOG.md`: 결함 수정 및 검증 이력을 기록하는 영구 감사 원장으로 유지.
- `docs/CONVENTIONS.md`: 파이썬 명명 규칙 및 스타일 가이드로서 지속 준수.

---

## 2. Four Subsystem Boundaries

과거 단일한 '제로 쓰기 / 순수 무상태' 선언이 초래한 내부 모순을 완전히 해소하기 위해, 엔진을 명확한 경계를 지닌 4대 서브시스템으로 분할하여 정의합니다:

```text
+---------------------------------------------------------------------------------+
| 서브시스템 A: 정적 분석 엔진 (Static Analysis Engine)                               |
| - 대상: src/, tests/, .vault-graph/invariants.yaml, .vault-graph/exemptions.json |
| - 쓰기: 서브시스템 A 0바이트 (O_RDONLY 파일 디스크립터 계약)                       |
+---------------------------------------------------------------------------------+
| 서브시스템 B: 런타임 조율 저장소 (Runtime Coordination Store)                         |
| - 경로: <graph-home>/run/<repo_hash>/coordination.db (SQLite WAL)              |
| - 역할: 의미론적 임대(Lease), 인터페이스 계약 스테이징, WFG 데드락 방지                   |
+---------------------------------------------------------------------------------+
| 서브시스템 C: 프리머지 계약 미리보기 수명주기 (Pre-merge Contract Preview)           |
| - 경로: .vault-graph/premerge_contract_previews/ (.gitignore 강제 등록)      |
| - 역할: SHA256 무결성 헤더가 포함된 임시 .pyi 생성 및 만료/머지 시 자동 정리   |
| - 원칙: 크로스 워크트리 직접 쓰기 금지, 항상 로컬 워크트리 소유자가 구체화      |
+---------------------------------------------------------------------------------+
| 서브시스템 D: 명시적 거버넌스 도구 (Explicit Governance Tooling)                      |
| - 대상: .vault-graph/exemptions.json (래칫 다운), invariants.yaml (헌법 개정)       |
| - 성격: 검증 부수효과가 아닌 명시적 CLI 호출에 의한 Git 추적 변경 기록                   |
+---------------------------------------------------------------------------------+
```

1. **서브시스템 A (정적 분석 엔진, Static Analysis Engine):**
   - `src/`, `tests/`, `.vault-graph/invariants.yaml`, `.vault-graph/exemptions.json`을 검증할 때 완전한 읽기 전용(`O_RDONLY` 또는 `mode="r"`) 계약을 준수합니다.
   - 서브시스템 A는 단 1바이트의 쓰기도 발생시키지 않습니다. C 미리보기 경로와 D 명시 명령은 별도 서브시스템 예외입니다.
   - 전역 디렉터리 체크섬 대신, 읽기 전용 파일 디스크립터 강제 및 ΔF 스냅샷 해시 검증으로 무변형을 검사합니다.
2. **서브시스템 B (런타임 조율 저장소, Runtime Coordination Store):**
   - `<graph-home>/run/<repo_hash>/coordination.db`에 위치하며 SQLite WAL 모드로 구동됩니다. `<repo_hash>`는 `SHA256(realpath(git common dir))`이며, 기본 graph-home은 `~/.vault-graph`입니다.
   - 워크트리 간 동시 작업 시 의미론적 임대(Semantic Lease), 사전 인터페이스 계약 스테이징(Staged Contract), 대기 그래프(Wait-for Graph)를 원자적으로 관리합니다.
   - 프로세스 메모리에는 영구 세션을 유지하지 않는 무상태(stateless) 구조이나, 디스크 트랜잭션으로 프로세스 재시작 생존을 제공합니다. OS 충돌 시 유실은 재획득·재스테이징으로 복구합니다.
3. **서브시스템 C (프리머지 계약 미리보기, Pre-merge Contract Preview):**
   - 병렬 작업 중인 에이전트 간 비동기 타입 조율을 위해 `.vault-graph/premerge_contract_previews/` 경로에 미리보기 `.pyi` 파일을 생성합니다.
   - 이 경로는 반드시 `.gitignore`에 등록되어 Git 추적 대상에서 엄격히 제외됩니다.
   - 모든 미리보기 파일은 상단에 SHA256 무결성 헤더를 지니며, 임대 만료·브랜치 머지·CLI 정리 시 자동으로 제거됩니다.
   - 크로스 워크트리 파일 직접 쓰기를 금지합니다. 생산자는 `coordination.db`에만 계약을 기록하고, 소비자 워크트리 소유자가 자기 경로에 파일을 구체화합니다.
4. **서브시스템 D (명시적 거버넌스 도구, Explicit Governance Tooling):**
   - 면제 한도의 영구 하향(Ratchet down) 및 헌법 매니페스트 개정은 검증 명령어 실행 중의 암묵적 부수 효과로 발생하지 않습니다.
   - 반드시 엔지니어 또는 에이전트의 명시적인 거버넌스 명령(`vg exemption ratchet`, `vg constitution amend`) 호출을 통해서만 변경되며, 독립적인 Git 커밋으로 영구 기록됩니다.

---

## 3. Three-Tier Invariant Hierarchy & Core Values

### 3.1 3단계 불변식 계층 (Three-Tier Invariant Hierarchy)

```text
+-------------------------------------------------------------------------+
| [Tier 0] 절대 불변식 (Universal Structural Invariants)                  |
| - 규모/언어 불문 강제: 순환 참조 금지, 데드락 방지, 서브시스템 A 읽기 전용 경계 |
+-------------------------------------------------------------------------+
                                    | 계승(Inherit)
                                    v
+-------------------------------------------------------------------------+
| [Tier 1] 아키텍처 원형 프로파일 (Archetype Profiles)                     |
| - 규모/도메인별 프리셋: minimal-script, modular-monolith, clean-hexagonal, client-mobile |
+-------------------------------------------------------------------------+
                                    | 구체화(Specialize)
                                    v
+-------------------------------------------------------------------------+
| [Tier 2] 프로젝트 고유 헌법 (Project Constitution)                      |
| - .vault-graph/invariants.yaml, .vault-graph/exemptions.json            |
+-------------------------------------------------------------------------+
```

1. **Tier 0 (절대 불변식):** 어떤 프로젝트든 순환 의존성(Cyclic Dependency)은 시스템을 파괴하는 수학적 결함입니다. 무조건 강제됩니다.
2. **Tier 1 (원형 프로파일):** 프로젝트 유형에 맞춘 규격화된 표준 세트(`minimal-script`, `modular-monolith`, `clean-hexagonal`, `client-mobile`).
3. **Tier 2 (프로젝트 헌법):** `.vault-graph/invariants.yaml`에 정의되는 팀 고유의 계층 정의 및 `exemptions.json`의 점진적 면제 관리.

### 3.2 4대 핵심 불변 가치 (The 4 Non-Negotiable Invariant Values)

#### Value 1. 아키텍처 위상 및 경계 불변식 검증기 (Architectural Topology Invariant Engine)
* **정의:** 소프트웨어의 계층(Layer)과 모듈 경계는 코드의 물리적 위치가 아니라 그래프 상의 도달 가능성(Reachability)과 의존성 방향(Dependency Direction)으로 규정됩니다.
* **Strict Layering:** 고수준 비즈니스 정책(Core/Inner)은 저수준 세부 구현(Outer/Mechanism)에 직접 의존할 수 없으며, 의존성 역전 원칙을 위배하는 역방향 의존성은 절대 금지됩니다 (예: `domain` $\rightarrow$ `infrastructure` 직접 의존 금지).
* **Acyclic Dependencies:** 패키지 및 모듈 간의 순환 참조는 허용되지 않으며, 전역 $O(V+E)$ SCC 알고리즘으로 임의의 $N \ge 2$ 순환을 원천 차단합니다.
* **Deep Modules:** 모듈의 외부 공개 인터페이스 표면적은 내부 구현 복잡도 대비 극도로 작아야 하며(Information Hiding), 내부 전용 심볼이 경계 밖으로 누수되어서는 안 됩니다.
* **Rationale Integration:** 왜 이 규칙이 필요한지에 대한 설계 의도는 헌법 매니페스트(`.vault-graph/invariants.yaml`) 내 각 규칙의 `rationale` 필드에 기재되어 검증과 일체화됩니다.

#### Value 2. 멀티 에이전트 작업 공간의 의미론적 조율 (Cross-Worktree Semantic Coordination)
* **정의:** 코드는 문서와의 인위적 결합 없이 스스로 자족적이어야 하며, 다중 에이전트 환경에서 발생하는 엔트로피는 물리적 파일 충돌 이전에 인터페이스와 심볼 수준에서 기계적으로 통제되어야 합니다.
* **Semantic Lease & Blast Radius Management:** 멀티 에이전트 환경에서 에이전트가 특정 심볼에 대해 작업 의향을 선언하면, 해당 심볼의 1-hop 호출 그래프(Blast Radius)에 의미론적 임대(Semantic Lease)를 부여하여 동시 작업 중인 다른 에이전트와의 충돌을 사전에 원천 차단합니다.
* **Pre-merge Interface Contracts:** 상류 에이전트는 구현 완료 전 변경될 시그니처 AST 계약을 `coordination.db`에 선공개하여, 하류 에이전트가 타입 스텁(`.pyi`)을 통해 병렬 개발할 수 있도록 격리합니다.
* **Zero Document Burden:** 문서를 코드 심볼과 억지로 결합하거나 또 다른 관리 대상으로 만들지 않으며, 불변성은 순수하게 실행 가능한 코드(`src/`), 테스트(`tests/`), 기계 헌법 규칙(`.vault-graph/invariants.yaml`)에 의해서만 강제됩니다.

#### Value 3. 코딩 컨벤션과 정적 제약의 기계적 집행 (Executable Coding Conventions)
* **정의:** 코딩 컨벤션은 위키에 방치된 자연어 문서가 아니라, 컴파일러 수준에서 통과 여부가 판정되는 실행 가능한 제약 조건(Executable Constraints)이어야 합니다.
* **Type Purity & Immutability:** 핵심 도메인 모델은 불변(`@dataclass(frozen=True)`)이어야 하며, 제네릭과 반환 타입을 포함한 완전한 정적 타이핑(Strict Typing)을 만족해야 합니다.
* **Error Boundary Contract:** 시스템 경계를 넘나드는 예외 처리는 `VaultGraphError` 하위 클래스를 명시적으로 따라야 하며, 원인 은폐(Bare Exception)를 금지합니다.
* **Naming & Structure Determinism:** 파일명, 클래스명, 모듈 구조는 [`docs/CONVENTIONS.md`](CONVENTIONS.md)의 규칙을 100% 준수해야 합니다.
* **Fail-Closed Syntax Safety:** 치명적 구문 오류(Level 2 Syntax Error) 존재 시 검증을 즉시 차단합니다. 작업 중인 임시 구문 오류(Level 1 Syntax Error)는 경고를 보고하되 개발 흐름을 완전히 차단하지 않습니다.

#### Value 4. 결정론적 테스트 계약과 안전 경계 (Deterministic Test Contract Guard)
* **정의:** 자동화된 테스트로 증명되지 않은 아키텍처와 코드는 존재하지 않는 것과 같습니다. 모든 검증은 로컬 환경에서 100% 재현 가능해야 합니다.
* **Read-Only Boundary Invariant (서브시스템 A):** 정적 검증 및 분석 과정에서 소스 코드 및 저장소 거버넌스 파일에 단 1바이트의 쓰기도 발생하지 않습니다 (`O_RDONLY` 파일 디스크립터 계약 준수).
* **Deterministic Fakes & Isolation:** 모든 테스트 스위트는 외부 네트워크, 시계 변동, 난수성에 의존하지 않는 결정론적 가짜 객체를 사용합니다.
* **Impact-Driven Test Contract:** 코드가 수정되었을 때, AST 호출 경로 상 영향을 받는 모든 상류/하류 인터페이스에 대해 필수적으로 통과해야 하는 '최소 불변 테스트 스위트'를 역산출합니다.
* **Regression Baseline Protection:** 기존 1,188개 단위/통합 회귀 테스트 스위트를 100% 통과하는 절대적 안전 기준선으로 영구 유지합니다.

---

## 4. Repository Topology & Governance Ledgers

### 4.1 저장소 구조 및 3대 실행 가능 실체 (The Executable Trinity)

```text
<repository-root>/
├── README.md                      # [인간/에이전트 공통 안내] 저장소 목적 및 빠른 시작 이정표
│
├── docs/                          # [영구 거버넌스 및 기준선 명세]
│   ├── SPEC.md                    # [본 문서: 최상위 활성 제품 명세서] v5.1
│   ├── archive/                   # [아카이브 보존 경로]
│   │   └── SPEC-v1.2.md           # [보존 기준선] v1.2 기능 명세서 (1,188개 테스트 근거)
│   ├── DECISIONS.md               # [영구 결정 원장] 승인된 아키텍처/제품 결정 기록
│   ├── PATCH_LOG.md               # [영구 패치 원장] 검토/검증 결함 및 수정 이력
│   └── CONVENTIONS.md             # [코딩 컨벤션] Python 스타일 및 명명 규칙
│
├── .vault-graph/                  # [기계 거버넌스 기판: Invariant Substrate]
│   ├── invariants.yaml            # [구조적 헌법] 계층 경계, 순환 금지, 타입 불변식 및 rationale 정의
│   ├── exemptions.json            # [품질 래칫] 동결된 일시적 아키텍처 면제 장부 (단방향 감소만 허용)
│   └── premerge_contract_previews/ # [서브시스템 C: 프리머지 계약 미리보기 경로 - .gitignore 대상]
│
├── src/                           # [시스템 구현체 - How] 단방향 레이어 규칙을 따르는 소스 코드 (AST)
└── tests/                         # [실행 명세 - What & Behavioral Why] 1,188개 테스트 및 행위 계약
```

- **How (어떻게 동작하는가):** 소스 코드 AST (`src/`) $\rightarrow$ 런타임/컴파일러가 실행
- **What (무엇을 하는가 & 행위적 Why):** 행위 테스트 계약 (`tests/`) $\rightarrow$ pytest/테스트 러너가 실행 (1,188개 테스트 기준선)
- **Guard & Architectural Why (어떤 경계를 지키는가):** 아키텍처 헌법 (`.vault-graph/invariants.yaml`) $\rightarrow$ 불변성 엔진이 50ms 내 검증

### 4.2 Architecture Exemptions Ledger (`.vault-graph/exemptions.json`)

레거시 코드나 점진적 리팩토링 과정에서 불가피하게 존재하는 아키텍처 위반 사항을 **'동결된 일시적 면제(Exemptions)'**로 관리하는 기계 판독용 장부입니다. 신규 위반은 즉시 차단되지만, 본 장부에 등록된 항목은 빌드가 허용되며 리팩토링 시 명시적 거버넌스 도구(서브시스템 D)를 통해 영구 감소(Ratchet Down)합니다.

```json
{
  "version": "1.0",
  "generated_at": "2026-09-06T12:00:00Z",
  "total_exemptions_ceiling": 2,
  "exemptions": [
    {
      "id": "EXEMPT-001",
      "rule_id": "strict-layer-boundaries",
      "targets": [
        "vault_graph.graph.graph_service -> vault_graph.graph.topology_cache"
      ],
      "reason": "단방향 계층 분리 리팩토링 진행 중 (임시 면제)",
      "created_at": "2026-09-06"
    },
    {
      "id": "EXEMPT-002",
      "rule_id": "strict-layer-boundaries",
      "targets": [
        "vault_graph.code_index.legacy_adapter -> vault_graph.storage"
      ],
      "reason": "단방향 포트-어댑터 인터페이스 교체 전까지 임시 허용",
      "created_at": "2026-09-06"
    }
  ]
}
```

* **Tier 0 불변식 면제 불가 원칙:** Tier 0 절대 불변식(순환 의존성 차단, 데드락 방지, 서브시스템 A `O_RDONLY` 읽기 전용 경계)은 `exemptions.json`을 통한 면제가 원천적으로 불가능하며, CI(GATE-6)에서 0건으로 엄격히 강제됩니다. 면제 장부는 오직 Tier 1 아키텍처 프로필에 대한 프로젝트별 Tier 2 한시적 예외만을 관리합니다.
* **비가역성 불변식 (Irreversible Invariant):** `total_exemptions_ceiling` 및 `exemptions` 항목은 리팩토링으로 위반이 해소될 때 서브시스템 D의 명시적 실행(`vg exemption ratchet`)을 통해 영구 하향(Ratchet Down) 조정됩니다. 상향은 원칙적으로 금지되며, 예외적으로 `vg exemption ceiling raise --reason --expiry` 명령과 별도 Git 커밋으로만 허용됩니다. 상향 커밋 없는 증가는 CI에서 차단됩니다.

### 4.3 헌법 매니페스트 최소 스키마 (`.vault-graph/invariants.yaml`)

GATE-2 판정 기준입니다. `rationale`은 필수이며, DMI 임계값과 가중치는 Tier 2 정책으로 재정의할 수 있습니다.

```yaml
version: "1.0"
profile: minimal-script | modular-monolith | clean-hexagonal | client-mobile
layers:
  - name: domain
    paths: ["src/**/domain/**"]
rules:
  - id: no-circular-dependencies
    description: 순환 의존성 금지
    rationale: 순환은 변경 전파를 예측 불가능하게 만든다
    severity: error
  - id: strict-layer-boundaries
    description: 하위에서 상위로 의존 금지
    rationale: 단방향 계층을 유지한다
    severity: error
dmi_overrides:
  shallow_below: 1.5
  deep_at_or_above: 4.0
```

---

## 5. SQLite WAL Coordination Store Architecture (서브시스템 B)

### 5.1 상태 수명주기 분리 및 저장소별 해시 격리 (`<repo_hash>`)

```text
+------------------------------------+      +-----------------------------------------+
|      Rebuildable Projections       |      |       Runtime Coordination Store        |
|  <graph-home>/generations/.../     |      |   <graph-home>/run/<repo_hash>/         |
|  - metadata.db (심볼, 위상 인덱스)   |      |  - coordination.db (SQLite WAL Mode)    |
|  - TopologyGraph (rustworkx graph) |      |  - 의미론적 임대 및 인터페이스 계약 스테이징|
|  - 소스로부터 100% 재구축 가능      |      |  - Wait-for Graph (교착 상태 감시)       |
+------------------------------------+      +-----------------------------------------+
```

1. **영구 파생 프로젝션 (`metadata.db`):** 순수 파생 데이터로서 언제든 삭제 후 소스 코드와 헌법 매니페스트로부터 100% 재구축(`vg index --rebuild`)됩니다. 모든 파생 경로는 `GraphHomeResolver`를 따르며 기본값은 `~/.vault-graph`입니다. `--graph-home` 지정 시 해당 루트 아래에 배치합니다.
2. **런타임 동시성 저장소 (`coordination.db`):** 무상태(Stateless) 프로세스들이 동시 접근할 수 있도록 SQLite WAL 모드로 구동되며, 프로세스 메모리가 아닌 디스크 트랜잭션으로 원자적 임대와 계약을 관리합니다. `<repo_hash>`는 `SHA256(realpath(git common dir))`로 계산합니다(`git rev-parse --git-common-dir` 실경로 기준). Git 저장소가 아닐 때만 저장소 루트 실경로로 폴백합니다. 워크트리 절대 경로나 remote URL은 식별자로 쓰지 않습니다. 최종 경로는 `<graph-home>/run/<repo_hash>/coordination.db`입니다.

### 5.2 Connection PRAGMA 명세
`coordination.db`에 연결하는 모든 프로세스는 연결 초기화 시 다음 PRAGMA를 필수적으로 실행해야 합니다:

```sql
PRAGMA journal_mode = WAL;
PRAGMA busy_timeout = 5000;
PRAGMA synchronous = NORMAL;
PRAGMA foreign_keys = ON;
```

- `journal_mode = WAL`: 읽기 작업과 쓰기 작업의 완전한 동시성을 보장하여 잠금 충돌을 최소화합니다.
- `busy_timeout = 5000`: 드라이버 수준 대기 상한입니다. 애플리케이션 재시도와 합산하지 않고 요청별 절대 마감 시각 5,000ms를 공유합니다. 마감 초과 시 `CoordinationLockTimeoutError`를 반환합니다.
- `synchronous = NORMAL`: WAL 모드에서 디스크 동기화 부하를 최적화합니다. OS 충돌 시 최근 확정 트랜잭션 유실이 가능하므로, 임대 재획득과 계약 재스테이징을 정상 복구 경로로 둡니다. 프로세스 재시작 생존은 보장합니다.
- `foreign_keys = ON`: 외래 키 제약 조건을 강제하여 참조 무결성을 보장합니다.

### 5.3 4대 테이블 표준 DDL 스키마

```sql
-- 0. Schema version (cache/DB format invalidation)
CREATE TABLE IF NOT EXISTS schema_version (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- 1. Client Request Deduplication & Idempotency
CREATE TABLE IF NOT EXISTS client_requests (
    client_request_id TEXT PRIMARY KEY,
    command TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    request_payload_hash TEXT NOT NULL,
    response_json TEXT,
    status TEXT NOT NULL CHECK(status IN ('in_progress', 'completed', 'failed')),
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_client_requests_created ON client_requests(created_at);

-- 2. Semantic Leases
CREATE TABLE IF NOT EXISTS semantic_leases (
    lease_id TEXT PRIMARY KEY,
    client_request_id TEXT NOT NULL REFERENCES client_requests(client_request_id) ON DELETE CASCADE,
    agent_id TEXT NOT NULL,
    worktree_path TEXT NOT NULL,
    root_symbol_id TEXT NOT NULL,
    blast_radius_symbols TEXT NOT NULL, -- JSON array of symbol strings
    intent_summary TEXT NOT NULL,
    heartbeat_interval_seconds REAL NOT NULL DEFAULT 30.0,
    acquired_at REAL NOT NULL,
    expires_at REAL NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('active', 'released', 'expired'))
);
CREATE INDEX IF NOT EXISTS idx_leases_expires ON semantic_leases(expires_at) WHERE status = 'active';
CREATE INDEX IF NOT EXISTS idx_leases_root_symbol ON semantic_leases(root_symbol_id) WHERE status = 'active';
CREATE INDEX IF NOT EXISTS idx_leases_agent ON semantic_leases(agent_id);

-- 3. Staged Interface Contracts (Pre-merge Contract Preview source of truth)
CREATE TABLE IF NOT EXISTS staged_contracts (
    contract_id TEXT PRIMARY KEY,
    client_request_id TEXT NOT NULL REFERENCES client_requests(client_request_id) ON DELETE CASCADE,
    producer_agent_id TEXT NOT NULL,
    producer_worktree_path TEXT NOT NULL,
    symbol_id TEXT NOT NULL,
    signature_ast_json TEXT NOT NULL,
    preview_content TEXT NOT NULL,
    sha256_hash TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('draft', 'locked', 'merged', 'superseded')),
    staged_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_staged_contracts_symbol ON staged_contracts(symbol_id, status);
CREATE INDEX IF NOT EXISTS idx_staged_contracts_producer ON staged_contracts(producer_agent_id);

-- 4. Wait-For Graph (Dependency & Deadlock Detection)
CREATE TABLE IF NOT EXISTS wait_for_edges (
    waiting_agent_id TEXT NOT NULL,
    blocking_agent_id TEXT NOT NULL,
    target_symbol_id TEXT NOT NULL,
    contract_id TEXT REFERENCES staged_contracts(contract_id) ON DELETE CASCADE,
    created_at REAL NOT NULL,
    PRIMARY KEY (waiting_agent_id, blocking_agent_id, target_symbol_id, contract_id)
);
CREATE INDEX IF NOT EXISTS idx_wfg_blocking ON wait_for_edges(blocking_agent_id);
```

- `client_requests`는 TTL 정리 대상입니다. `vg maintenance prune`으로 완료 30일 경과 행을 삭제합니다.
- `worktree_path`는 git 공통 디렉터리 실경로 아래만 허용합니다. `symbol_id`는 영문·숫자·점·밑줄·화살표 외 문자를 거부합니다. `preview_content`는 크기 상한 256KB를 적용합니다.

### 5.4 동시성 프로토콜, 재시도 루프 및 멱등성 보장 전략

#### 1. 즉시 쓰기 트랜잭션 (Immediate Write Transactions)
상태를 변경하는 모든 연산(`claim_semantic_lease`, `stage_interface_contract` 등)은 반드시 `BEGIN IMMEDIATE` 트랜잭션을 사용하여 즉시 쓰기 락 의도를 확보합니다. 이는 지연된 락 업그레이드로 인한 상호 교착 상태(Deadlock)를 원천 차단합니다.

#### 2. 지수 백오프 및 무작위 지터 재시도 루프 (Exponential Backoff with Jitter)
SQLite 드라이버 수준의 `busy_timeout` 대기 외에도, 일시적 경합에 의한 `sqlite3.OperationalError`("database is locked" 또는 "busy") 발생 시 애플리케이션 레벨의 재시도 루프를 수행합니다:
- **최대 재시도 횟수:** 5회
- **기본 대기 시간 (Base Delay):** 50ms
- **증가 계수 (Multiplier):** 1.5x
- **무작위 지터 (Randomized Jitter):** ±20% 범위의 무작위 변동 적용
- **누적 상한 (Timeout Cap):** 누적 5,000ms 초과 시 즉시 중단하고 `CoordinationLockTimeoutError`를 발생시켜 활성 임대 진단 정보를 반환합니다. 지터는 경합 상태의 교착·스로팅을 완화하기 위한 일시적 지연 분산 목적으로만 사용되며, 검증 결과물(위배 여부·그래프 구조·해지 결과)은 지터 적용 여부와 무관하게 결정론적으로 동일하므로 안전성 판정은 지터에 의존하지 않습니다.

```python
import time
import random
import sqlite3

def execute_with_coordination_retry(db_conn, operation_fn, max_retries=5, base_delay=0.05, max_delay=5.0):
    start_time = time.time()
    for attempt in range(max_retries):
        try:
            return operation_fn(db_conn)
        except sqlite3.OperationalError as err:
            if ("locked" in str(err) or "busy" in str(err)) and attempt < max_retries - 1:
                elapsed = time.time() - start_time
                if elapsed >= max_delay:
                    raise CoordinationLockTimeoutError(f"Lock timeout exceeded after {elapsed:.2f}s: {err}")
                jitter = random.uniform(0.8, 1.2)
                sleep_time = min(base_delay * (1.5 ** attempt) * jitter, max_delay - elapsed)
                time.sleep(max(0.0, sleep_time))
            else:
                raise
```

#### 3. 클라이언트 요청 중복 제거 (`client_request_id` Idempotency Protocol)
네트워크 재시도, 프로세스 비정상 재시작, 다중 에이전트 재호출 환경에서 안전한 멱등성을 보장하기 위해 모든 변경 요청에 UUIDv4 형식의 `client_request_id`를 의무화합니다:
1. `BEGIN IMMEDIATE` 실행 후 `client_requests` 테이블을 조회합니다.
2. 동일 `client_request_id`가 이미 존재하면 저장된 `request_payload_hash`와 현재 요청 해시를 비교합니다. 해시가 다르면 비즈니스 로직을 실행하지 않고 `PayloadMismatchError`를 반환합니다.
3. 상태가 `'completed'`이고 해시가 일치하면 비즈니스 로직을 재실행하지 않고 기저장된 `response_json`을 즉시 반환합니다(`is_replayed=true`).
4. 상태가 `'in_progress'`이며 마지막 갱신 시간(`updated_at`)이 10초 이내인 경우, 중복 병렬 실행을 차단하기 위해 `ConcurrentOperationError`를 발생시킵니다.
5. 신규 요청인 경우 `status = 'in_progress'`로 행을 삽입하고 비즈니스 로직을 수행한 뒤 `status = 'completed'`로 갱신하고 커밋합니다.
6. 실패 시 비즈니스 쓰기를 롤백한 뒤 별도 트랜잭션으로 `status = 'failed'`를 기록합니다. 실패 기록 커밋이 부분 쓰기를 확정하지 않습니다.

---

## 6. Cross-Worktree Orchestration Protocol

### 6.1 Concurrency Model: Physical Isolation vs. Logical Concurrency

복수 에이전트가 단일 저장소를 목표로 협업할 때, 물리적 파일 충돌과 의미론적 파편화를 방지하는 2계층 동시성 오케스트레이션 모델입니다. 

물리적 파일 I/O는 Git Worktree로 철저히 격리하며, 논리적 인터페이스 의존성은 **런타임 조율 저장소(서브시스템 B: `<graph-home>/run/<repo_hash>/coordination.db`)**와 **프리머지 계약 미리보기 경로(서브시스템 C: `.vault-graph/premerge_contract_previews/`)**를 통해 원자적으로 중계합니다. 크로스 워크트리 파일 직접 쓰기를 금지하며, 미리보기 파일 쓰기는 항상 로컬 워크트리 소유자가 수행합니다.

```text
 [워크트리 A: 에이전트 1]                                 [워크트리 B: 에이전트 2]
  (AuthService 리팩토링 - 공급자)                           (OrderService 개발 - 소비자)
           |                                                        |
  1) 인터페이스 계약 선공개                                                  |
     (vg_register_premerge_contract action='stage')                 |
           |                                                        |
            +--------> [ coordination.db (SQLite WAL) ]              |
                       - params._meta.client_request_id 멱등성 검증   |
                       - BEGIN IMMEDIATE 원자적 트랜잭션 기록          |
                       - staged_contracts 테이블 저장                 |
                       - wait_for_edges 의존성 기록 (B -> A 대기)     |
                       - DB 기록만 수행 (파일 직접 투영 금지) --------+
                                                                     |
                                                            2) 소비자 가져오기
                                                               (query 후 로컬 미리보기 구체화)
                                                               (블로킹 없이 병렬 진행)
                                                                    |
  3) 구현 완료 및 단위 테스트 통과                                           |
     (contract_locked 상태 변경) ---------------------------------->+
           |                                                        |
            +--------> [ 프리머지 사전 중첩 검증 (vg_check_premerge_overlap) ] <-+
                       - 1단계: git merge-base 텍스트 충돌 여부 확인
                       - 2단계: 양쪽 워크트리 AST 결합 검증
                       - 베이스 그래프 캐시 + 인메모리 오버레이(G_ephemeral)
                       - 불변식 위반 및 타입 불일치 제로 검증
```

### 6.2 Stateless Orchestration 핵심 기작

#### 1. 물리적 격리 (Physical Isolation via Git Worktree)
각 에이전트는 독립된 Git Worktree에서 물리적으로 격리된 파일 I/O를 수행하여 디스크 파일 쓰기 경쟁(Race Condition)을 원천 차단합니다. 작업 중인 소스 트리는 타 에이전트의 파일 수정을 직접 관측하지 않습니다.

#### 2. 디스크 기반 계약 선공개 및 배타적 트랜잭션 (Coordination Store & Atomic Transactions)
* 상류 모듈을 수정하는 에이전트(Producer)는 세부 구현 완성 전, 변경될 함수의 시그니처와 타입 규약을 `<graph-home>/run/<repo_hash>/coordination.db`에 원자적 트랜잭션으로 사전 등록(stage)합니다. 생산자는 소비자 워크트리에 파일을 직접 쓰지 않습니다.
* 모든 상태 변경 연산(`vg_acquire_lease`, `vg_register_premerge_contract` 등)은 동시성 프로토콜을 따릅니다:
  - **연결 PRAGMA:** `journal_mode = WAL;`, `busy_timeout = 5000;`, `synchronous = NORMAL;`, `foreign_keys = ON;`.
  - **트랜잭션 격리:** `BEGIN IMMEDIATE`를 사용하여 쓰기 락 의도를 즉시 선점함으로써 교착 상태를 방지합니다. 임대 획득은 만료 확인과 삽입을 같은 트랜잭션의 조건부 삽입(`WHERE NOT EXISTS`)으로 수행합니다.
  - **재시도 루프:** 락 경합 시 50ms 기본 지연, 1.5배 지수 증가, ±20% 무작위 지터를 적용한 5회 재시도 루프를 실행합니다. 드라이버 대기와 합산하지 않고 요청별 절대 마감 5,000ms를 공유합니다.
  - **요청 멱등성:** `params._meta.client_request_id`(UUIDv4)와 비즈니스 인자 기반 RFC 8785 JCS SHA-256 해시를 함께 기록합니다. 동일 ID에 해시가 다르면 `McpRpcError`를 반환합니다.
* 만료된 임대는 조회 시점 비교가 아니라 획득 트랜잭션 내 조건식으로 판정합니다. 시간 비교 기반 게으른 축출은 조회 편의 기능으로만 둡니다.
* 임대 충돌 판정: 활성 임대 간 `blast_radius_symbols` 교집합이 비어 있지 않으면 충돌로 판정합니다. `blast_radius_symbols`는 정적 직접 호출자 1-hop과 대상 심볼로 구성하며, 전이 범위는 검증 단계에서 확장합니다.

#### 3. 불변 베이스 그래프 캐시 및 인메모리 오버레이 (Immutable Base Graph & Ephemeral Overlays)
1. **불변 베이스 그래프 캐시:**
   $$\text{CacheKey} = \text{SHA256}(T_{\text{base}} \parallel \text{":"} \parallel \text{SHA256}(\texttt{invariants.yaml}) \parallel \text{":"} \parallel \text{EngineFingerprint})$$
   $$T_{\text{base}} = \texttt{git rev-parse HEAD\^{tree}}$$
   `EngineFingerprint`는 코드 내 단일 상수입니다(그래프 스키마, Tree-sitter 문법, DMI 버전). 파서나 스키마 변경 시 상수를 올려 기존 캐시를 무효화합니다. 계산된 토폴로지 그래프는 읽기 전용 디스크 캐시(`<graph-home>/cache/graphs/<CacheKey>.rx`)로 보존되며 복수 프로세스가 안전하게 동시 공유합니다. 캐시 생성은 잠금 파일로 리더 1개로 제한하고, 임시 파일은 시작 시 정리하며, 30일 미사용 캐시는 정리합니다.
2. **휘발성 인메모리 오버레이 ($G_{\text{ephemeral}}$):**
   에이전트 프로세스는 디스크 캐시를 수정하지 않고, 스냅샷 복사된 변경분과 스테이징된 계약 정보만을 메모리 상에서 베이스 그래프 위에 덧씌워 결합 그래프를 구성합니다. 단일 워크트리 검증은 $G_{\text{ephemeral}} = G_{\text{base}} \oplus \Delta G_{\text{worktree}}$, 양쪽 사전 중첩 검증은 $G_{\text{premerge}} = G_{\text{base}} \oplus \Delta_A \oplus \Delta_B$로 정의합니다. 검증 종료 시 오버레이는 즉시 소멸합니다.

### 6.3 프리머지 계약 미리보기 수명주기 (.pyi) 및 8줄 무결성 헤더 (서브시스템 C)
하류 기능을 개발하는 에이전트(Consumer)가 상류 코드가 Git에 머지되지 않은 상태에서도 LSP 및 정적 타이핑 지원을 받을 수 있도록 계약 미리보기를 제공합니다:
* **투영 경로:** `.vault-graph/premerge_contract_previews/` (해당 경로는 반드시 `.gitignore`에 등록되어 버전 관리 대상에서 영구 제외됩니다).
* **생성 원칙:** 생산자는 DB에만 계약을 기록합니다. 소비자 런타임이 `vg_register_premerge_contract(action='query')` 결과로 자기 워크트리에 미리보기 파일을 구체화합니다.
* **무결성 헤더:** 생성되는 모든 미리보기 파일 최상단에는 조작 여부를 검증하는 불변 배너 헤더를 의무 삽입합니다:
  ```python
  # ============================================================================
  # AUTO-GENERATED BY VAULT-GRAPH SOFTWARE INVARIANT ENGINE (DO NOT EDIT)
  # Contract-ID: <contract_uuid>
  # Producer-Agent: <producer_agent_id>
  # Producer-Worktree: <producer_worktree_hash>
  # Symbol-ID: <symbol_id>
  # Preview-Hash: <sha256_of_signature_ast_json>
  # Engine-Fingerprint: <graph_cache_version>
  # Generated-At-UTC: <iso_8601_timestamp>
  # ============================================================================
  ```
  `vg_check_premerge_overlap` 실행 시 헤더의 해시와 AST 시그니처를 대조하여 수동 변조 감지 시 즉시 `PreviewTamperedError`를 방출합니다.
* **자동 정리(Eviction) 조건:**
  1. 공급자 에이전트의 의미론적 임대 해제(`vg_acquire_lease action='release'`) 후 소비자가 자기 파일을 삭제
  2. 임대 만료 시간 도달 후 게으른 축출 발생 시 소비자가 자기 파일을 삭제
  3. 상류 작업 브랜치가 베이스 브랜치로 실제 병합 완료(`git merge`)될 때 소비자가 자기 파일을 삭제
  4. 엔지니어의 명시적 정리 명령(`vg clean --previews`) 실행 시

### 6.4 위상 대기열, Wait-for Graph 및 교착 상태 방지
* 상류 작업이 완료되어 테스트 통과 및 계약 확정(`contract_locked`)에 도달하기 전까지, 하류 에이전트의 최종 브랜치 머지를 보류(Semantic Hold)시킵니다.
* `wait_for_edges` 테이블을 쿼리하여 에이전트 간 환형 대기(Circular Wait)가 감지되는 즉시 `DeadlockDetectedError`를 방출하고 즉각적인 실패(Fail-fast) 처리를 유도합니다.

### 6.5 2단계 프리머지 사전 중첩 검증 (Two-Stage Pre-merge Pre-check)
실제 `git merge` 실행 전 다음 2단계를 선제 검증합니다:
1. **1단계 (물리 텍스트 정합성):** `git merge-tree` 또는 `git merge-base`를 활용하여 소스 코드 및 설정 파일의 물리적 충돌 여부를 선제 검증합니다. 동일 파일 양쪽 수정은 AST 자동 병합 없이 텍스트 단계에서 차단합니다.
2. **2단계 (의미론적 AST 정합성):** $G_{\text{premerge}} = G_{\text{base}} \oplus \Delta_A \oplus \Delta_B$ 결합 그래프에서 심볼 호출 정합성, 타입 호환성, 레이어 단방향 불변식이 유지되는지 검증합니다.

### 6.6 데이터 계약 및 Python 데이터클래스 정의

```python
from dataclasses import dataclass
from typing import Literal

@dataclass(frozen=True)
class ClientRequestRecord:
    client_request_id: str
    command: str
    agent_id: str
    request_payload_hash: str
    response_json: str | None
    status: Literal["in_progress", "completed", "failed"]
    created_at: float
    updated_at: float

@dataclass(frozen=True)
class SemanticLease:
    lease_id: str
    client_request_id: str
    agent_id: str
    worktree_path: str
    root_symbol_id: str
    blast_radius_symbols: tuple[str, ...]
    intent_summary: str
    heartbeat_interval_seconds: float  # 기본 30초
    acquired_at: float
    expires_at: float                  # 만료 시 Lazy Eviction 처리
    status: Literal["active", "released", "expired"]

@dataclass(frozen=True)
class StagedInterfaceContract:
    contract_id: str
    client_request_id: str
    producer_agent_id: str
    producer_worktree_path: str
    symbol_id: str
    signature_ast_json: str
    preview_content: str
    sha256_hash: str
    status: Literal["draft", "locked", "merged", "superseded"]
    staged_at: float
    updated_at: float

@dataclass(frozen=True)
class WaitForEdgeRecord:
    waiting_agent_id: str
    blocking_agent_id: str
    target_symbol_id: str
    contract_id: str | None
    created_at: float

@dataclass(frozen=True)
class PremergeContractValidationReport:
    is_compatible: bool
    textual_merge_clean: bool          # Git merge-tree / merge-base 사전 검증 결과
    consumer_worktree: str
    producer_worktree: str
    textual_conflict_files: tuple[str, ...]
    incompatible_call_sites: tuple[str, ...]
    topology_violations: tuple[str, ...]
```

---

## 7. Vertical Slice Specifications (VS-1 ~ VS-6)

```text
=============================================================================
[VS-1] Topological Invariant Verification Slice
       (Global O(V+E) SCC + Git Tree-Hash Caching + DMI & 3-Tier Latency SLA)
-----------------------------------------------------------------------------
[VS-2] Cross-Worktree Coordination & Pre-merge Contract Preview Slice
        (coordination.db WAL -> Atomic Leases, Staged Contracts, 2-Stage Pre-check)
-----------------------------------------------------------------------------
[VS-3] Executable Conventions & Structural Linter Slice
       (Tree-sitter Query Engine + Dual-tier Syntax Safety -> Conventions)
-----------------------------------------------------------------------------
[VS-4] Deterministic Test Contract & Verification Guard Slice
       (Code Impact Analysis + Staged Delta Hash & Read-Only Contract)
-----------------------------------------------------------------------------
[VS-5] Constitutional Discovery & Synthesis Slice
       (PackageManifest + CodeTopology Mining -> Invariant Proposal)
-----------------------------------------------------------------------------
[VS-6] Gradual Evolutionary Governance & Exemption Ratchet Slice
       (DMI Entropy Diagnostics + Irreversible Exemptions Ratchet)
=============================================================================
```

### 7.1 [VS-1] Topological Invariant Verification Slice

* **목적:** 의존성 그래프를 분석하여 계층화(Layering), 순환 참조 금지(Acyclicity), 은닉성(Deep Module) 규칙을 다계층 지연시간 예산(Fast Path p95 < 50ms) 내에 검증.

#### 1. Git 트리 해시 내용 주소 지정형 캐시 모델
공유 디스크 상의 가변 그래프를 직접 수정하던 기존 "Delta Hot-swap" 방식은 동시 실행되는 다중 워크트리 환경에서 그래프 오염, 경쟁 상태(Race Condition), 쓰기 파손(Torn Writes), 무상태성 위반을 유발하므로 완전 폐기합니다. 본 시스템은 Git의 머클 트리 해시를 기반으로 하는 **불변(Immutable) 내용 주소 지정형 캐시 모델**을 채택합니다.

```text
[ Git Worktree State ]
        │
        ▼
   git rev-parse HEAD^{tree}  ───► TreeHash (Merkle Tree ID)
        │
        ├──► Combine with SHA256(.vault-graph/invariants.yaml)
        ├──► Combine with EngineFingerprint (graph schema + parser versions)
        │
        ▼
   CacheKey = SHA256(TreeHash + ":" + InvariantsHash + ":" + EngineFingerprint)
        │
        ├──► Disk Cache: <graph-home>/cache/graphs/<CacheKey>.rx (IMMUTABLE, READ-ONLY)
        │
   [ In-Memory Ephemeral Overlay (Process-Private) ]
        │
        ├── 1. Read / mmap immutable base graph G_base
        ├── 2. Snapshot delta files ΔF to temp dir, hash snapshots
        ├── 3. Parse snapshot files via Tree-sitter
        ├── 4. Mutate edges in G_ephemeral only (Zero disk write)
        ├── 5. Run Global O(V+E) SCC & Topological Invariant Rules
        └── 6. Discard snapshots and G_ephemeral on process exit
```

1. **트리 해시 식별자 및 캐시 키 생성:**
   $$T_{\text{base}} = \texttt{git rev-parse HEAD\^{tree}}$$
   $$\text{CacheKey} = \text{SHA256}(T_{\text{base}} \parallel \text{":"} \parallel \text{SHA256}(\texttt{.vault-graph/invariants.yaml}) \parallel \text{":"} \parallel \text{EngineFingerprint})$$
   `EngineFingerprint` 예: `graph-schema-v3|ts-python-0.25.0|ts-dart-0.1.0|rustworkx-0.17|dmi-v1`. 파서·스키마·DMI 변경 시 상수를 올려 무효화합니다.
2. **불변 디스크 캐시 아티팩트 (`<graph-home>/cache/graphs/<CacheKey>.rx`):**
   - 베이스 트리의 직렬화된 구조 그래프(`rustworkx.PyDiGraph`)를 저장합니다.
   - `<CacheKey>.rx` 파일은 한 번 기록되면 영구히 수정되지 않습니다. 캐시 미스 발생 시 잠금 파일로 생성 리더 1개만 기록하고, 임시 파일(`<CacheKey>.tmp.<pid>`)에 기록한 뒤 `os.replace`로 원자 교체합니다. 나머지는 대기 후 판독만 합니다.
   - 여러 워크트리와 CLI/MCP 프로세스가 OS 페이지 캐시를 공유하며 병렬 판독합니다.
   - 30일 미사용 캐시는 정리합니다. 지연 예산은 캐시 적중·ΔF 10 이하·벤치 환경 명시 조건에서 측정합니다.
3. **프로세스 비공개 임시 인메모리 오버레이 ($G_{\text{ephemeral}}$):**
   - 에이전트가 스테이징된 변경 사항($\Delta F$)에 대해 검증을 요청할 때:
     1. 베이스 그래프 역직렬화: $G_{\text{base}} \leftarrow \text{deserialize}(\langle\text{CacheKey}\rangle\text{.rx})$
     2. ΔF 스냅샷 복사: 실시간 파일을 직접 파싱하지 않고 임시 스냅샷 디렉터리에 복사한 뒤 SHA256 해시를 기록합니다. 편집 중 파일로 인한 flakiness를 제거합니다.
     3. 프로세스 비공개 복제본 생성: $G_{\text{ephemeral}} = G_{\text{base}}.\text{copy}()$
     4. 스냅샷 기준 심볼 삭제 동기화:
        - 수정된 파일 $f \in \Delta F$를 재파싱한 결과 기존 $G_{\text{base}}$에 정의되어 있던 심볼 $S \in f$가 제거된 경우(심볼 삭제 또는 이름 변경), $G_{\text{ephemeral}}$ 상에서 해당 심볼 $S$를 향하는 모든 진입 엣지(Incoming Edges)를 즉시 제거하여 고아 노드로 인한 유령 폐로 탐색을 방지하며, 이를 고아 참조 진단(`DanglingReferenceWarning` 또는 strict 모드 시 `DanglingReferenceError`)으로 식별하여 검증 결과에 포함합니다.
     4. Tree-sitter로 스냅샷 파일만 증분 파싱하여 신규 심볼 및 의존성 엣지 추출
     5. $G_{\text{ephemeral}}$에 신규 엣지 삽입
     6. $G_{\text{ephemeral}}$ 상에서 글로벌 $O(V+E)$ SCC 순환 탐지 및 계층 규칙 검증 수행
     7. 검증 결과를 호출자에게 반환하고 스냅샷과 $G_{\text{ephemeral}}$을 즉시 소멸 (Zero Disk Write, 서브시스템 A 0바이트).

#### 2. 글로벌 $O(V+E)$ 순환 탐지 및 증분 도달 가능성 경로 분석

##### A. 2차 국소 영향 반경 검증의 수학적 결함 및 반례
기존의 "2차 영향 반경 서브그래프($G_{\Delta}$) 국소 검증"은 길이가 3 이상($N \ge 3$)인 순환 참조를 구조적으로 탐지하지 못하는 치명적 결함을 포함하고 있어 완전 삭제합니다.

**수학적 반례 증명 ($N = 3$ 순환 누락):**
1. 기존 비순환 그래프 $G$: $B \rightarrow C$, $C \rightarrow A$ 간선이 존재 ($B \rightarrow C \rightarrow A$).
2. 에이전트가 파일 $A$를 수정하여($\Delta F = \{A\}$) $A \rightarrow B$ 간선을 추가함.
3. 실제 그래프에는 길이 3인 순환 참조 $A \rightarrow B \rightarrow C \rightarrow A$가 발생함.
4. 만약 $A$의 2차 영향 반경(Hop $\le 2$)만 탐색할 경우:
   - $A$로부터 2-hop 전방 탐색은 $A \rightarrow B \rightarrow C$에서 종료됩니다.
   - 순환을 완성하는 간선인 $C \rightarrow A$는 3번째 홉에 위치하므로, 2-hop 국소 탐색은 $A$로 되돌아오는 폐로를 감지하지 못하고 검증을 잘못 통과(False Negative)시킵니다.

##### B. 글로벌 $O(V+E)$ SCC 검증 및 증분 도달 가능성 규약
1. **전역 강결합 컴포넌트 분석 (Global SCC Analysis):**
   - 타잔 알고리즘 기반 `rustworkx.strongly_connected_components` 사용 ($O(|V| + |E|)$).
   - 유효한 방향 비순환 그래프(DAG) 판정 기준:
     $$\forall \text{scc} \in \text{SCC}(G_{\text{ephemeral}}), \quad |\text{scc}| = 1 \quad \land \quad (v, v) \notin E$$
2. **표적 증분 도달 가능성 분석 및 순환 증거 추출:**
   - 신규 의존성 간선 $u \rightarrow v$ 유입 시, 기존 그래프에서 $v \rightsquigarrow u$ 유향 경로 존재 여부를 `rustworkx.has_path`로 즉시 판정.
   - 경로 존재 시 `rustworkx.dijkstra_shortest_paths`를 통해 최단 폐로 증거 시퀀스(`CycleWitness = [u, v, w_1, ..., w_k, u]`)를 추출하고 소스 위치가 명시된 `CircularDependencyError`를 패스트 페일(Fail-fast) 방출.
   - 도달 가능성 검사는 패스트 페일용이며, 최종 판정은 항상 전역 SCC로 확정합니다. 지연 예산은 벤치 환경 명시 조건에서 측정합니다.
3. **정적 타입 검사 전용 import 분기 식별 (`if TYPE_CHECKING:` Exclusion):**
   - 1차 범위는 리터럴 `if TYPE_CHECKING:`과 `if typing.TYPE_CHECKING:`만 제외하고 런타임 간선($E_{\text{runtime}}$)에서 분리합니다. 별칭(`as TC`)과 동적 가져오기는 제외하지 않습니다.
   - 순환 탐지는 $E_{\text{runtime}}$만을 대상으로 수행합니다. 지연 평가 가져오기로 인한 거짓 음성 가능성을 문서화합니다.

#### 3. 깊은 모듈 지수 ($DMI$: Deep Module Index) 수학적 정식화

DMI는 Tier 0 불변식이 아니라 Tier 2 조정 가능 정책입니다. 아래 상수는 `dmi-v1` 경험식이며, 프로젝트 헌법에서 임계값과 가중치를 재정의할 수 있습니다. Python과 Dart 가중치는 분리합니다(Python `self`·`cls` 제외 규칙은 Dart에 적용하지 않음).

$$DMI(M) = \frac{C_{\text{internal}}(M)}{S_{\text{interface}}(M) + 1}$$

1. **외부 공개 인터페이스 표면적 ($S_{\text{interface}}(M)$):**
   $$S_{\text{interface}}(M) = \sum_{s \in \mathcal{E}(M)} W_{\text{kind}}(s) \cdot \left( 1 + \alpha \cdot P(s) + \beta \cdot T(s) \right)$$
   - $W_{\text{kind}}(s)$: 클래스/프로토콜/타입=2.0, 함수/메서드=1.0, 전역상수/변수=0.5
   - $P(s)$: 매개변수 개수 (`self`, `cls` 제외), $T(s)$: 타입 시그니처 AST 노드 총합
   - $\alpha = 0.2$, $\beta = 0.1$
2. **내부 캡슐화 복잡도 ($C_{\text{internal}}(M)$):**
   $$C_{\text{internal}}(M) = \sum_{f \in \mathcal{F}(M)} \Big( v(f) + \gamma \cdot N_{\text{AST}}(f) \Big) + \lambda \cdot |\mathcal{I}(M)|$$
   - $v(f)$: 함수 $f$의 McCabe 순환 복잡도 (분기 노드 합산 + 1)
   - $N_{\text{AST}}(f)$: 본문 내부 AST 노드 총합 ($\gamma = 0.05$)
   - $|\mathcal{I}(M)|$: 은닉된 비공개 심볼 개수 ($\lambda = 2.0$: 캡슐화 보너스 가중치)
3. **운영 분류 임계값:**
   - **Shallow Module (얕은 모듈):** $DMI < 1.5$ (인터페이스 과대, 얇은 통과 계층 안티패턴)
   - **Balanced Module (균형 모듈):** $1.5 \le DMI < 4.0$ (표준 통과)
   - **Deep Module (깊은 모듈):** $DMI \ge 4.0$ (우수 모범 아키텍처)
4. **3대 특수 모듈 면제 규약:**
   - `DMI_EXEMPT_PROTOCOL`: 순수 프로토콜 및 ABC 모듈 (포트 인터페이스)
   - `DMI_EXEMPT_DTO`: 불변 데이터 전송 객체 모듈 (`@dataclass(frozen=True)`)
   - `DMI_EXEMPT_FACADE`: 패키지 루트 재수출 파사드 (`__init__.py`)

#### 4. 다계층 지연시간 예산 SLA (3-Tier Latency Budget SLA)

| 계층 (Tier) | 동작 조건 | 평가 범위 | 지연시간 목표 | 슬로우 패스 폴백 동작 |
| :--- | :--- | :--- | :--- | :--- |
| **Fast Path (상호작용형)** | 캐시 적중 상태에서 스테이징 변경분 검증 | $\Delta F \le 10$ 파일 | **p50 < 15ms<br>p95 < 50ms<br>p99 < 100ms** | 별도 폴백 불필요. 스냅샷 증분 파싱 및 인메모리 오버레이로 즉시 판정. 벤치 환경 명시 조건에서 측정. |
| **Warm Path (중규모 변경)** | 피처 브랜치 검증 또는 다중 파일 리팩토링 | $10 < \Delta F \le 50$ 파일 | **p95 < 250ms** | 250ms 초과 시 동기식 완결을 유지하고 진행 상태를 반환합니다. MCP 스트리밍 토큰은 별도 규격 확정 전까지 쓰지 않습니다. |
| **Slow Path (콜드 스타트 / 캐시 미스)** | 최초 저장소 인덱싱, 대규모 Git 리베이스, 캐시 부재 | 저장소 전체 / $> 50$ 파일 | **p95 < 3000ms** (10,000 심볼·벤치 환경 명시 기준) | 백그라운드 태스크 분리 및 `CacheRebuildingNotification` 이벤트 방출. 단, 5,000ms 초과 시 `VerificationTimeoutError`를 반환하며 프로세스를 안전 종료. |

---

### 7.2 [VS-2] Cross-Worktree Coordination & Pre-merge Contract Preview Slice
멀티 에이전트 환경에서 독립된 Git Worktree 간 파일 I/O 충돌을 방지하고, 원자적 임대(`SemanticLease`)와 프리머지 계약 선공개 및 2단계 사전 중첩 검증을 수행합니다. 생산자는 DB에만 기록하고 소비자가 자기 워크트리에 미리보기를 구체화합니다. (제5절 및 제6절 상세 규격 준수)

### 7.3 [VS-3] Executable Conventions & Structural Linter Slice
코딩 규약을 Tree-sitter 구문 패턴 쿼리로 기계적 집행하며, 이원화된 구문 오류 분류 체계를 적용합니다:
1. **Level 1 (드래프트 / 복구 가능 구문 오류):** 함수 내부 국소 오류이나 최상위 시그니처 추출이 가능한 경우, 비차단 경고(`SyntaxWarning`)와 함께 `status: "draft_advisory"`를 발급하여 에이전트 작업 흐름을 보장.
2. **Level 2 (치명적 / 구조적 구문 오류):** 최상위 문법 파괴, import 손상, 닫히지 않은 클래스, 또는 엄격 모드(`vg check --strict`, 커밋 전 훅, CI 게이트)에서 발생하는 오류는 즉시 `FatalSyntaxError`를 방출하고 검증을 차단.
* **규칙 정의:** 불변 데이터 클래스 강제(`@dataclass(frozen=True)`), 명시적 예외 상속 강제(`VaultGraphError` 하위 클래스), 엄격한 정적 타입 어노테이션(`Any` 금지).

### 7.4 [VS-4] Deterministic Test Contract & Verification Guard Slice
코드 수정 시 영향받는 인터페이스에 대해 필수적으로 통과해야 하는 최소 회귀 테스트 스위트를 역산출하고, 서브시스템 A 읽기 전용 검증 규약을 적용합니다:
1. **스냅샷 델타 해시 검증:** ΔF를 임시 스냅샷에 복사한 뒤 SHA256 해시를 기록하고 스냅샷만 파싱합니다. 실시간 파일 직접 대조로 인한 flakiness를 제거합니다. 검증 대상은 서브시스템 A 전체이며 `src/` 한정이 아닙니다.
2. **파일 디스크립터 읽기 전용 경계:** 정적 분석 코어는 소스 파일 접근 시 `mode="r"` 또는 `os.O_RDONLY` 플래그만을 사용하며, `tests/test_read_only_boundary.py`를 통해 검증 경로의 쓰기 호출 부재를 검사합니다. 다른 프로세스 쓰기까지 증명하지 않습니다.

### 7.5 [VS-5] Constitutional Discovery & Synthesis Slice
- **Greenfield Bootstrap:** 빌드 매니페스트(`pyproject.toml` 등) 분석을 통해 프로젝트 유형에 맞는 헌법 매니페스트(`.vault-graph/invariants.yaml`) 및 기본 테스트 스캐폴딩 자동 생성.
- **Brownfield Mining:** 디렉터리 간 호출 결합 행렬을 연산하여 자연 계층을 발견하고, 출처 라인이 첨부된 헌법 초안 반환.

### 7.6 [VS-6] Gradual Evolutionary Governance & Exemption Ratchet Slice
- **비가역적 면제 래칫:** 레거시 위반 사항은 `.vault-graph/exemptions.json`에 동결하여 초기 빌드를 허용하되, 리팩토링 시 `total_exemptions_ceiling`과 목록을 영구 하향(Ratchet Down) 조정하여 과거로의 회귀를 차단.
- **엔트로피 진단 및 DMI 연동:** 깊은 모듈 지수 공식($DMI(M) = \frac{C_{\text{internal}}(M)}{S_{\text{interface}}(M) + 1}$)을 기반으로 모듈 단위 DMI 점수를 연속 측정하여 얕은 모듈 경고 및 깊은 모듈 승격 진단.
- **질서 있는 헌법 개정:** 헌법 변경 시 각 규칙의 `rationale` 갱신을 의무화하고 Git 커밋 이력에 암호학적으로 기록.

---

## 8. Stateless MCP 및 CLI 인터페이스 명세 (Stateless MCP & CLI Interface Specification)

### 8.1 완전 무상태 MCP 아키텍처 및 3계층 전송 추상화 (Tri-Transport Architecture)

Vault Graph의 MCP 서버(`vg serve --mcp`)는 **무상태 프로세스(Stateless Process) + 지속성 조율 기판(Durable Coordination Substrate)** 구조로 설계됩니다. MCP 서버 프로세스는 메모리 세션 상태를 전혀 유지하지 않으며, 모든 에이전트 간 조율 상태는 서브시스템 B의 `coordination.db`(SQLite WAL) 트랜잭션을 통해 디스크에 보존됩니다.

이 구조는 Anthropic이 제안하고 최종 확정한 **SEP-2575 (2026-07-28 확정, Final: "Make MCP Stateless")** 및 **SEP-3182 (Request Idempotency in MCP)** 표준 규격에 완벽히 정합합니다:
1. **초기화 핸드셰이크 제거 (Zero-Handshake Execution):** 기존의 상태 유지형 `initialize` 및 `notifications/initialized` 양방향 세션 핸드셰이크를 전면 배제합니다. 클라이언트는 연결 즉시 도구를 호출하거나 `server/discover`를 통해 서버 역량을 단일 왕복으로 조회할 수 있습니다.
2. **요청 완결성 및 프로토콜 메타데이터 격리 (Request Completeness via `_meta`):** 모든 요청은 자체 완결적(self-contained)입니다. `client_request_id`, `idempotency_key`, `caller_identity`, `timeout_ms` 등 전송 제어 식별자는 비즈니스 인자(`arguments`)에 오염되지 않고, JSON-RPC 2.0 표준 확장 필드인 `params._meta`를 통해 전달됩니다. 실행 결과 메타데이터(`is_replayed`, `latency_ms`) 또한 `result._meta`에 격리 반환됩니다.
3. **3계층 전송 추상화 (Tri-Transport Support):**
   - **Streamlined HTTP 전송 (`--transport http --port 8120`):** SEP-2575가 표준화한 무상태 HTTP POST 기반 전송입니다. 복수의 독립적인 Git 워크트리와 자율 에이전트(Cursor, Claude Code, CI 컨테이너)가 단일 로컬 엔드포인트(`http://127.0.0.1:8120/mcp`)에 세션 없이 동시 접속합니다.
   - **무상태 Stdio 전송 (`--transport stdio`):** 단일 프로세스 파이프 환경을 지원하되, 각 JSON-RPC 프레임은 프로세스 메모리 상태에 의존하지 않는 독립 프레임으로 처리됩니다.
   - **CLI 직접 실행 브리지 (`vg mcp call <tool> '<json>'`):** 셸 스크립트, Git Hook, CI 파이프라인에서 백그라운드 데몬 구동 없이 동일한 도구 파이프라인과 멱등성 검증 엔진을 1회성 프로세스로 즉각 호출합니다.
4. **역량 발견 규약 (`server/discover`):** 세션 수립 없이 서버의 메타데이터, 지원 프로토콜 버전(`2026-07-28`), 멱등성 표준(`SEP-3182`), 도구 목록 및 불변성 엔진 안내 지침을 즉시 반환합니다.
5. **읽기/쓰기 트랜잭션 분리 원칙 (Read/Write Separation):** 불변식 조회 및 정적 검증 등 읽기 전용 도구는 멱등성 원장(`client_requests`) 쓰기 트랜잭션을 우회(Bypass)하여 SQLite WAL 쓰기 락 경합을 원천 차단함으로써 Fast Path SLA($p95 < 50\text{ms}$)를 보장합니다.

```text
  [ Multi-Agent Clients: Cursor / Claude Code / Codex / CI Runner ]
                 │
                 │ 1) Streamlined HTTP (POST /mcp)  [SEP-2575]
                 │ 2) Stateless Stdio (Framed Line JSON-RPC)
                 │ 3) Direct CLI Bridge (vg mcp call)
                 ▼
  +─────────────────────────────────────────────────────────────────────────+
  |                    Vault Graph MCP Dual Transport Layer                 |
  |   - StdioTransportAdapter (Local Subprocess Pipe)                       |
  |   - HttpTransportAdapter (Stateless Endpoint, Streamable HTTP POST)     |
  |   - CliBridgeAdapter (Direct Single-Invocation Execution)               |
  +─────────────────────────────────────────────────────────────────────────+
                                      │
                                      ▼ [Extract params._meta & params.arguments]
  +─────────────────────────────────────────────────────────────────────────+
  |                 StatelessMcpService (Protocol & Router)                 |
  |   - Dynamic Discovery: server/discover, tools/list                      |
  |   - SEP-3182 Idempotency Engine: RFC 8785 JCS SHA-256 Hashing          |
  +─────────────────────────────────────────────────────────────────────────+
         │                                                  │
         │ [Read-Only Zero-Mutation Bypass]                 │ [Durable Concurrency Writes]
         ▼                                                  ▼
  +──────────────────────────────────────+   +──────────────────────────────+
  | [서브시스템 A & Domain 1] 불변성 투영 |   | [서브시스템 B] 런타임 조율 저장소 |
  | - .vault-graph/invariants.yaml       |   | <graph-home>/run/<repo_hash>/|
  | - .vault-graph/exemptions.json       |   | coordination.db (SQLite WAL) |
  | - Tree-sitter AST & rustworkx Graph  |   | - client_requests (멱등성)    |
  | - O_RDONLY 불변 디스크 캐시 (.rx)    |   | - semantic_leases (시맨틱임대)|
  | - Context Pack & GraphRAG Impact     |   | - staged_contracts (프리머지) |
  | - Fast Path p95 < 50ms (Zero-Write)  |   | - wait_for_edges (교착 감시)  |
  +──────────────────────────────────────+   +──────────────────────────────+
                                      │
                                      ▼ [Format result.content & result._meta]
  +─────────────────────────────────────────────────────────────────────────+
  |    Deterministic JSON-RPC Response (result._meta.is_replayed 투명성)     |
  +─────────────────────────────────────────────────────────────────────────+
```

### 8.2 핵심 7대 표준 심층 MCP 도구 상세 규격 (`vg_*`)

모든 도구는 도구 이름 충돌을 방지하기 위해 `vg_` 접두사를 표준 적용하며, 프로토콜 메타데이터(`client_request_id`, `caller_identity`, `timeout_ms`)는 최상위 `params._meta`로 전달됩니다. 아래 명세의 입력 스키마는 순수한 비즈니스 도메인 인자(`arguments`)만을 정의합니다.

#### 1. `vg_get_invariants` (읽기 전용 / Subsystem D & A)
- **역할:** 활성화된 아키텍처 헌법 규칙(`.vault-graph/invariants.yaml`), 계층별 불변식 매니페스트, 면제 목록 및 잔여 면제 상한선(`exemptions.json`)을 조회합니다.
- **입력 (`arguments`):**
  ```json
  {
    "type": "object",
    "properties": {
      "rule_category": { "type": "string", "enum": ["topology", "convention", "all"], "default": "all" },
      "scope_path": { "type": "string", "description": "특정 하위 디렉터리 또는 모듈 범위 한정 시 지정" },
      "include_exemptions": { "type": "boolean", "default": true }
    }
  }
  ```
- **출력 (`result`):**
  ```json
  {
    "constitution_version": "1.0.0",
    "constitution_hash": "sha256-4b825dc642cb6eb9a060e54bf8d69288fbee4904",
    "rules": [
      {
        "id": "RULE-LAYER-01",
        "name": "Strict Layering",
        "source_layer": "adapters",
        "forbidden_target": "domain",
        "severity": "fail_closed"
      }
    ],
    "exemptions_count": 2,
    "exemptions_ceiling": 2,
    "ratchet_status": "enforced"
  }
  ```

#### 2. `vg_verify_topology` (읽기 전용 / Subsystem A Static Analysis Engine)
- **역할:** 작업 트리 또는 스테이징된 변경분의 Tree-sitter AST 및 유향 그래프를 분석하여 $O(V+E)$ 복잡도 내에서 계층 경계 위배, 순환 의존성(Tarjan SCC), 코딩 규약 준수 여부, 깊은 모듈 지수($DMI$)를 결정론적으로 검증합니다.
- **입력 (`arguments`):**
  ```json
  {
    "type": "object",
    "required": ["worktree_path"],
    "properties": {
      "worktree_path": { "type": "string" },
      "staged_only": { "type": "boolean", "default": true },
      "target_paths": { "type": "array", "items": { "type": "string" } },
      "mode": { "type": "string", "enum": ["draft", "strict"], "default": "draft" }
    }
  }
  ```
- **출력 (`result`):**
  ```json
  {
    "status": "passed | advisory | violated",
    "evaluated_commit": "4b825dc642cb6eb9a060e54bf8d69288fbee4904",
    "delta_hash": "sha256-e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "violations": [],
    "warnings": [],
    "deep_module_metrics": {
      "average_dmi": 4.25,
      "shallow_modules_flagged": []
    }
  }
  ```

#### 3. `vg_acquire_lease` (상태 변경 멱등성 보장 / Subsystem B Coordination Store)
- **역할:** 특정 심볼 및 1-hop 폭발 반경(Blast Radius)에 대해 원자적 시맨틱 임대를 획득(`acquire`), 갱신(`renew`), 또는 해제(`release`)합니다.
- **입력 (`arguments`):**
  ```json
  {
    "type": "object",
    "required": ["action", "worktree_path", "target_symbol"],
    "properties": {
      "action": { "type": "string", "enum": ["acquire", "renew", "release"], "default": "acquire" },
      "worktree_path": { "type": "string" },
      "target_symbol": { "type": "string" },
      "intent_summary": { "type": "string", "description": "acquire 액션 수행 시 필수" },
      "lease_duration_seconds": { "type": "number", "default": 300.0 },
      "lease_id": { "type": "string", "description": "renew 또는 release 액션 수행 시 필수" }
    }
  }
  ```
- **출력 (`result`):**
  ```json
  {
    "status": "granted | renewed | released | conflict",
    "lease_id": "lease-f47ac10b-58cc-4372-a567-0e02b2c3d479",
    "target_symbol": "src/auth/service.py:AuthService.login",
    "blast_radius_symbols": [
      "src/auth/service.py:AuthService.login",
      "src/api/routes.py:login_route"
    ],
    "conflict_details": null,
    "expires_at": 1757153100.0
  }
  ```

#### 4. `vg_register_premerge_contract` (상태 변경 멱등성 보장 / Subsystem B & C)
- **역할:** 상류 에이전트(Producer)가 변경 예정인 인터페이스 시그니처 AST 및 무결성 SHA-256 해시를 `coordination.db`에 등록(`stage`)하거나, 하류 에이전트(Consumer)가 등록된 계약 목록을 조회(`query`)합니다. 생산자는 DB 기록만 수행하며 타 워크트리에 파일을 직접 쓰지 않습니다.
- **입력 (`arguments`):**
  ```json
  {
    "type": "object",
    "required": ["action", "worktree_path", "symbol_id"],
    "properties": {
      "action": { "type": "string", "enum": ["stage", "query"], "default": "stage" },
      "worktree_path": { "type": "string" },
      "symbol_id": { "type": "string" },
      "signature_ast_json": { "type": "string", "description": "stage 액션 수행 시 필수" },
      "type_stub_content": { "type": "string", "description": "선택적 타입 스텁 본문" }
    }
  }
  ```
- **출력 (`result`):**
  ```json
  {
    "status": "staged | query_result",
    "contract_id": "contract-7c9e6679-7425-40de-944b-e07fc1f90ae7",
    "symbol_id": "src/auth/service.py:AuthService.login",
    "sha256_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "preview_content": "string (소비자 워크트리 구체화용 8줄 무결성 헤더 포함 .pyi 코드)",
    "staged_at": 1757152800.0
  }
  ```

#### 5. `vg_check_premerge_overlap` (읽기 전용 / Subsystem B & A Pre-merge Pre-check)
- **역할:** 머지 전에 두 워크트리 간 2단계 사전 중첩 검증(1단계: Git merge-base 텍스트 충돌, 2단계: 휘발성 인메모리 결합 오버레이 $G_{\text{premerge}} = G_{\text{base}} \oplus \Delta_A \oplus \Delta_B$ 아키텍처 및 타입 정합성)을 수행합니다.
- **입력 (`arguments`):**
  ```json
  {
    "type": "object",
    "required": ["producer_worktree_path", "consumer_worktree_path"],
    "properties": {
      "producer_worktree_path": { "type": "string" },
      "consumer_worktree_path": { "type": "string" },
      "target_contract_id": { "type": "string" }
    }
  }
  ```
- **출력 (`result`):**
  ```json
  {
    "is_compatible": true,
    "text_conflicts": [],
    "invariant_violations": [],
    "type_mismatches": [],
    "evaluated_base_tree": "7a9f2c1e8d4b825dc642cb6eb9a060e54bf8d692"
  }
  ```

#### 6. `vg_query_impact` (읽기 전용 / Subsystem A Graph Analysis)
- **역할:** 특정 심볼이나 모듈의 변경이 초래하는 역방향 의존성 폭발 반경(Upstream Blast Radius), 전이 호출 경로, 필수 재실행 회귀 테스트 스위트, 모듈의 깊은 모듈 지수($DMI$)를 산출합니다. 문서를 코드와 억지로 바인딩하지 않으며 순수 코드 위상에만 집중합니다.
- **입력 (`arguments`):**
  ```json
  {
    "type": "object",
    "required": ["target_symbols"],
    "properties": {
      "target_symbols": { "type": "array", "items": { "type": "string" } },
      "worktree_path": { "type": "string" },
      "max_depth": { "type": "integer", "default": 3 },
      "include_tests": { "type": "boolean", "default": true }
    }
  }
  ```
- **출력 (`result`):**
  ```json
  {
    "affected_symbols_count": 14,
    "blast_radius": [
      {
        "symbol": "src/api/routes.py:login_route",
        "depth": 1,
        "call_type": "direct_call"
      }
    ],
    "suggested_verification_suites": [
      "tests/test_auth.py",
      "tests/test_api_routes.py"
    ],
    "deep_module_metrics": {
      "symbol_id": "src/auth/service.py:AuthService",
      "dmi": 4.5,
      "classification": "deep"
    }
  }
  ```

#### 7. `vg_get_context_pack` (읽기 전용 / Evidence-First Context Pack)
- **역할:** 특정 작업 및 심볼 영역에 대해 결정적 증거(관련 불변식 규칙, 심볼 AST 인터페이스 스텁, 위상 의존 관계)만을 압축한 토큰 효율적 컨텍스트 팩(`context-pack-v1`)을 조립하여 제공합니다.
- **입력 (`arguments`):**
  ```json
  {
    "type": "object",
    "required": ["goal"],
    "properties": {
      "goal": { "type": "string" },
      "target_symbols": { "type": "array", "items": { "type": "string" } },
      "worktree_path": { "type": "string" },
      "token_budget": { "type": "integer", "default": 4000 }
    }
  }
  ```
- **출력 (`result`):**
  ```json
  {
    "context_pack_schema_version": "context-pack-v1",
    "pack_id": "sha256-a665a45920422f9d417e4867efdc4fb8a04a1f3fff1fa07e998e86f7f7a27ae3",
    "goal": "Refactor AuthService login to support JWT refresh",
    "invariants_block": {
      "mandatory_rules": ["RULE-LAYER-01", "RULE-NO-CYCLE"],
      "exemption_status": "none"
    },
    "contract_stubs": [
      {
        "symbol_id": "src/auth/service.py:AuthService.login",
        "stub_content": "def login(credentials: AuthCredentials) -> AuthToken: ..."
      }
    ],
    "total_tokens": 1250,
    "is_truncated": false
  }
  ```

### 8.3 역량 발견 규약 (`server/discover`) 명세

SEP-2575에 따라 클라이언트가 연결 수립 직후 단일 왕복으로 서버 역량을 질의하는 표준 엔드포인트입니다:

* **RPC Method:** `server/discover`
* **요청:** `{ "jsonrpc": "2.0", "id": 1, "method": "server/discover", "params": {} }`
* **응답 (`result`):**
  ```json
  {
    "server_info": {
      "name": "vault-graph",
      "version": "5.1.0",
      "protocol_version": "2026-07-28"
    },
    "capabilities": {
      "stateless": true,
      "idempotency_standard": "SEP-3182",
      "tools": { "list_changed": false },
      "prompts": { "list_changed": false }
    },
    "tools": [
      { "name": "vg_get_invariants", "description": "아키텍처 헌법 및 면제 목록 조회" },
      { "name": "vg_verify_topology", "description": "증분 AST 위상 및 순환 참조, 규약 검증" },
      { "name": "vg_acquire_lease", "description": "시맨틱 임대 획득, 갱신, 해제 통합 관리" },
      { "name": "vg_register_premerge_contract", "description": "프리머지 인터페이스 시그니처 계약 등록 및 조회" },
      { "name": "vg_check_premerge_overlap", "description": "2단계 프리머지 사전 충돌 및 결합 오버레이 검증" },
      { "name": "vg_query_impact", "description": "정적 역방향 의존성 폭발 반경, 테스트, DMI 분석" },
      { "name": "vg_get_context_pack", "description": "최소 증거 기반의 토큰 효율적 구조화 컨텍스트 팩 발행" }
    ]
  }
  ```

### 8.4 5단계 클라이언트 요청 멱등성 실행 알고리즘 (Python 참조 구현체)

```python
import json
import random
import sqlite3
import time
from typing import Any, Callable, Dict, Optional

# SEP-3182 표준 JSON-RPC 오류 코드 정의
RPC_INVALID_REQUEST = -32600
RPC_INTERNAL_ERROR = -32603
RPC_IDEMPOTENCY_MISMATCH = -32001
RPC_IDEMPOTENCY_IN_PROGRESS = -32002

class McpRpcError(Exception):
    def __init__(self, code: int, message: str, data: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data or {}

class CoordinationLockTimeoutError(Exception):
    pass

def execute_with_deduplication(
    conn: sqlite3.Connection,
    meta: Dict[str, Any],
    tool_name: str,
    arguments: Dict[str, Any],
    payload_hash: str,
    handler_fn: Callable[[sqlite3.Cursor, Dict[str, Any]], Dict[str, Any]],
    is_mutating: bool = True,
) -> Dict[str, Any]:
    """
    SEP-2575 및 SEP-3182 표준을 완벽히 준수하는 5단계 멱등성 실행 엔진
    """
    start_time = time.time()

    # 프로토콜 제어 메타데이터 추출 (params._meta)
    client_request_id = meta.get("client_request_id")
    caller_identity = meta.get("caller_identity", "anonymous-agent")
    timeout_ms = float(meta.get("timeout_ms", 5000.0))

    # 읽기 전용 도구는 WAL 쓰기 락 경합을 방지하기 위해 멱등성 원장 쓰기 우회
    if not is_mutating or not client_request_id:
        cursor = conn.cursor()
        business_result = handler_fn(cursor, arguments)
        latency_ms = (time.time() - start_time) * 1000.0
        return {
            "content": business_result,
            "_meta": {
                "is_replayed": False,
                "latency_ms": round(latency_ms, 2),
            },
        }

    # Autocommit 강제 (드라이버 레벨 암묵적 트랜잭션 충돌 방지)
    conn.isolation_level = None
    cursor = conn.cursor()

    # 1. 5회 지수 백오프 및 무작위 지터를 적용한 즉시 쓰기 락 선점 루프
    deadline = start_time + (timeout_ms / 1000.0)
    retries = 0
    max_retries = 5
    base_delay = 0.05
    acquired_lock = False

    while time.time() < deadline:
        try:
            cursor.execute("BEGIN IMMEDIATE")
            acquired_lock = True
            break
        except sqlite3.OperationalError as err:
            err_msg = str(err).lower()
            if "locked" in err_msg or "busy" in err_msg:
                retries += 1
                if retries > max_retries:
                    break
                jitter = random.uniform(0.8, 1.2)
                sleep_time = min(base_delay * (1.5 ** (retries - 1)) * jitter, max(0.0, deadline - time.time()))
                if sleep_time > 0:
                    time.sleep(sleep_time)
            else:
                raise McpRpcError(code=RPC_INTERNAL_ERROR, message=f"데이터베이스 오류: {str(err)}") from err

    if not acquired_lock:
        raise CoordinationLockTimeoutError(
            f"요청 {client_request_id}에 대한 조율 잠금 선점에 실패했습니다 (제한 시간: {timeout_ms}ms)."
        )

    try:
        now = time.time()
        cursor.execute(
            """
            SELECT status, response_json, updated_at, request_payload_hash
            FROM client_requests
            WHERE client_request_id = ?
            """,
            (client_request_id,),
        )
        row = cursor.fetchone()

        # 2. 기등록된 요청 대조 및 재생 판정 (Fail-closed)
        if row is not None:
            status, cached_response, updated_at, stored_hash = row

            if stored_hash != payload_hash:
                cursor.execute("ROLLBACK")
                raise McpRpcError(
                    code=RPC_IDEMPOTENCY_MISMATCH,
                    message=f"Request {client_request_id} payload mismatch: expected {stored_hash}, got {payload_hash}",
                    data={"client_request_id": client_request_id},
                )

            if status == "completed" and cached_response:
                cursor.execute("ROLLBACK")
                replayed_content = json.loads(cached_response)
                total_latency = (time.time() - start_time) * 1000.0
                return {
                    "content": replayed_content,
                    "_meta": {
                        "is_replayed": True,
                        "latency_ms": round(total_latency, 2),
                    },
                }

            in_progress_threshold = (timeout_ms / 1000.0) * 1.5
            if status == "in_progress" and (now - updated_at) < in_progress_threshold:
                cursor.execute("ROLLBACK")
                raise McpRpcError(
                    code=RPC_IDEMPOTENCY_IN_PROGRESS,
                    message=f"Request {client_request_id} is already in progress by {caller_identity}",
                    data={"client_request_id": client_request_id, "retry_after_ms": 200},
                )

            if status == "failed":
                cursor.execute("ROLLBACK")
                raise McpRpcError(
                    code=RPC_INTERNAL_ERROR,
                    message=f"Request {client_request_id} previously failed deterministically",
                    data={"client_request_id": client_request_id, "failure_recorded": True},
                )

        # 3. 요청 접수 및 in_progress 상태 선점 기록
        if row is None:
            cursor.execute(
                """
                INSERT INTO client_requests (
                    client_request_id, command, agent_id, request_payload_hash,
                    response_json, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, NULL, 'in_progress', ?, ?)
                """,
                (client_request_id, tool_name, caller_identity, payload_hash, now, now),
            )
        else:
            cursor.execute(
                """
                UPDATE client_requests
                SET status = 'in_progress', agent_id = ?, updated_at = ?
                WHERE client_request_id = ?
                """,
                (caller_identity, now, client_request_id),
            )

        # 4. 도구 핸들러 비즈니스 로직 실행
        business_result = handler_fn(cursor, arguments)

        finish_time = time.time()
        cursor.execute(
            """
            UPDATE client_requests
            SET response_json = ?, status = 'completed', updated_at = ?
            WHERE client_request_id = ?
            """,
            (json.dumps(business_result), finish_time, client_request_id),
        )
        cursor.execute("COMMIT")

        latency_ms = (finish_time - start_time) * 1000.0
        return {
            "content": business_result,
            "_meta": {
                "is_replayed": False,
                "latency_ms": round(latency_ms, 2),
            },
        }

    except McpRpcError:
        try:
            cursor.execute("ROLLBACK")
        except Exception:
            pass
        raise
    except Exception as exc:
        # 5. 실패 시 비즈니스 쓰기 롤백 후 원자적 Upsert로 실패 상태 기록
        try:
            cursor.execute("ROLLBACK")
        except Exception:
            pass

        try:
            cursor.execute("BEGIN IMMEDIATE")
            fail_time = time.time()
            error_payload = json.dumps({"error_type": type(exc).__name__, "error_message": str(exc)})
            cursor.execute(
                """
                INSERT INTO client_requests (
                    client_request_id, command, agent_id, request_payload_hash,
                    response_json, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, 'failed', ?, ?)
                ON CONFLICT(client_request_id) DO UPDATE SET
                    status = 'failed',
                    response_json = excluded.response_json,
                    updated_at = excluded.updated_at
                """,
                (client_request_id, tool_name, caller_identity, payload_hash, error_payload, fail_time, fail_time),
            )
            cursor.execute("COMMIT")
        except Exception:
            try:
                cursor.execute("ROLLBACK")
            except Exception:
                pass

        raise McpRpcError(
            code=RPC_INTERNAL_ERROR,
            message=f"도구 실행 중 내부 오류가 발생했습니다: {str(exc)}",
            data={"client_request_id": client_request_id},
        ) from exc
```

### 8.5 인간 중심 CLI 인터페이스 및 대칭적 도메인 매핑 (Symmetric Dual-Adapter)

CLI 인터페이스(`vg`)와 무상태 MCP 서버(`vg serve --mcp`)는 동일한 서브시스템 코어(A, B, C, D)의 도메인 서비스를 호출하는 대칭적 어댑터 쌍(Symmetric Adapters)입니다. CLI는 인간 엔지니어와 CI 파이프라인의 명령행 인자 및 표준 입출력을 담당하고, MCP는 AI 자율 에이전트의 JSON-RPC 무상태 프로토콜을 담당합니다:

| CLI 명령어 | 매개변수 | 대응하는 MCP 도구 및 서브시스템 | 설명 |
| :--- | :--- | :--- | :--- |
| `vg serve --mcp` | `[--transport stdio\|http] [--port <port>] [--host <host>]` | MCP Server Core (Stateless Adapter) | SEP-2575 준수 무상태 MCP 서버 기동 (기본: stdio, HTTP 지정 시 분산 서버리스 모드) |
| `vg mcp call` | `<tool_name> '<args_json>' [--meta '<meta_json>']` | Core Dispatcher Direct Bridge | 백그라운드 데몬 없이 셸 및 CI 환경에서 무상태 MCP 도구를 1회성으로 직접 호출 |
| `vg mcp discover` | `[--json]` | `server/discover` Endpoint | 무상태 `server/discover` 엔드포인트를 호출하여 노출된 도구 및 스키마, 기능 플래그 확인 |
| `vg constitution init` | `[--profile <name>]` | `vg_get_invariants` (Subsystem D) | 신규 프로젝트 헌법 제안 및 `.vault-graph/invariants.yaml` 스캐폴딩 생성 |
| `vg constitution draft` | `--discover` | `vg_get_invariants` (Subsystem D) | 기존 코드 정적 분석 마이닝 기반 맞춤형 헌법(`.vault-graph/invariants.yaml`) 초안 자동 추출 |
| `vg exemption capture` | `[--output <path>]` | `vg_get_invariants` (Subsystem D) | 현재 존재하는 아키텍처 위반 사항을 `.vault-graph/exemptions.json`으로 동결 수집 |
| `vg exemption ratchet` | `[--clean] [--dry-run]` | Subsystem D (Git 연동) | 위반이 해소된 면제 항목을 정리하고 `total_exemptions_ceiling`을 현재 위반 개수로 영구 하향 |
| `vg check` | `[--staged] [--strict] [--timeout-ms <ms>]` | `vg_verify_topology` (Subsystem A) | 증분 델타 엔진 기반 아키텍처 불변식 검증 (Fast Path p95 < 50ms, Level 1 드래프트 권고 vs Level 2 Fail-closed 차단) |
| `vg constitution audit` | `[--json]` | `vg_query_impact` (Subsystem A) | 엔트로피, 결합도, 깊은 모듈 지수($DMI = \frac{C_{\text{internal}}}{S_{\text{interface}} + 1}$) 산출 및 아키텍처 승격 진단 ($DMI < 1.5$ 얕은 모듈 경고, $DMI \ge 4.0$ 깊은 모듈 승격) |
| `vg constitution amend` | `--rule <id> --rationale <text>` | Subsystem D (Git 연동) | 사유(`rationale`)를 명시하여 헌법 규칙 개정 (Git 커밋 연동) |
| `vg exemption ceiling raise` | `--reason <text> --expiry <date>` | Subsystem D (Git 연동) | 면제 상한 예외 상향 (별도 Git 커밋 필수, CI는 상향 커밋 없는 증가 차단) |
| `vg pack` | `--goal <text> [--symbols <list>]` | `vg_get_context_pack` (Subsystem A) | 특정 목표에 대한 최소 증거 블록 기반의 압축된 토큰 효율적 컨텍스트 팩 발행 |
| `vg clean --previews` | `[--worktree <path>]` | Subsystem C (파일 정리) | 만료되거나 머지 완료된 프리머지 계약 미리보기(`.vault-graph/premerge_contract_previews/*.pyi`) 일괄 정리 |
| `vg maintenance prune` | `[--older-than <days>]` | Subsystem B (원장 정리) | 완료 30일 경과 `client_requests` 원장 행 및 미사용 그래프 캐시(`.rx`) 일괄 정리 |
| `vg doctor` | `[--json]` | Subsystem B & A 진단 | SQLite WAL 조율 원장 무결성, 활성 임대 수, WFG 의존 간선 수, 캐시 적중률 및 검증 지연 진단 |

---

## 9. Evolutionary Migration, Pruning & Verification Invariants

### 9.1 점진적 어댑터 마이그레이션 로드맵 (Phase 1 ~ Phase 3)
1. **1단계: 공존 단계 (Phase 1: Coexistence)**
   - 소프트웨어 아키텍처 불변성 엔진을 기존 Vault Graph 인덱싱 및 검색 모듈과 병행 구동.
   - 테스트 베이스라인: 수집 1,188개 기준, failures=0, errors=0. 조건부 스모크 1건의 스킵만 허용.
   - 불변성 엔진 가져오기 그래프는 Chroma·FastEmbed를 직접 참조하지 않습니다. Vault 어댑터 진입점에서만 지연 로딩합니다.
2. **2단계: 포트-어댑터 분리 단계 (Phase 2: Decoupled Ports/Adapters)**
   - 자연어 답변 합성(`vault_graph.answer.*`) 및 프롬프트 합성(`mcp_prompts.py`) 모듈을 플러그형 어댑터 인터페이스 뒤로 분리.
   - 코어 불변성 엔진은 순수 정적 분석(Zero-Write AST/DAG)으로 독립하며, 기존 테스트는 어댑터 계약 테스트로 안전하게 이관.
3. **3단계: 저장소 자체 완결형 기본값 단계 (Phase 3: Repo-Native Default)**
   - 단일 Git 저장소 자체 완결형 아키텍처 검증이 기본 동작 모드로 정착.
   - 외부 Vault 및 LLM 답변 합성 기능은 선택적 확장 플러그인 어댑터로 강등되어 기존 사용자의 하위 호환성을 완벽히 보장.

### 9.2 폐기 및 정리 대상 요소 (Pruned Elements)
* **추측성 분산 DB 및 Web UI 백로그 정리:** Postgres, Neo4j, Qdrant, Web UI 등 외부 인프라 의존성을 코어에서 분리하고 로컬 rustworkx 및 SQLite WAL 단일 프로세스로 수렴합니다. Phase 1에서 Chroma는 Vault 어댑터 뒤에 유지되며, Phase 3에서 선택적 플러그인으로 강등됩니다.
* **상태 유지형 데몬 메모리 락 폐기:** 프로세스 재시작 시 유실되는 메모리 세션 락을 전면 폐기하고 디스크 기반 `coordination.db` 트랜잭션으로 단일화.
* **중복 YAML 패치 원장 폐기:** `.vault-graph/patches/`의 이중 YAML 기록을 배제하고 Git 머클 트리 커밋 히스토리와 `docs/PATCH_LOG.md`로 일원화.

### 9.3 6대 결정론적 차단 게이트 (Hard CI Failure Gates)
1. **[GATE-1] Zero Test Regression Gate (테스트 무회귀 게이트):**
   - 수집 1,188개 기준(`uv run pytest --collect-only -q`), failures=0, errors=0. 조건부 스모크 1건의 스킵만 허용.
2. **[GATE-2] Invariant Enforcement Gate (헌법 불변식 게이트):**
   - `vg check --staged` 실행 시 헌법 매니페스트(`.vault-graph/invariants.yaml`) 위반 0건 (`exemptions.json` 제외). 이 중 순환 의존성 위반은 GATE-6의 전역 $O(V+E)$ SCC 수학적 확정판과 함께 검증된다 — GATE-2는 선언된 정책과의 대조를, GATE-6은 수학적 최종 판정을 담당한다.
3. **[GATE-3] Exemption Ceiling Ratchet Gate (면제 상한 래칫 게이트):**
   - `len(exemptions) <= total_exemptions_ceiling` 불변식 강제. 하향은 항상 허용. 상향은 `vg exemption ceiling raise` 별도 커밋이 있을 때만 허용.
4. **[GATE-4] Zero-Mutation Boundary Gate (서브시스템 A 불변 게이트):**
   - 서브시스템 A(`src/`, `tests/`, `invariants.yaml`, `exemptions.json`의 무단 변경 없음) 0바이트 쓰기 보증. ΔF 스냅샷 해시 검증 및 `os.O_RDONLY` 강제. C 미리보기 경로와 D 명시 명령은 예외.
5. **[GATE-5] Fail-Closed Syntax Safety Gate (구문 오류 안전 게이트):**
   - 커밋 및 CI 대상 파일의 치명적 Level 2 구문 오류 존재 시 빌드 즉시 차단.
6. **[GATE-6] Acyclic Dependency Gate (전역 비순환 의존성 게이트):**
   - 전체 의존성 그래프에 대한 $O(V+E)$ 강결합 컴포넌트(SCC) 연산 결과, 비자명 컴포넌트($|V_{\text{scc}}| \ge 2$) 및 자기 루프 0건. 이 판정은 GATE-2에서 선언된 `no-circular-dependencies` 규칙의 수학적 최종 판정으로 기능한다.

### 9.4 4대 통계적 성능 예산 목표 (Performance Benchmark Targets)

#### Tier 1 원형 프로파일별 차등 규칙 (예시)
아래는 각 Tier 1 프로파일이 Tier 0 절대 불변식을 계승하면서 구체화하는 차등 규칙의 최소 예시입니다. 이 예시는 설명 목적의 주석이며, `.vault-graph/invariants.yaml` 스키마를 변경하지 않습니다. 실제 차등 정의는 해당 프로젝트의 Tier 2 헌법이 확정합니다.

| Tier 1 프로파일 | Tier 0 계승 | Tier 1 차등 규칙 (예시) | 비고 |
|---|---|---|---|
| `minimal-script` | 순환 금지, 읽기 전용 경계 | 레이어 규칙 미적용(또는 순환 금지만 적용), DMI 미적용 | 소형 스크립트·단일 목적 도구 |
| `modular-monolith` | 순환 금지, 읽기 전용 경계 | 단방향 레이어 1~2계층, DMI 기본 임계값 적용 | 모노리스 모듈 구조 |
| `clean-hexagonal` | 순환 금지, 읽기 전용 경계 | 포트/어댑터 방향의 엄격한 단방향 계층, DMI 엄격 적용 | 육각형·클린 아키텍처 계열 |
| `client-mobile` | 순환 금지, 읽기 전용 경계 | 플랫폼 격리 계층, 순환 금지, DMI 적용 | 클라이언트·모바일 계열 |

아래 수치는 벤치 환경 명시 조건에서의 기준값이며, 하드 CI 차단 게이트가 아닙니다. 측정 스크립트와 하드웨어 기준을 함께 기록합니다.

1. **[TARGET-1] Incremental Verification Latency:** 10,000개 심볼 규모에서 스테이징 델타($\Delta F \le 10$, 캐시 적중) 검증 시간 **p50 < 15ms, p95 < 50ms, p99 < 100ms**.
2. **[TARGET-2] Exemption Parsing Latency:** `.vault-graph/exemptions.json` 파싱 및 래칫 상한 검증 시간 **p99 < 1ms** 유지.
3. **[TARGET-3] Graph Cache Deserialization Latency:** 엔진 지문 포함 직렬화 캐시(`<CacheKey>.rx`) 역직렬화 시간 **p95 < 5ms**.
4. **[TARGET-4] SQLite WAL Concurrency Latency:** 동시성 경합 상태에서 임대 및 계약 트랜잭션 응답 시간 **p95 < 10ms** 목표 (요청별 절대 마감 5,000ms).

### 9.5 1,188개 테스트 베이스라인 무회귀 보증
본 명세의 모든 구현과 리팩토링은 **수집 시점의 테스트 베이스라인**을 회귀 없음의 기준선으로 유지한다. 수집 시점 기준선은 `uv run pytest --collect-only -q`로 수집한 전체 테스트 스위트에서 failures=0, errors=0(조건부 스모크 1건의 스킵만 허용)을 충족한 시점의 스냅샷이며, 그 개수는 수집 시점의 집합 크기를 반영한다. 기준선의 상세(선택 시점, pytest 실행 환경, 스킵된 조건부 스모크 식별)는 `docs/DECISIONS.md`에 기록한다.

이후 테스트가 추가되거나 제거될 수 있으며, 이 경우 GATE-1은 "해당 시점의 전체 스위트에서 failures=0, errors=0"으로 재운용한다. 즉 "1,188개"는 불변 상수라기보다 기준일 시점의 집합을 지칭하며, **어느 시점의 전체 스위트에서도 regressions-free가 유지되어야 한다는 조건이 본 명세의 불변입니다.**

### 9.6 기존 Context Pack 호환성 계약 (Phase 1 Coexistence Contract)

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

## 10. Independent Graph Search Design Proposal

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


## 11. Independent Graph Document Design Proposal

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
