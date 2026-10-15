# 현재 구현 아키텍처

이 문서는 현재 소스의 위치·책임·의존 규칙을 정한다. [SPEC.md](SPEC.md)는 활성 제품 계약이며 불변성 엔진과 조정 저장소의 향후 구현도 포함한다. 이 문서의 `engine`은 이미 구현된 일반 패키지 5개의 논리적 분류이다. `vault_graph.invariants`나 새 `engine/` 디렉터리의 구현을 뜻하지 않는다.

## 1. 소스 구조와 소유권

아래 경로는 `src/vault_graph/` 기준이다. 그룹은 실제 디렉터리이며 배포 단위는 아니다. M 번호는 [승인된 모듈 명세](design/specs/2026-10-15-vault-graph-modular-architecture-ko.md)의 책임을 유지한다.

```text
src/vault_graph/
├── indexing/                 # 색인 실행·계획·반영
│   ├── ingestion/           # 원본 읽기·정규화·청크
│   ├── extraction/          # 명시적 엔터티·관계 추출
│   ├── publication/         # Vault 투영 세대 발행
│   ├── index_service.py
│   ├── metadata_indexer.py
│   ├── vector_indexer.py    # 기존 공개 경로를 보존하는 호환 진입점
│   ├── vector_index_adapter.py # 실제 Vault 전용 벡터 색인 구현
│   ├── graph_indexer.py
│   └── revision_planner.py
├── retrieval/
│   ├── search/              # 후보 결합·순위·검색 응답
│   ├── graph/               # 그래프 계약·조회
│   │   └── projection/      # 일반 그래프 검색으로 변환·투영
│   ├── evidence/            # 검색 대상과 근거의 양방향 연결
│   └── explanation/         # 결과 이유·임시 설명 캐시
├── context/
│   ├── pack/                # 근거 선택·예산·문맥 팩
│   ├── memory/              # 파생 기억 조회
│   └── answer/              # 발췌 답변·인용 검증
├── project/
│   ├── code/                # 코드 투영·심볼·호출·영향 조회
│   └── context/             # 코드·Vault 근거 조합
├── operation/
│   ├── scope/               # 등록·범위·경로 보호
│   ├── readiness/           # 조회 전제 판정
│   ├── diagnostics/         # 상태·위생·진단 설명
│   ├── runtime/             # setup·watch·자원 종료
│   └── integration/         # 명시적 연동 설정·지침 관리
│       ├── mcp/             # MCP 설정 파일 생성·등록
│       ├── harness/         # 지침 설치·제거
│       └── project_binding_catalog.py
├── interface/
│   ├── cli/
│   ├── mcp/
│   ├── http/
│   └── composition/         # 구체 구현 생성·주입·자원 수명
│       └── adapters/        # 제공자 구성·기존 생성자의 기본 구성
├── storage/
│   ├── interfaces/          # 저장소·임베딩 계약
│   └── local/               # SQLite·Chroma·문서 그래프 어댑터
└── errors.py
```

| 책임 | 구현 위치 | 소유 범위 |
|---|---|---|
| M01 범위·등록 | `operation/scope/` | catalog·Graph Home·안전 경로·조회 범위 |
| M02 문서 준비 | `indexing/ingestion/` | 리더 선택·읽기·정규화·청크 |
| M03 투영 색인 | `indexing/`, `indexing/extraction/` | 문서 선택·색인 계획·반영·명시적 관계 추출 |
| M04 세대 발행 | `indexing/publication/` | 비공개 세대 검증·활성화·폐기·복구 |
| M05 통합 검색 | `retrieval/search/` | 키워드·벡터·선택적 그래프 후보 결합·순위·주변 청크 |
| M06 그래프 조회 | `retrieval/graph/` | 관련 항목·결정 경로·리소스·일반 그래프 투영 어댑터 |
| M07 근거 연결 | `retrieval/evidence/` | 대상→문서/청크 및 근거→그래프 소유자. 저장소 계약은 `storage/interfaces/evidence_owner_lookup.py` |
| M08 문맥 팩 | `context/pack/` | 근거 선택·예산·누락 설명·팩 구성 |
| M09 발췌 답변 | `context/answer/` | 근거 수집·발췌·인용 검증·렌더링 |
| M10 기억 조회 | `context/memory/` | 프로젝트·결정·질문·타임라인의 파생 조회 |
| M11 코드 투영·조회 | `project/code/` | 스캔·파싱·참조 해석·코드 전용 세대·심볼/호출/영향 |
| M12 프로젝트 문맥 | `project/context/` | 명시적 저장소↔Vault 연결의 코드·문서 근거 조합 |
| M13 결과 설명 | `retrieval/explanation/` | 검색 이유와 최대 256건의 프로세스 임시 캐시 |
| M14 준비 상태 | `operation/readiness/` | 색인·근거 해시·리비전의 조회 전제 판정 |
| M15 진단 | `operation/diagnostics/` | 상태·투영 위생·확장 준비 설명. 자동 수리하지 않음 |
| M16 실행 운영 | `operation/runtime/` | 초기 설정·주기 색인·중단·자원 정리 |
| M17 연동 설정 | `operation/integration/` | MCP 등록·저장소 연결 catalog·지침의 명시적 변경 |

`interface`는 입력 검증·전송·직렬화와 구성을 담당한다. `storage`는 포트의 구체 저장 방식과 저장 모델을 담당한다. `errors.py` 등 지원 파일과 이전 가져오기 경로도 남아 있으므로 위 트리는 전체 파일 목록이 아니다.

## 2. 일반 패키지와 Vault 정책

| 배포 이름 | Python 패키지 | 실제 소스 |
|---|---|---|
| `nolemy-graph-search` | `graph_search` | `packages/graph-search/src/graph_search/` |
| `nolemy-graph-document` | `graph_document` | `packages/graph-document/src/graph_document/` |
| `nolemy-text-embeddings` | `text_embeddings` | `packages/text-embeddings/src/text_embeddings/` |
| `nolemy-vector-search` | `vector_search` | `packages/vector-search/src/vector_search/` |
| `nolemy-vector-index` | `vector_index` | `packages/vector-index/src/vector_index/` |

이 다섯 패키지는 `vault_graph`를 가져오지 않고 Vault ID·역할·경로·세대 정책을 해석하지 않는다. `vector_index`는 임베딩·벡터 계약을 사용하고 `graph_document`는 선택적 `search_bridge`로 그래프 검색과 연결된다. 다섯 패키지 사이의 모든 의존을 금지하는 규칙은 아니다. 배포 이름과 `packages/` 위치는 유지한다.

Vault 전용 벡터 색인 정책은 `indexing/vector_index_adapter.py`, 임베딩 계약은 `storage/interfaces/text_embeddings.py`, Chroma 연결은 `storage/local/vector_store_adapter.py`가 소유한다. 제공자·모델 경로·오프라인 정책의 구체 구성은 `interface/composition/adapters/text_embeddings.py`에서 맡는다.

## 3. 의존과 구성 규칙

그룹 전체에 일률적인 상하 순서를 부여하지 않는다. 예를 들어 `operation`에는 조회에서 사용하는 준비 상태와 색인을 실행하는 운영 기능이 함께 있다. 의존은 그룹 이름이 아니라 각 책임과 소비자가 요구하는 포트로 판단한다.

- **규칙1:** 기능은 필요한 읽기·쓰기·수명 계약을 소비자 포트로 요구한다. 구체 저장소·제공자 생성은 `interface/composition/`에서 수행하고 주입한다. 포트와 DTO는 소유 기능 또는 기존 `storage/interfaces/` 계약에 두며 범용 공통 모듈을 만들지 않는다.
- **규칙2:** `ReadOnlyServiceFactory`, `LocalIndexServiceFactory`, `CodeIndexFactory`, `GraphDocumentServiceFactory`와 `graph_store_factory.py`는 `interface/composition/`에 둔다. 전송별 구성은 `interface/mcp/mcp_service_factory.py`와 `interface/http/http_service_factory.py`에 둔다. 기능 정책은 factory로 옮기지 않는다.
- **규칙3:** 문맥·답변·프로젝트 문맥은 검색·그래프·코드 조회를 조합한다. 준비 상태는 조회나 진단 응답에 의존하지 않는다. 진단은 상태를 설명하며 조회 정책이나 자동 복구를 소유하지 않는다.
- **규칙4:** 새 기능은 구체 factory를 내부에서 다시 열지 않고 주입을 우선한다. 기존 생성자의 선택 인자를 보존하기 위해 `operation/runtime/{setup_service,watch_service}.py`는 `interface/composition/adapters/runtime_indexing.py`의 기본 구성을 지연 가져온다. `project/code/{code_projection_service,code_freshness}.py`도 `interface/composition/adapters/code_projection_storage.py`의 기본 구성을 지연 가져온다. 이 제한된 호환 기본값은 현재 구현의 예외이며 모든 상위 가져오기가 제거됐다는 뜻이 아니다.

## 4. 원본·투영·쓰기 경계

Vault 문서와 등록 저장소의 소스는 읽기만 한다. 메타데이터·벡터·그래프·코드 투영은 원본으로부터 다시 만들 수 있는 파생 데이터이며 지식의 공식 원본이 아니다. 임시 결과 설명 캐시도 영구 기억 저장소가 아니다.

일반 조회는 모델 다운로드·색인 생성·투영 기록·파일 초기화·설정 변경을 실행하지 않는다. 준비되지 않았거나 손상된 경우 기존 오류·경고·복구 안내를 반환한다. 여러 저장소의 색인 반영을 하나의 원자적 트랜잭션이라고 주장하지 않는다. Vault 투영은 비공개 세대를 검증한 뒤 발행하고 코드 투영은 전용 세대 수명을 유지한다.

명시적으로 요청한 setup·index·watch는 해당 파생 데이터를 기록할 수 있다. MCP 등록·저장소 연결 설정·지침 설치/제거는 기존 경로·dry-run·사용자 수정 보존 규칙 아래에서만 설정 파일을 변경한다. 이 예외는 Vault 문서 편집 권한을 주지 않는다.

## 5. 가져오기 호환성과 변경 방법

새 구현과 내부 참조는 위 정식 경로를 사용한다. 이전 `app/`, `ingestion/`, `answer/`, `code_index/`, `vault_adapter/` 등의 공개 경로는 필요한 호환 파일로 남긴다. 이전 파일은 `sys.modules`를 통해 정식 모듈과 같은 객체를 가리켜 기존 클래스 identity와 monkeypatch 동작을 보존한다. 같은 기능을 두 경로에 복제하지 않는다.

기존 leaf 패키지의 `__init__.py` 공개 API를 보존한다. 새 상위 그룹의 초기화는 가볍게 유지하고 필요한 재노출은 지연 처리한다. 가져오기만으로 파일 기록·네트워크·색인·모델 준비를 실행하지 않는다.

기능을 변경할 때는 소유 모듈·소비자 포트·구성 지점을 함께 확인한다. 경로를 변경하면 공개 가져오기와 모듈 identity, 전송 응답, 읽기 전용 경계, 실패 세대 비발행을 관련 검사로 확인한다. 단계별 구현과 과거 실행 증거는 [완료 기록](design/reports/2026-10-15-modularization-completion-ko.md)에 보존한다. 그 기록의 과거 테스트 횟수를 후속 변경의 새 실행 결과로 해석하지 않는다.

호환 경로에는 새 정책이나 계산을 추가하지 않고 정식 구현으로 전달한다. `indexing/vector_indexer.py`처럼 새 그룹 안에도 호환 진입점이 있을 수 있으므로 파일 이름만으로 구현 소유자를 판단하지 않는다. 호환 경로를 없애려면 공개 가져오기·monkeypatch·설치된 진입점의 사용 여부와 호환성 변경 범위를 먼저 확인한다. 이번 재배치에서는 삭제 시점을 정하지 않는다.

## 6. 새 코드를 배치할 때의 기준

| 가이드 | 판단 기준 | 배치 |
|---|---|---|
| 배치1 | Vault 없이 사용할 수 있으며 일반 입력·출력만 요구하는 계산인가? | 기존 `packages/` 중 해당 계약을 소유한 패키지. 새 배포 패키지는 실제 별도 사용 요구가 있을 때 판단한다. |
| 배치2 | Vault ID·문서 역할·조회 범위·근거·세대 정책을 해석하는가? | 해당 기능 그룹의 구현 또는 어댑터. 일반 패키지로 옮기지 않는다. |
| 배치3 | MCP 요청·응답을 다루는가, MCP 설정 파일을 기록하는가? | 프로토콜·도구·리소스는 `interface/mcp/`, 설정 생성·등록은 `operation/integration/mcp/`. |
| 배치4 | 기능을 실행하는가, 구체 저장소·제공자를 생성하는가? | 실행·중단은 `operation/runtime/`, 생성·주입·자원 수명 구성은 `interface/composition/`. |
| 배치5 | 저장 방식을 바꾸는가, 소비자가 요구하는 계약을 바꾸는가? | 저장 구현은 `storage/local/`, 기존 저장소 계약은 `storage/interfaces/`, 기능 전용 소비자 포트·DTO는 소유 기능 가까이에 둔다. |
| 배치6 | 계약이 같은 책임의 구현인가? | 기존 기능 모듈에 둔다. 짧은 파일이나 함수라는 이유만으로 새 폴더·서비스·공통 계층을 만들지 않는다. |

테스트는 현재 `tests/`의 기능별 파일, 공통 대역은 `tests/fakes/`, 원본 예제는 `tests/fixtures/`에 둔다. 독립 패키지 테스트는 각 `packages/<package>/tests/`에 둔다. 소스 그룹과 테스트 폴더를 일대일로 맞추기 위한 이동은 이번 구조에 포함하지 않는다.

경로·초기화·의존을 바꾸면 `tests/test_grouped_module_layout.py`와 관련 `test_*_import_boundaries.py` 및 `test_*_boundaries.py`로 정식 소스의 경계와 기존 경로의 호환성을 확인한다. 정적 검사는 호환 파일만 읽거나 빈 파일 목록으로 통과하지 않아야 한다. 배포 경로를 바꾸면 `tests/verify_graph_module_wheels.py`로 저장소 밖 설치까지 검사한다. 전체 재현 명령은 [완료 기록 §6](design/reports/2026-10-15-modularization-completion-ko.md#6-재현-명령)을 따른다.
