# graph_search와 기존 Vault Graph 연동 설계

- Design ID: GS-20261003-INTEGRATION
- Status: Proposed — 기존 응답을 유지하기 위한 연동 제안
- Created: 2026-10-03
- Parent Contract: [GS-20261003](2026-10-03-graph-search-ko.md)
- Product specification: [SPEC §10](../../SPEC.md#10-independent-graph-search-design-proposal)
- Scope: 기존 문서 그래프 투영의 대체 지점과 호환성 검증

이 문서는 부모 계약의 보조 설계다. 별도의 부모 계약이나 승인된 구현 계획이
아니다. 기존 Phase 3C·코드 색인·컨텍스트 팩 계약을 변경하지 않는다.

## 1. 연동 목표와 책임 경계

독립 `graph_search`는 노드·간선·이동 방향만 처리한다. 기존 Vault Graph의
조회 범위, 문서 근거, 신뢰도, 순위, 리비전, 경고는 기존 시스템이 관리한다.
중간 어댑터는 이미 조회·검증된 데이터를 순수 그래프로 변환하고,
탐색한 ID를 원래 객체로 연결한다. DB를 조회하는 두 번째 서비스가 아니다.

```text
CLI / MCP / HTTP
    ↓
GraphRetrievalService
    범위·최신 상태·대상 이름 해석
    GraphStore 읽기·MetadataStore 근거 검증
    ↓ GraphProjectionInput
VaultGraphProjectionAdapter.project()
    도메인 필터 → 간선 상한 → ID 변환
    ↓ 순수 GraphSnapshot
graph_search.search_paths()
    도메인 없는 단순 경로 탐색
    ↓ Path와 종료 요약
VaultGraphProjectionAdapter
    원본 객체 연결 → v1 경로 선택·점수·순위·빌드 ID
    ↓ GraphProjectionResult
GraphRetrievalService
    RelatedResponse / DecisionTraceResponse / graph 후보
    ↓
RetrievalService
    키워드·벡터·그래프 후보 통합과 최종 근거 순위
```

기존 조회는 여러 경로에 점수를 매긴다. 따라서 기존 경로에서는 대표 최단
경로만 반환하는 `graph_search()`가 아니라 `search_paths()`를 사용한다.
새 BFS 기능은 독립 소비자가 직접 사용하며, 기존 응답에 새 필드를 추가하지 않는다.

## 2. 변경 지점과 공개 인터페이스

기존 `GraphProjection` 프로토콜과 DTO는 유지한다.

```python
class VaultGraphProjectionAdapter:
    def __init__(self, *, execution_limits: ProjectionExecutionLimits) -> None: ...

    def project(self, request: GraphProjectionInput) -> GraphProjectionResult: ...
```

제안 위치는 `src/vault_graph/projection/vault_graph_projection_adapter.py`다.
입력·출력·프로토콜의 위치는 `projection/graph_projection.py`에 유지한다.
정책이 충분히 커지면 `vault_graph_path_ranking.py`로 분리하되, 단순한
함수를 여러 계층으로 감싸지는 않는다. execution_limits는 그래프 생성,
간선 검사, 경로 산출, v1 중복 판정 저장량의 운영 상한을 명시한다.
이 값은 기존 request.limit 또는 request.edge_limit과 의미가 다르다.
구현의 명시 실행 예산은 `max_nodes`, `max_input_relationships`,
`max_original_id_bytes`, `max_total_original_id_bytes`, `max_edge_examinations`,
`max_paths`, `max_dedup_paths`를 지정한다. 노드·시작점 발생 수, 필터 전 관계 수와
원래 ID의 UTF-8 크기를 정렬 전에 검사한다. 기본값 `None`은 기존 유효 입력을
그대로 처리하고, 별도 예산을 지정할 때만 새 admission 오류를 적용한다.

기존 클래스 경로 `projection.rustworkx_projection.RustworkxGraphProjection`과
`projection.__init__`의 지연 내보내기는 전환 중 유지한다. 내부 위임 여부는
호환성 게이트 이후에 정하며, 처음부터 클래스를 삭제하거나 import 경로를 바꾸지 않는다.

실제 주입 지점은 현재 다음 두 곳이다.

- `app/read_only_service_factory.py`의 `RustworkxGraphProjection()` 생성
- `cli/main.py`의 그래프 조회 서비스 생성

MCP와 HTTP가 이 서비스를 조합하는 경로를 끝까지 검증한다. 생성자가 여전히
옛 엔진을 사용한다면 단위 테스트가 통과해도 실제 연동 완료가 아니다.
코드용 `CodeQueryService`와 SQLite 코드 탐색은 이번 대체 대상에 넣지 않는다.
향후 소비 가능성은 부모 계약의 도메인 독립성 테스트로 증명하고, 코드 색인을
현재 문서 그래프 DTO에 억지로 통합하지 않는다.

## 3. 입력 변환 계약

### 3.1 필터와 상한의 순서

1. 현재 구현처럼 노드를 `(vault_id, entity_id)`로 중복 제거한다. 같은 ID의
   여러 입력은 첫 객체를 유지하는 v1 규칙을 따른다.
2. 기존 노드 순서 `(vault_id, normalized_name, entity_id)`를 구한다.
3. 관계 종류, 허용 상태, cross-Vault 허용 여부, 양쪽 끝점 존재를 검사한다.
4. 기존 간선 정렬키와 동점 시 입력 순서를 유지해 정렬한다.
5. 허용된 간선에만 request.edge_limit을 적용한다. 필터 전의 소음이 상한을 소모하지 않는다.
6. 선택한 노드·간선으로 코어 스냅샷을 만든다. 원래의 범위·근거·상태 정보는 어댑터에 남긴다.

근거 확인은 이 절보다 앞서 `GraphRetrievalService._evidence_valid_relationships()`에서
끝나야 한다. 어댑터가 결과를 받은 뒤 근거 없는 간선을 제거하면, 그 간선에
연결된 경로가 이미 검색을 왜곡하므로 허용하지 않는다.

### 3.2 ID 대응표

도메인 ID를 `vault + ':' + entity`처럼 이어 붙이지 않는다. 구분 문자가
원본에 포함될 수 있고 동일 개체·관계 ID가 서로 다른 Vault에 존재할 수 있다.
요청마다 불투명한 고유 ID를 할당하고 다음 대응표를 어댑터 내부에 둔다.

| 순수 ID | 도메인 대응 |
| --- | --- |
| NodeId | `(vault_id, entity_id)`와 원본 GraphProjectionNode |
| EdgeId | 선택된 입력 간선의 고유 발생 위치와 원본 GraphProjectionEdge |
| EdgeId의 원본 객체 | `(source_vault_id, relationship_id)` 및 양쪽 끝점 |

NodeId는 기존 정렬 후의 노드 번호, EdgeId는 필터·정렬·상한 적용 후의 발생
번호를 고정 폭 ASCII로 표현할 수 있다. 예: `n00000001`, `e00000001`.
번호는 요청 안에서만 의미가 있고 공개 응답·캐시 키·영구 식별자로 사용하지 않는다.
같은 두 끝점의 평행 간선과 서로 다른 Vault의 같은 relationship_id를 코어 단계에서
합치지 않는다. 일관성 없는 동일 도메인 행은 §6의 v1 호환성 조건을 별도로 따른다.

코어로 넘기는 값은 Edge(id, source_id, target_id)와 노드 ID뿐이다.
status, confidence, relationship_type, evidence_ref_ids, graph_index_revision,
actual_scope_keys, source_graph_revisions는 넘기지 않는다.

## 4. 탐색·복수 시작점·순위

`out/in/both`를 코어의 `outbound/inbound/both`로 변환한다.
시작점을 기존 노드 정렬키로 정렬해 한 번씩 탐색한다. 중복 시작점은 v1의
관찰 가능한 효과가 유지되도록 처리하고, 시작점 자체나 다른 시작점을 끝점으로
하는 경로는 v1처럼 결과에서 제외한다. 해당 시작점을 통과하는 경로는
탐색 과정에서 막지 않는다.

코어 경로의 각 EdgeId를 원본 객체로 복원한다. inbound 또는 both의 역방향
스텝에서도 원본 source/target과 근거 소유 Vault를 뒤집지 않는다.
노드·간선·경로를 새 도메인 객체로 추정하지 않고 정확한 대응표로 찾는다.
대응표 누락은 내부 오류이며, 조용히 결과를 버리거나 빈 결과로 바꾸지 않는다.

### 4.1 기존 점수와 정렬

기존 정책을 코어 밖에 둔다.

```text
score = min(edge.confidence × status_weight(edge.status)) × depth_weight(depth)

status: stated=1.0, inferred=0.75, contested=0.45, deprecated=0.0
depth: 1=1.0, 2=0.6
```

경로 정렬은 현재 `_path_sort_key`와 같은 순서다.
점수 내림차순 → 깊이 → 첫 관계 종류 우선순위 → 첫 관계 종류 →
끝점 Vault → 끝점 normalized_name → 첫 relationship_id.
종류 우선순위는 supersedes, depends_on, blocks, implements, related_to,
mentions 순서이며 나머지는 뒤에 둔다. 설명 문자열도 기존 형식을 유지한다.

코어는 canonical ID 순서로 열거하므로 기존 DFS 순서와 같다고 가정하지 않는다.
모든 후보가 완전히 열거된 뒤 기존 정렬과 v1 동점 순서를 적용한다.
동점 비교에 필요한 legacy traversal ordinal은 시작점 순서와 각 단계의
기존 인접 간선 순위의 튜플로 복원한다. 인접 순위는 현재 `_adjacent_edges`의
정렬키·끝점 노드 번호·동점 규칙을 그대로 재현한다. 네이티브 열거 순서에
의존하는 동점은 명시된 rustworkx 지원 버전별 차분 검증을 통과해야 한다.

최종 상위 K 선택은 전체 열거 후의 순위와 동일해야 한다. 먼저 DFS K건만
얻어 점수를 매기는 방식은 금지한다. 구현은 스트리밍 후보와 크기 K의 heap으로
선택할 수 있지만, v1 중복 선택 상태의 별도 메모리는 §6과 §7에서 제한한다.
최종 items의 순위·근거 조립은 기존 서비스를 유지한다.

## 5. 결과·빌드 ID·완전성

GraphProjectionResult의 의미를 유지한다.

- node_count: 도달 노드 수가 아니라 입력에서 중복 제거한 전체 노드 수.
- edge_count: 검사를 수행한 횟수가 아니라 필터 후 상한으로 선택한 간선 수.
- paths: 원본 seed·target·간선·score·explanation을 가진 GraphPath.
- source_graph_revisions: 기존대로 정렬한 리비전.
- graph_projection_version: v1 호환이 증명되는 동안 `graph-projection-v1`.
- projection_build_id: 기존 `_projection_build_id`의 필드·JSON 직렬화·SHA256을 보존.
- truncated: 기존 간선 상한으로 빠진 간선이 있거나, 완전 열거한 v1 유효 경로가
  최종 limit보다 많을 때 True. 상한에 수가 딱 맞는 경우는 초과와 구분한다.

코어의 stop_reason=completed는 이미 필터·상한을 적용한 메모리 그래프에
대한 완료다. DB 조회의 스캔 상한, stale 범위 누락, cross-Vault 제한, 근거 누락은
기존 서비스의 경고로 별도 보존한다. 코어의 완료로 기존 경고를 지우지 않는다.
generated_at은 서비스가 생성하며, 코어 결과에 시간이나 리비전을 추가하지 않는다.

이 코어의 대표 경로 완료를 사용해 전체 코드 그래프의 영향도·SCC 검증이
완료되었다고 표시하지 않는다. 저장소 전체 검증은 SPEC의 별도 계약이다.

## 6. 현재 구현의 호환성 주의점

현재 코드에서 실제로 확인된 사항이며 이번 설계에 숨겨 넣어 수정하지 않는다.

| ID | 현재 동작 | v1 연동 규칙 / 개선 제안 |
| --- | --- | --- |
| COMP-01 | 간선 정렬키에 source_entity_id·전체 payload가 없으며 동점은 입력·네이티브 순서에 영향을 받는다. | v1에서는 같은 입력의 같은 결과를 차분 검증한다. 완전한 정렬키 추가는 별도 정책 version 제안으로 남긴다. |
| COMP-02 | 경로 중복키는 seed·target·relationship_id 순열뿐이다. 서로 다른 Vault의 같은 관계 ID가 충돌할 수 있다. | 코어는 간선을 모두 구분한다. v1 어댑터는 legacy 순서로 최초 경로를 선택하는 규칙을 재현한다. 충돌 보정은 별도 version 승인이 필요하다. |
| COMP-03 | build ID는 간선 payload를 직접 해시하지 않고 source_graph_revisions에 의존한다. | v1 빌드 ID 공식을 보존한다. 전체 그래프 내용 해시는 별도 변경이며 코어에 Vault 리비전을 넣는 이유가 아니다. |

COMP-02를 재현할 때 canonical 탐색에서 먼저 나온 경로를 선택하면 안 된다.
같은 legacy 중복키의 후보 중 legacy traversal ordinal이 가장 작은 경로를
선택해야 하며, 그 뒤에 점수·순위를 계산한다. 중복키별 최소 ordinal의 후보를
보유하는 상태는 후보 수에 비례할 수 있다. 이를 항상 O(K) 메모리라고 주장하지 않는다.

기존 중복 버그의 조용한 수정과 기존 버그를 코어에 옮기는 방식 모두 피한다.
수정된 정책을 채택한다면 `graph-projection-v2` 등 별도 계약, golden 결과,
명시적인 사용자 판단이 필요하다. 이번 요청은 그 변경을 승인하지 않는다.

## 7. 자원 한도와 오류 변환

GraphProjectionInput의 depth는 현재 1–2, edge_limit은 최대500,
최종 결과 limit은 최대50이다. 이 limit은 계산량 상한과 같지 않다.
양방향 탐색의 방향 후보 수 A는 선택한 E개 간선에 대해 최대2E다.
한 시작점, 깊이2에서 후보 검사·비어 있지 않은 경로 수의 보수적 상한은
`A + A²`로 잡을 수 있다. 여러 시작점 S는 시작점별 예산을 정하고
합계 `S × (A + A²)`도 admission 단계에서 검사한다.

검사 상한은 `A + A²`, max_paths는 `max(1, A + A²)`로 설정한다.
E=0일 때는 검사 상한0과 경로 상한1로 정상적인 빈 결과를 얻는다.
이 상계를 사용하면 허용된 그래프에서 전량 열거가 가능하다.
그러나 E=500이면 계산·메모리 비용이 충분히 클 수 있으므로,
숫자만으로 운영 적합성을 주장하지 않는다. GraphLimits는 실제 입력 노드·
간선·ID 크기를 모두 검사하고, 중복 추적 메모리도 별도 운영 상한으로 제한한다.

기존 모든 허용 입력에서 동일 결과를 내면서 낮은 임의 시간 제한도 보장한다는
주장은 하지 않는다. 실제 부하 측정 후 지원 입력 범위와 execution_limits를
정해야 한다. 범위 변경·새 실패 조건은 Open Decisions에 두고 기본 엔진 전환 전에 판단한다.

| 조건 | 제안하는 변환 | 보존할 사항 |
| --- | --- | --- |
| 정상·전체 열거 완료 | 기존 GraphProjectionResult | 점수·순위·리비전·빌드 ID·경고 흐름 |
| 도메인 row→순수 snapshot 변환 불일치 | GraphStoreError 계열의 명시적 오류 | 빈 결과로 정상 처리하지 않는다. |
| 구성된 실행 예산을 초과하거나 paths가 미완료 | `graph_projection_budget_exceeded` 실패 제안 | 부분 DFS를 완전한 점수 상위 결과로 게시하지 않는다. |
| native 엔진·내부 대응표 오류 | GraphStoreError로 원인을 보존 | 자동 색인·캐시 생성·외부 쓰기 없음 |

새 오류 코드는 기존 공개 응답에 대한 제안이지 이미 승인된 변경이 아니다.
예산 밖 요청의 거부, 기존 엔진으로 유지, 상한 확대 중 선택은 Q-INT-01이다.
명시 승인 전에는 현행 factory 기본값과 공개 실패 동작을 유지한다.
오류가 발생한 다음 더 약한 검증으로 재실행해 정상 결과를 만들어서는 안 된다.

## 8. 연동 수용 기준과 검증

| ID | 검증해야 하는 결과 | 현재 근거 / 추가 증거 |
| --- | --- | --- |
| IT-01 | 순수 패키지에 도메인 객체·근거·범위가 전달되지 않는다. | import 경계와 spy로 순수 입력을 확인하는 새 테스트 |
| IT-02 | 필터 후 edge_limit을 적용한다. | `tests/test_graph_projection.py`의 filters-before-cap와 새 어댑터 차분 테스트 |
| IT-03 | out/in/both, 깊이1·2, 모든 중간 끝점, 시작점 제외가 유지된다. | 기존 투영 테스트 + multi-seed·역방향 복수 경로·필터 후 간선0건 fixture |
| IT-04 | 점수·정렬·설명·동점 순서·최종limit이 동일하다. | 기존 엔진과 새 어댑터의 field-by-field oracle 비교 |
| IT-05 | node_count·edge_count·truncated·version·build ID가 동일하다. | 기존 투영 계약과 같은 입력 golden |
| IT-06 | 근거 없는 간선은 탐색 전에 제거된다. | `tests/test_graph_retrieval_service.py` + 코어 입력 spy |
| IT-07 | Vault별 같은 개체·관계 ID와 평행 간선이 정확히 원본에 연결된다. | 기존 multi-Vault 테스트 + 충돌 fixture, COMP-02의 v1 억제도 별도로 확인 |
| IT-08 | CLI/MCP/HTTP의 related·decision-trace·include-graph가 같은 서비스를 호출한다. | 공개 입구 응답 검사 + 실제 주입된 구현 확인 |
| IT-09 | plain search는 그래프 엔진을 열지 않는다. | `tests/test_graph_retrieval_read_only_boundary.py`의 기존 경계 테스트 |
| IT-10 | Vault·graph-home·model-cache·projection-cache에 쓰지 않는다. | 기존 readonly 테스트 + 파일 쓰기/자동색인 금지 spy |
| IT-11 | 예산 중단을 완료된 순위로 공개하지 않는다. | path_limit/edge_limit/cancel/fault 주입과 명시 오류 변환 |
| IT-12 | 독립 모듈 wheel과 Vault Graph 배포에서 모두 동작한다. | 별도 설치 smoke + 두 wheel 및 factory 통합 검증 |

별도 차분 테스트에서 비교할 항목은 seed·target identity, 각 원본 간선,
score, explanation, 순서, count, truncated, version, build ID와 리비전이다.
generated_at은 제외하되 존재·형식·생성 책임을 별도로 검사한다.
시작점·노드·간선 입력 순열, 중복·동점·관계 ID 충돌을 포함한다.
독립 모듈의 canonical 결정성과 v1 어댑터의 입력순 의존 동작을 같은 기준으로
검사하지 않는다. v1은 같은 입력에 대해 기존 결과와 같아야 한다.

실제 비교 기준은 테스트 전용으로 고정한 기존 엔진이다. 새 어댑터를 호출하는
shim을 oracle로 사용하면 자기 비교가 되므로 금지한다. 고정본은 테스트 fixture로
기록하고, 프로덕션에서 중복 탐색을 상시 실행하는 방식은 도입하지 않는다.

현재 실행 가능한 회귀 테스트 계획:

```bash
uv run --python 3.12 pytest -q tests/test_graph_projection.py tests/test_graph_retrieval_service.py tests/test_multi_vault_graph_retrieval.py tests/test_search_include_graph.py tests/test_graph_retrieval_read_only_boundary.py
uv run --python 3.12 pytest -q tests/test_cli_related.py tests/test_cli_decision_trace.py tests/test_mcp_tools.py tests/test_http_server.py tests/test_context_pack_builder.py tests/test_answer_service.py
uv run --python 3.12 pytest -q
```

새 차분·예산·factory 테스트 경로는 구현 시 확정한다. 현재 존재하지 않는
테스트를 실행·통과했다고 적지 않는다. 전체 수집 수는 현재 상태에서 다시
측정하며, SPEC의 1,188 baseline 문구만으로 현재 무회귀를 증명하지 않는다.

## 9. 전환 절차와 되돌리기

1. 독립 package의 FA 검증과 wheel smoke를 먼저 완료한다.
2. 별도 어댑터를 기존 프로토콜 뒤에 추가한다. 기존 factory는 유지한다.
3. 고정한 v1 oracle과 새 어댑터를 모든 IT fixture에서 비교한다.
4. Q-INT-01·Q-INT-02 및 운영 측정을 해결하고, 실제 공개 입구에서 후보 factory를 검증한다.
5. 기존 import 경로를 유지하면서 factory의 한 주입 지점씩 전환한다.
6. 전체 회귀·배포 검사를 완료한 뒤에만 기본 전환을 완료했다고 기록한다.

DB 스키마·원본 Vault·persisted projection은 변경하지 않는다. 되돌리기는
factory 주입을 기존 엔진으로 복구하는 코드 변경으로 수행한다. 자동 외부 쓰기나
runtime flag 체계를 새로 만들지 않는다. 기존 엔진 삭제는 소비자를 확인한
별도 승인 범위이며 이번 설계의 완료 조건이 아니다.

## 10. Open Decisions와 설계 제출 기준

| ID | 질문 | 선택지와 판단 기준 | 제안 |
| --- | --- | --- | --- |
| Q-INT-01 | 실행 예산 밖 입력을 어떻게 처리할 것인가? | 명시 실패는 새로운 동작, 현행 엔진 유지에는 기존 계산 위험, 상한 확대에는 운영 비용이 있다. | 실측으로 admission 범위를 정하고 실패 계약을 먼저 승인. 그전에는 기본값 유지. |
| Q-INT-02 | COMP-01–03을 v1에서 수정할 것인가? | 수정은 결과·빌드 ID·호환성 변경. 유지하면 기존 한계가 남는다. | 최초 연동은 v1 보존. 보정은 별도 version으로 제안. |

설계 제출은 변환 양방향, 정확한 기존 정책, 자원·오류·호환성 위험, 주입 지점,
테스트·배포·되돌리기 계획이 구체화되고 부모 계약과 서로 연결되면 완료다.
운영 준비나 실제 연동 완료는 IT 증거와 미확정 판단의 해결 전에는 주장하지 않는다.
