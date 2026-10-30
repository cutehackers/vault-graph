# Vault Graph 모듈화 보완 계획

- Parent Contract: [VG-MOD-20261015](../specs/2026-10-15-vault-graph-modular-architecture-ko.md)
- 선행 계획: [기능별 모듈 전환 계획](2026-10-15-vault-graph-modularization-plan-ko.md)
- Status: Draft — 사용자 검토 전. 구현을 시작하지 않았다.
- Created: 2026-10-29
- 확인 기준: `28f1c96`. 전체 테스트 1435 통과·1 건너뜀.

## 1. 배경

선행 계획은 완료로 기록됐다. 2026-10-29에 AST로 실제 가져오기 그래프를 다시 만들어 VG-MOD §4의 의존 규칙과 대조했다. 정식 디렉터리 배치, 독립 패키지 5개의 `vault_graph` 비의존, 기능 모듈의 전송·구성 계층 비의존은 지켜진다. 그러나 기능 모듈 사이의 방향 규칙 일부가 어긋나 있고, 이를 검사하는 테스트가 없다.

이 계획은 어긋난 지점만 고친다. 공개 CLI/MCP/HTTP 동작, 저장 형식, 검색 점수·순서는 바꾸지 않는다(VG-MOD INV-05). 새 기능, 새 패키지, 범용 `common` 모듈은 만들지 않는다.

## 2. 확인된 차이

| 코드 | 위치 | 내용 | 어긋난 규칙 | 심각도 |
|---|---|---|---|---|
| 발견5 | `context/memory/memory_request_context.py:15`, `timeline_memory.py:19` | 기억 조회가 M15의 `StatusReport` 타입을 가져온다. `TYPE_CHECKING` 전용이라 실행 의존은 없다. | DEP-02 "조회 서비스는 M15에 의존하지 않는다" | 낮음 |
| 발견5-b | `indexing/index_service.py:14,121` | M03 색인 서비스가 M15 `IndexStatusReader`를 직접 생성한다. | DEP-02, 규칙1 | 중간 |
| 발견6 | `operation/readiness/search_readiness_service.py:3,93` | M14 준비 상태 판정이 M03 `VectorIndexer`를 생성해 색인 계획을 계산한다. | DEP-02 "M14는 조회·색인 구현을 가져오지 않는다"의 취지 | 높음 |
| 발견7 | `indexing/index_service.py:24-26`, `operation/diagnostics/index_status_reader.py:15-21`, `operation/diagnostics/projection_hygiene_service.py:12-13` | 기능 코드가 `storage/local` 구체 클래스를 타입·생성에 사용한다. | FA-02, 규칙1 | 중간 |
| 발견8-a | `project/context/project_context_service.py:12` ↔ `operation/integration/project_binding_catalog.py:12` | M12가 M17의 구체 catalog를 받고, M17은 M12의 `ProjectBinding`을 가져온다. | DEP-01 "binding 기록은 M17, 읽기 조합은 M12로 분리" | 중간 |
| 발견8-b | `retrieval/graph/graph_retrieval_service.py:40-43,382` ↔ `retrieval/search/__init__.py:6` | M06이 M05의 후보·응답 DTO를 만들어 반환하고, M05 패키지 초기화가 M06을 다시 노출한다. | 순환 금지(DEP-03/04 취지) | 낮음 |
| 발견8-c | `operation/scope/catalog_service.py:5,21` | M01이 활성 세대를 읽으려고 M04 `ProjectionGenerationManager`를 생성한다. | DEP-01 "M01은 하위 계층" | 낮음 |
| 발견8-d | `indexing/ingestion/document_authority.py` ↔ `document_normalizer.py`, `interface/mcp` 리소스 리더 3개 | 같은 패키지 안 모듈 순환 | 일반 순환 금지 | 낮음 |
| 발견9 | 최상위 호환 경로 28개 디렉터리, 파일 176개 | 모두 얇은 별칭이며 정식 소스는 사용하지 않는다. 테스트 169개 파일이 이전 경로를 가져온다. | 위반 아님. 정리 대상 | 결정 필요 |
| 발견10 | `tests/test_*import_boundar*.py`, `test_functional_module_boundaries.py` | 전송·구성 계층 금지만 검사하고 기능 간 방향은 검사하지 않는다. | FA-02 증거 부족 | 높음 |

`retrieval/graph/graph_contracts.py`, `graph_identity.py`, `graph_readiness.py`, `project/code/code_models.py`를 `storage/interfaces`와 다른 기능이 가져오는 것은 VG-MOD §4 "포트와 DTO는 소유 기능 가까이 둔다"에 맞는 의도된 배치다. 옮기지 않고 아래 보완1의 허용 목록에 계약 모듈로 등록한다.

## 3. 보완 순서

각 단계는 독립 커밋으로 끝내고, 단계마다 전체 테스트와 새 경계 테스트를 통과해야 한다.

| 순서 | 대상 | 변경 | 완료 증거 |
|---|---|---|---|
| 보완1 | 발견10 | 기능 영역 간 가져오기 방향 테스트를 추가한다. 영역 매핑, 허용 방향, 계약 모듈 목록을 테스트 안에 표로 둔다. 현재 위반(발견5–8)은 파일·대상 단위 예외 목록으로 고정해, 새 위반은 실패하고 예외는 늘어나지 않게 한다. 지연 가져오기와 `TYPE_CHECKING` 가져오기도 검사한다. | 새 테스트 통과. 임의 위반을 추가하면 실패하는 것을 한 번 확인 |
| 보완2 | 발견6 | `ReadOnlySearchReadiness`가 `VectorIndexer`를 직접 만들지 않게 한다. 필요한 "벡터 색인이 최신인가" 판정을 생성자 인자 포트로 받고, composition에서 기존 `VectorIndexer` 기반 구현을 주입한다. | 준비 상태 결과·경고 회귀 동일. 예외 목록에서 해당 항목 제거 |
| 보완3 | 발견5-b | `IndexService.status`가 `IndexStatusReader`를 직접 만들지 않게 한다. 상태 조회 포트를 주입받거나, 상태 조회 진입점을 composition에서 `IndexStatusReader`로 직접 연결한다. 공개 `IndexService.status` 시그니처는 유지한다. | `vg status`·MCP 상태 응답 동일 |
| 보완4 | 발견7 | `LocalVectorStatusStore`, `LocalGraphStatusStore`, `SQLiteMetadataStore`, `ChromaVectorStore`에 대해 기능 코드가 쓰는 메서드만 담은 Protocol을 `storage/interfaces/`에 둔다. 기능 코드의 타입과 생성을 Protocol과 주입으로 바꾸고, 구체 생성은 composition에 남긴다. | 기능 영역에서 `storage.local` 가져오기 0건. 예외 목록 제거 |
| 보완5 | 발견8-a | `ProjectContextService`가 binding 읽기 Protocol을 받게 한다. `ProjectBinding` DTO는 M12에 두고, M17 catalog가 그 Protocol을 구현한다. | `explore_project`·`vg project bind` 회귀 동일. M12→M17 가져오기 0건 |
| 보완6 | 발견5 | `StatusReport` 중 기억 조회가 쓰는 필드만 담은 Protocol을 `context/memory`에 둔다. | M10→M15 가져오기 0건 |
| 보완7 | 발견8-b, 8-c, 8-d | 순환을 끊는다. 8-b는 `retrieval/search/__init__.py`의 M06 재노출을 지연 가져오기로 바꾸거나 제거 여부를 확인한다. 8-c는 활성 세대 경로 읽기만 함수 또는 Protocol로 분리한다. 8-d는 공유 타입을 한쪽으로 옮긴다. 공개 가져오기 경로는 유지한다. | 모듈 단위 순환 0건 |
| 보완8 | 발견9 | 결정1에 따라 진행한다. | 결정1 참조 |
| 보완9 | 문서 | `ARCHITECTURE.md`의 의존 규칙과 VG-MOD 완료 기록에 이번 재검증 결과와 보완 결과를 추가한다. 선행 문서의 "Complete" 표기는 그대로 두고 후속 보완 링크만 단다. | 문서와 보완1 테스트의 허용 방향 표가 일치 |

보완2–7은 서로 다른 파일을 고치므로 순서를 바꿔도 된다. 보완1은 반드시 먼저 한다.

## 4. 결정이 필요한 항목

| 코드 | 질문 | 선택지 | 권고 |
|---|---|---|---|
| 결정1 | 이전 경로 호환 파일 176개를 언제 지울 것인가? 지우면 외부에서 `vault_graph.app.*` 같은 이전 경로로 가져오던 코드가 깨진다. | 옵션1: 테스트 169개 파일을 정식 경로로 옮긴 뒤 호환 파일을 지운다. 옵션2: 테스트만 옮기고 호환 파일은 유지한다. 옵션3: 둘 다 그대로 둔다. | 옵션1. 아직 pre-release(0.2.x)이고 정식 소스는 이전 경로를 쓰지 않는다. 다음 메이저 전 정리 비용이 가장 낮다. |
| 결정2 | 보완1의 예외 목록을 보완 완료 후에도 남길 것인가? | 비워서 예외 없이 검사 / 사유를 적어 일부 유지 | 비운다. 남는 항목은 VG-MOD에 규칙 예외로 명시한다. |

## 5. 범위 밖

- Honcho형 대화 기억, 세션 수집, 기록 API. 별도 방향 결정 후 다룬다.
- 검색 품질 개선(임베딩 모델 교체, 코드 청크 색인, 파일 이벤트 기반 watch).
- SPEC v5.0 불변성 엔진 구현.
