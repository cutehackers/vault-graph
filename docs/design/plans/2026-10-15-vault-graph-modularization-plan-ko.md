# Vault Graph 기능별 모듈 전환 계획

- Parent Contract: [VG-MOD-20261015](../specs/2026-10-15-vault-graph-modular-architecture-ko.md)
- Status: Approved roadmap — 사용자가 명세·계획의 구현을 지시했다. 구현용 Vertical Slice 계약은 생성하지 않았다.
- Created: 2026-10-15
- Implementation: Complete — [단계0–8 실제 구현·검증·독립 리뷰](../reports/2026-10-15-modularization-completion-ko.md). 당시 발견한 legacy 색인 결함의 후속 수정은 같은 기록 §5에 설명한다.

## 1. 실행 원칙

기존 디렉터리와 서비스를 재사용한다. 먼저 기능별 진입점·의존 방향·행동 보존을 검증하고, 파일 이전은 그 경계를 강제할 때만 한다. 각 단계는 공개 진입점부터 저장/조회와 응답까지 이어지는 동작으로 끝낸다. 클래스나 디렉터리만 이동한 상태는 완료가 아니다.

현재 공개 인터페이스·저장 형식·배포 패키지 계약을 보존한다. 단계가 실패하면 그 단계의 코드 변경과 비활성 파생 세대만 되돌리며 사용자 파일과 활성 세대를 덮어쓰지 않는다. 이 계획 자체가 커밋 되돌리기나 데이터 삭제의 실행 지시는 아니다.

## 2. 순서와 사용자 결과

| 순서 | 모듈 / 선행 단계 | 단계 종료 시 확인할 사용자 결과 | 핵심 증거 |
|---|---|---|---|
| 단계0 | 전체 / 없음 | 현재 CLI/MCP/HTTP 기능·기본값과 저장/파일 부작용의 기준선을 재현할 수 있다. | 현재 명령/DTO 목록·대표 응답·원본 해시·테스트 결과. 아래 기존 테스트는 실행 예정 목록이며 이번 문서 작업에서 실행한 결과가 아니다. |
| 단계1 | M01·M04·M14 / 단계0 | 같은 등록 범위로 조회·색인이 동작하며, 실패한 새 색인은 기존 조회를 손상시키지 않는다. | 경로 이탈·읽기 실패·세대 발행 실패·자원 종료. readiness 계산과 진단 조립 분리 |
| 단계2 | M02·M03 / 단계1 | 명시적 색인 뒤 문서·태그·관계와 벡터 결과를 기존 경로로 조회한다. | 전체/증분/삭제 범위·재시도·문서 그래프 백엔드 전환·모델 오류·원본 불변 |
| 단계3 | M07 + M05/M06의 근거 조회 교체 / 단계2 | 기존 검색·관련 항목 응답이 유지되고, 명시적 내부 호출로 문서/청크→노드·관계를 찾는다. | SEL의 순서·중복·범위·부분 결과·리비전 변경·provider 실패, legacy/document와 실제 factory |
| 단계4 | M05·M06 / 단계3 | 검색·관련 항목·결정 경로·리소스 조회가 다른 기능의 내부 구현 없이 동작한다. | 순위·중복·경고·cross-vault·bounded traversal·기본 그래프 비활성 보존 |
| 단계5 | M08·M10·M09 / 단계4 | 문맥 팩·기억 조회·발췌 답변이 같은 근거·예산·인용 정책으로 동작한다. | 예산 초과·누락·오래된 근거·인용 검증·공유 읽기 문맥·의존 순환 차단 |
| 단계6 | M11·M12 / 단계4와 단계5의 M08 | 코드 색인·심볼/영향 조회와 `explore_project`가 함께 동작하고 코드 부재 시 기존 대체 응답을 유지한다. | 파서·참조 해석·코드 세대·신선도·binding 범위·문맥 예산·저장소 원본 불변 |
| 단계7 | M13·M15·M16·M17 / 단계5–6 | 초기 설정·주기 색인·결과 설명·상태 조회와 명시적 설정 변경을 기존 명령으로 실행한다. | 중단/close·dry-run·설명 캐시 퇴출·진단 읽기 전용·지침 사용자 수정 보존·명시적 등록 |
| 단계8 | 지원 계층·전체 / 단계7 | 동일 설치 환경에서 독립 패키지와 모든 기존 진입점이 동작한다. | 전체 회귀·정적 검사·wheel 격리 검증·동일 fixture 성능 비교·최종 독립 리뷰 |

단계1에서 모든 factory를 재작성하지 않는다. 안전성 정책의 소유권을 먼저 정하고 후속 단계에서 필요한 구성만 바꾼다. 단계3은 SEL의 단일 구현 경로이며 단계4에서 역조회나 근거 조회를 다시 구현하지 않는다. 단계6의 코드 내부 정리는 단계5와 독립 진행할 수 있지만, 프로젝트 조합의 통합 검증은 M08 정리 후 수행한다. 불필요한 동시 작업은 늘리지 않는다.

## 3. 현재 코드의 소유권과 검증 지도

표의 파일명은 `src/vault_graph/` 기준이다. 테스트명은 `tests/` 기준이며 실제 변경 범위에 맞춰 선택한다.

| 소유 경계 | 현재 소스 | 기존 검증 출발점 |
|---|---|---|
| M01 | `app/{catalog_service,graph_home,path_guard,query_scope_resolution}.py` | catalog·scope·graph home·path guard 테스트 |
| M02 | `ingestion/` | `test_vault_loader.py`, `test_document_readers.py`, `test_document_models.py` |
| M03 | `indexing/`, `extraction/`, `app/index_service.py`, `vault_adapter/vector_index.py` | `test_graph_indexer.py`, `test_graph_source_store.py`, metadata/vector indexer 테스트 |
| M04 | `app/projection_generation.py`; local bundle의 commit/close | generation·bundle publication·local index factory 실패 테스트 |
| M05 | `retrieval/` 중 그래프 인터페이스·readiness 제외 | `test_search_include_graph.py`, keyword·ranking·retrieval 테스트 |
| M06 | `projection/`, `app/{graph_retrieval_service,graph_resource_service}.py`, `retrieval/graph_retrieval.py` | `test_multi_vault_graph_retrieval.py`, `test_cli_related.py`, `test_cli_decision_trace.py` |
| M07 | 제안 `vault_adapter/evidence_linking.py` + 소비자의 분산 근거 조회 | SEL 수용 기준, 이후 추가할 행동 검증 |
| M08 | `context/` | `test_context_pack_builder.py`, `test_context_pack_import_boundaries.py`, `test_context_pack_read_only_boundary.py` |
| M09 | `answer/`, `app/answer_service.py` | `test_answer_composer.py`, `test_answer_renderer.py`, `test_answer_import_boundaries.py` |
| M10 | `memory/`의 기억 모델·reader·context·project/decision/issue/timeline 서비스 | `test_project_memory_service.py`, `test_decision_memory_service.py`, `test_issue_memory_service.py`, `test_timeline_memory_service.py` |
| M11 | `code_index/` | `test_code_projection_service.py`, `test_code_generation.py`, `test_code_query_service.py`, `test_code_query_read_only_boundary.py` |
| M12 | `project_context/` 중 binding catalog 제외 | `test_project_context_service.py`, `test_project_context_scope.py`, `test_project_context_budget.py`, `test_project_context_import_boundaries.py` |
| M13 | `memory/`의 result explanation·cache | `test_result_explanation.py`, `test_mcp_result_explanation_cache.py`, `test_mcp_explain_result.py` |
| M14 | `app/{graph_readiness_service,search_readiness_service}.py`, `retrieval/search_readiness.py` | `test_app_search_readiness_service.py`, graph readiness 테스트 |
| M15 | `app/{index_status_reader,projection_hygiene_service}.py`, `memory/health_explorer.py` | `test_health_explorer_service.py`, projection hygiene·status 테스트 |
| M16 | `app/{setup_service,watch_service}.py` | `test_setup_service.py`, `test_cli_watch.py` |
| M17 | `harness/`, `project_context/project_binding_catalog.py`, MCP config/registration | `test_harness_guidance.py`, `test_harness_guidance_read_only.py`, `test_setup_harness_guidance.py`, `test_project_binding_catalog.py`, `test_mcp_config_registration.py` |
| 구성 지점 | `app/{read_only_service_factory,local_index_service_factory,code_index_factory,graph_store_factory,graph_document_service_factory}.py`, `mcp/mcp_service_factory.py`, `http/http_service_factory.py` | factory·read-only·backend selection·세대 정리 테스트 |
| 전송 | `cli/`, `mcp/` 중 설정/등록/factory 제외, `http/` 중 factory 제외 | `test_mcp_stdio_smoke.py`, `test_mcp_scope.py`, `test_mcp_tool_serialization.py`, CLI/HTTP 회귀 |
| 저장·어댑터·호환 | `storage/`, `vault_adapter/`의 나머지 파일, `embeddings/`, `graph/`, `errors.py`, 패키지 초기화 | 저장소 계약·일반 패키지 역의존 금지·기존 가져오기·독립 wheel |

물리적 파일 하나에 두 책임이 있는 경우, 예를 들어 local bundle의 발행과 factory의 자원 조립, 현재 위치와 목표 책임을 구분한다. 단계별 변경 후에는 정책별 소유자가 하나가 되도록 정리한다. 모든 물리 파일을 별도 기능으로 만들지 않는다. 새 파일이 생기면 이 지도에 소유 경계를 추가한다.

## 4. 검증과 단계 종료 조건

실제 구현 전에 각 단계의 변경 파일과 위험에 맞춰 실행 명령을 확정한다. 현재 저장소의 실행 방식은 `pyproject.toml`과 CI 설정을 기준으로 재확인한다. 문서 계획 단계에서 아직 실행하지 않은 명령이나 테스트 성공을 기록하지 않는다.

현재 [CI](../../../.github/workflows/ci.yml)의 최종 통합 명령은 다음과 같다. 단계별로는 같은 실행 환경에서 위 지도에 해당하는 테스트를 먼저 선택한다. 아래 명령은 구현 단계의 필수 확인 목록이며 이번 문서 작업에서는 실행하지 않았다.

```sh
uv run --python 3.12 ruff check src tests packages
uv run --python 3.12 mypy src tests packages/text-embeddings/src packages/vector-search/src packages/vector-index/src
uv run --python 3.12 --all-packages --all-extras pytest -q tests packages/*/tests
uv run --python 3.12 python tests/verify_graph_module_wheels.py
```

| 검사 | 적용 조건 | 남길 증거 |
|---|---|---|
| 행동 보존 | 모든 단계 | 관련 공개 경로의 입력·응답·경고·순서, fixture 회귀 결과 |
| 경계·타입·정적 검사 | 의존 방향·인터페이스 변경 | 기존 import boundary 테스트와 변경 경계 검사, Ruff·mypy의 실제 명령/종료 코드 |
| 원본·조회 무변경 | 파일/저장 경계를 건드릴 때 | 보호 대상 해시·경로 이탈 거부·미초기화 조회의 무기록 |
| 발행·복구 | 색인·세대·factory·watch 변경 | 반영 중 실패·활성화 직전 실패·중단·재시도·close 후 상태 |
| 호환·패키지 | 공개 가져오기·어댑터 변경 및 최종 단계 | 기존 계약 테스트·독립 설치·Vault 실제 연결 경로 |
| 성능 | 비용이 달라지는 조회/색인 및 최종 단계 | 동일 입력·데이터 규모·모델·cold/warm 조건과 시간/메모리. 기존 성능 계약 적용 여부 |
| 독립 리뷰 | 단계별 실질 변경과 최종 통합 | 구체 반례·지적·수정·재검증. 리뷰 무지적을 실행 검증의 대체로 삼지 않음 |

모든 해당 기준이 통과하고 변경 diff·보호 파일·실행 상태를 확인해야 단계가 끝난다. 외부 제공자·실제 모델·배포 환경을 검증하지 않았다면 그 제한을 결과에 적는다. 문서 완성과 로컬 테스트 통과를 배포 검증으로 표현하지 않는다.

## 5. 제안 상태와 후속 작업

이 계획의 Q-01/Q-02는 후속 구현 지시로 해결했고 부모 명세와 결정 기록에 반영했다. 별도의 상충하는 상세 API나 `.tasks` 계약은 만들지 않았다. 후속 구현은 이 명세와 SEL 계약을 기준으로 진행하며 실제 결과는 구현·검증 기록에 남긴다. 본문에서 ‘이번 문서 작업’이라고 표시한 미실행 설명은 최초 명세 작성 시점을 가리킨다.
