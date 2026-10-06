# 독립 graph_search 상세 설계

- Contract ID: GS-20261003
- Contract Status: Proposed — 상세 설계 제안이며 구현·기존 동작 변경을 승인하지 않는다.
- Created: 2026-10-03
- Intent Status: Hardened for design scope
- Independent Design Review: Passed on 2026-10-04 — 상세 설계 제출 범위만 검토
- Source: 현재 사용자 요청과 이 대화에서 확인한 도메인 독립성·연동 어댑터 요구
- Product specification: [SPEC §10](../../SPEC.md#10-independent-graph-search-design-proposal)
- Supporting design: [기존 시스템 연동](2026-10-03-graph-search-integration-ko.md)
- Decision records: §12의 제안 기록. 승인 전에는 `docs/DECISIONS.md`에 옮기지 않는다.
- Glossary: §3
- Review corrections: [PATCH_LOG](../../PATCH_LOG.md#2026-10-04---correct-graph-search-boundary-contracts-after-review)

## 1. 문제와 완료 범위

현재 `GraphProjectionInput`은 Vault ID, 관계 상태, 신뢰도, 근거 ID,
리비전과 그래프 탐색 조건을 함께 받는다. 다른 소비자가 연결 탐색만
사용하려 해도 Vault의 데이터 모델을 알아야 한다.

이번 산출물은 독립적으로 배포·호출 가능한 그래프 탐색 모듈의 상세 계약,
기능·운영 검증 계획, 기존 응답을 보존하는 별도 어댑터 설계다.
이 문서의 완성은 모듈 구현이나 production-ready 인증을 뜻하지 않는다.
구현 완료와 운영 준비 완료는 §13–§15의 실제 증거로만 판정한다.

| ID | 의도 / 관찰 가능한 목표 |
| --- | --- |
| INT-01 | Vault와 무관한 소비자가 그래프 탐색을 재사용한다. |
| GOAL-01 → INT-01 | 별도 환경에서 모듈만 설치하고 노드·간선으로 탐색 결과를 얻는다. |
| GOAL-02 → INT-01 | 방향·깊이·동일 길이 경로·제한 중단을 일관되게 해석한다. |
| GOAL-03 → INT-01 | 동일 스냅샷을 반복·동시 조회해도 입력과 외부 상태가 변하지 않는다. |
| INT-02 | 모듈 분리 때문에 기존 Vault 결과가 바뀌지 않는다. |
| GOAL-04 → INT-02 | 기존 공개 조회 경로가 별도 어댑터를 통해 호환성 검증을 통과한다. |

사용자는 Python 라이브러리 소비자와 Vault Graph 개발자다. 호출자는
조회 권한과 최신 상태를 확인한 유한한 메모리 그래프를 준비한다.
코어에는 DB 연결, 파일 경로, 인증 정보, 도메인 객체를 전달하지 않는다.

### 범위

도메인 없는 유향 다중 그래프, 한 시작점의 제한된 BFS 탐색, 대표 최단
경로 복원, 제한된 단순 경로 열거, 결정적인 순서, 입력 검증, 부분 결과,
오류 계약, 독립 패키지와 검증·배포 기준을 포함한다.

가중 최단 경로, 자연어 검색, 순위·신뢰도 계산, 전체 관계 서브그래프 반환,
권한 검사, 도메인 필터, DB 조회, 영구 캐시, 원격 서비스, SCC 기반 순환
검증은 포함하지 않는다. 순환 그래프에서 탐색이 종료된다는 사실은 그래프가
비순환이라는 증명이 아니다. SPEC의 전역 SCC 검증을 대신하지 않는다.

## 2. 현재 사실과 설계의 관계

| 사실 | 현재 근거 | 설계에 미치는 영향 |
| --- | --- | --- |
| 기존 투영은 도메인 객체를 받는다. | [graph_projection.py](../../../src/vault_graph/projection/graph_projection.py) | 기존 타입을 독립 패키지로 이동하지 않는다. |
| 기존 구현은 여러 단순 경로를 열거한 뒤 점수를 매긴다. | [rustworkx_projection.py](../../../src/vault_graph/projection/rustworkx_projection.py) | BFS 대표 경로만으로 대체하면 호환성이 깨진다. |
| 조회 서비스는 근거 없는 관계를 탐색 전에 제외한다. | [graph_retrieval_service.py](../../../src/vault_graph/app/graph_retrieval_service.py) | 근거 검사와 접근 범위는 코어 밖에서 유지한다. |
| 저장소는 Python 3.12+, rustworkx를 사용한다. | [pyproject.toml](../../../pyproject.toml) | Python 3.12를 최소 지원선으로 제안한다. |
| CI는 lint·타입·pytest·wheel 검사를 수행한다. | [ci.yml](../../../.github/workflows/ci.yml) | 독립 wheel 검사와 연동 회귀 검사를 추가할 계획이다. |

기존 [Phase 3C 계약](../../superpowers/specs/phase-3/2026-06-10-phase-3c-graph-projection-retrieval-design.md)은
변경하거나 폐기하지 않는다. 이 문서는 새 모듈의 제안이고, 연동 문서는
그 계약을 유지하기 위한 변환·호환성 조건을 정의한다.

## 3. 용어와 불변 조건

| 용어 | 이 설계에서의 의미 |
| --- | --- |
| NodeId / EdgeId | 비어 있지 않은 UTF-8 인코딩 가능 `str`. 의미를 해석하지 않는 식별자. |
| 스냅샷 | 호출자가 준비한 그래프를 검증·복사해 만든 변경 불가능한 조회 대상. |
| 방향 | `outbound`는 원래 간선 방향, `inbound`는 역방향, `both`는 각 단계에서 양방향 허용. |
| 대표 경로 | 해당 시작점에서 노드까지 연결 수가 최소인 경로 하나. 동률은 정해진 탐색 순서로 선택. |
| 단순 경로 | 한 경로 안에서 노드를 재방문하지 않는 경로. 서로 다른 경로는 같은 노드를 사용할 수 있다. |
| 간선 검사 | 현재 노드의 다음 후보 연결을 처리하는 한 번의 작업. 같은 간선도 다른 노드·경로에서 다시 검사할 수 있다. |
| 완료 | 전달된 스냅샷·지정 방향·깊이 범위에서 요청한 탐색을 끝냄. 원본 DB 전체의 완전성을 보장하지 않는다. |

- INV-01: 코어의 공개 타입과 실행 경로에 Vault·저장소·문서·심볼·근거·리비전 필드가 없다.
- INV-02: 입력, 프로세스 전역 상태, 파일, 네트워크, 외부 저장소를 변경하지 않는다.
- INV-03: 동일 그래프와 옵션은 입력 배열 순서와 무관하게 동일 결과·계수·종료 이유를 낸다.
- INV-04: 간선 ID가 다르면 같은 두 노드의 평행 간선도 별도로 보존한다.
- INV-05: 정해진 자원 한도를 넘기기 전에 중단하고 불완전한 결과를 완료로 표시하지 않는다.
- INV-06: BFS 결과는 대표 경로다. 모든 경로나 모든 관계를 반환했다고 주장하지 않는다.
- INV-07: 단순 경로는 간선 ID와 실제 이동 방향까지 보존한다.
- INV-08: 원본의 권한·최신 상태·근거 적합성 판단은 호출자 책임이다.

## 4. 패키지와 공개 인터페이스

패키지 위치는 `packages/graph-search/`, import 이름은 `graph_search`다.
배포명은 사용자 결정에 따라 `nolemy-graph-search`로 지정한다.
독립 wheel에는 `vault_graph`를 포함하지 않는다. 코어의 런타임 의존성은
표준 라이브러리와 `rustworkx`로 제한하고, pytest·NetworkX 등은 개발 환경에만 둔다.
현재 프로젝트가 선언한 rustworkx 범위를 출발점으로 삼되 실제 지원 버전은
최저·최고 버전 검증 후 wheel 메타데이터에 고정한다. 이번 작업은 패키지를 생성하지 않는다.

내부 파일은 `graph_snapshot.py`, `graph_traversal.py`, `path_traversal.py`,
`search_results.py`, `errors.py`, `__init__.py`, `py.typed`로 제안한다.
공개 심벌은 아래 데이터 타입, 생성 API, 두 탐색 함수, 오류뿐이다.
rustworkx 객체·노드 인덱스·visitor는 공개하지 않는다. 엔진 선택 옵션도 만들지 않는다.

```python
NodeId = str
EdgeId = str
Direction = Literal["outbound", "inbound", "both"]

@dataclass(frozen=True)
class Edge:
    id: EdgeId
    source_id: NodeId
    target_id: NodeId

@dataclass(frozen=True)
class GraphLimits:
    max_nodes: int
    max_edges: int
    max_id_bytes: int
    max_total_id_bytes: int

@dataclass(frozen=True)
class SearchOptions:
    direction: Direction
    max_depth: int
    max_nodes: int
    max_edge_examinations: int

@dataclass(frozen=True)
class PathOptions:
    direction: Direction
    max_depth: int
    max_paths: int
    max_edge_examinations: int

GraphSnapshot.build(
    *, node_ids: tuple[NodeId, ...], edges: tuple[Edge, ...], limits: GraphLimits
) -> GraphSnapshot

graph_search(
    graph: GraphSnapshot, *, source_id: NodeId, options: SearchOptions
) -> SearchResult

search_paths(
    graph: GraphSnapshot, *, source_id: NodeId, options: PathOptions
) -> PathTraversal
```

코드 블록은 계약의 개요이며, 바로 실행할 수 있는 완성 구현은 아니다.
GraphSnapshot 생성은 명시적인 준비 작업으로 수행한다. DTO를 만들거나
모듈을 import하는 것만으로 그래프를 구성하거나 I/O 또는 캐시 쓰기를 하지 않는다.

### 입력 검증

입력 배열은 길이가 유한한 tuple만 받는다. 임의의 iterator, callback, 속성 사전은 허용하지 않는다.
중복 노드 ID, 잘못된 타입, 빈 문자열, UTF-8로 변환할 수 없는 값, 등록되지 않은 끝점을 거부한다.
잘못된 타입의 EdgeId와 중복 EdgeId도 거부하며, 같은 EdgeId가 같은 행에 반복되어도 거부한다.
ID에 strip, casefold, Unicode 정규화를 적용하지 않는다. 공백만 있는 ID는 거부하고,
그 밖의 공백은 식별자의 일부로 보존한다.

빈 그래프, 고립 노드, 자기 루프, 평행 간선은 허용한다.
시작 노드가 없으면 `UnknownNodeError`를 반환한다. 코어 API는 시작점을 하나만 받는다.
호출자가 시작점마다 별도로 실행해 여러 시작점의 최단 거리가 섞이지 않게 한다.

정수 옵션에는 bool을 허용하지 않는다. 깊이는 0 이상, 노드 및 경로 상한은 1 이상,
간선 검사 상한은 0 이상이어야 한다. GraphLimits의 각 값은 1 이상이어야 한다.
GraphLimits는 네이티브 그래프를 만들기 전에 노드 수, 간선 수, 각 ID의 UTF-8 바이트 수,
ID가 나타나는 모든 위치의 총 바이트 수를 검사한다.
총 바이트 수에는 node_ids와 각 Edge의 id, source_id, target_id가 등장하는 모든 위치를 포함한다.
이 문서에서 상한값을 임의로 정하지 않는다. 호출자가 명시하며, 예시 값은 fixture에만 적용한다.

## 5. 스냅샷과 결정성

입력을 검증한 뒤 노드와 간선을 각각 ID 순서로 등록한다.
ID는 Python의 str 비교 규칙으로 정렬하므로 로캘이나 입력 순서에 영향을 받지 않는다.
내부 rustworkx 그래프와 대응표는 공개하지 않으며, 변경 API도 제공하지 않는다.
공개 결과에는 전달받은 입력 tuple, 외부 dict, 그래프의 변경 가능한 참조를 보관하지 않는다.

방향별 후보는 `(next_node_id, edge_id, reversed)` 오름차순으로 준비한다.
자기 루프는 `both`에서도 같은 방향 후보를 중복 생성하지 않고 forward로 처리한다.
평행 간선은 ID별로 보존하며, 서로 반대 방향인 별도 간선도 구분한다.
`both`는 그래프 전체의 방향을 한꺼번에 뒤집는 옵션이 아니다. 각 단계에서 역방향 이동을 허용한다.

내부 구현은 rustworkx의 열거 순서나 visitor 중단 동작을 공개 계약으로 삼지 않는다.
정렬을 마친 인접 후보를 사용해 BFS 큐와 단순 경로용 명시적 스택을 제어한다.
재귀 한도에 의존하지 않는다. 준비된 스냅샷은 여러 호출이 동시에 공유할 수 있으며,
방문 집합, 큐, 스택, 계수는 호출마다 따로 관리한다.
하나의 PathTraversal을 여러 실행 흐름에서 동시에 소비하는 방식은 지원하지 않는다.

## 6. graph_search: 대표 경로 탐색

시작점을 깊이 0으로 방문하고 FIFO BFS로 아직 방문하지 않은 노드를 추가한다.
각 노드는 한 번만 추가하며, 처음 발견했을 때의 부모 노드와 간선을 저장한다.
깊이 상한에 도달한 노드에서는 간선을 검사하지 않는다. 깊이 0이면 시작점만 반환하고 완료한다.

SearchResult는 다음 불변 데이터를 가진다.

| 필드 | 의미 |
| --- | --- |
| source_id / direction / max_depth | 결과를 만든 검색 범위 |
| visits: tuple[Visit, ...] | BFS 발견 순서의 node_id, depth, parent_id, parent_edge_id, reversed |
| stop_reason | `completed` / `node_limit` / `edge_limit` |
| examined_edges | 실제로 처리한 후보 수 |
| discovered_nodes | 시작점을 포함한 visits 수 |

시작점 `Visit`의 부모 정보는 None이다. 역방향으로 이동한 부모 간선에는
`reversed=True`를 기록한다. 자기 루프나 이미 방문한 노드로 향하는 후보는
노드를 추가하지 않고 검사 횟수만 늘린다.

`result.path_to(target_id)`는 방문한 노드에 대해 `PathLookup(status='found', path=...)`를 반환하고,
그 밖에는 `status='not_observed', path=None`을 반환한다.
이 결과만으로는 노드 미등록, 도달 불가, 깊이 범위 밖, 상한으로 인한 생략을 구분할 수 없다.
호출자는 stop_reason과 검색 범위를 함께 확인해야 하며, 미관측을 “절대 도달할 수 없음”으로 해석해서는 안 된다.
시작점으로 가는 경로는 노드 하나와 단계 0개로 구성된다.
반환된 각 노드까지의 최소 간선 수는 보장하지만, `both`에서는 원래 유향 그래프의 도달 가능성을 증명하지 않는다.

Path는 `node_ids: tuple[str, ...]`와 `steps: tuple[TraversalStep, ...]`를 가진다.
TraversalStep에는 `edge_id, from_id, to_id, reversed`가 들어간다.
역방향 이동에서도 원래 간선의 끝점은 바꾸지 않는다. path_to는 필요할 때 부모 정보를 따라 경로를 복원한다.

### 상한에 따른 중단

간선을 검사하기 전에 edge_limit을 확인한다. 검사할 수 있으면 계수를 늘리고,
방문하지 않은 다음 노드를 추가하기 직전에 node_limit을 확인한다.
중단 사유가 겹치면 이 순서로 판정한다. 시작점도 max_nodes에 포함한다.
개수가 상한과 같아졌다는 이유만으로 중단하지 않는다.
다음 작업이 상한을 넘을 때 해당 limit을 반환한다.
깊이 조건에 따라 큐 처리가 끝나면 completed다.

예: `A→B`에서 max_nodes=2, 깊이 1이면 completed다.
`A→B→C`에서 max_nodes=2, 깊이 2이면 node_limit이다.
간선 검사 상한이 0이어도 시작점이 고립되어 있거나 깊이가 0이면 completed다.
다음 후보가 있으면 edge_limit이다. 벽시계 시간으로 도중에 끊는 동작은 넣지 않는다.
시간 상한이 필요하면 호출자가 프로세스를 격리해야 하며, 강제 종료된 작업에서 성공 결과를 만들지 않는다.

## 7. search_paths: 제한된 여러 경로 탐색

이 별도 API는 기존의 여러 경로와 점수 계산을 지원한다. BFS에 모든 기능을 넣는 mode는 추가하지 않는다.
최단 경로뿐 아니라 시작점부터 최대 깊이까지 이어지는 비어 있지 않은 모든 단순 경로를
후보 순서에 따른 DFS 전위 순회로 하나씩 yield한다. 시작점만 있는 경로는 yield하지 않는다.
도착 노드를 지정하지 않으며, 중간 노드까지의 경로도 반환 대상이다.
node_ids와 `(edge_id, reversed)`의 순서가 경로의 동일성을 결정한다.
평행 간선의 ID가 다르면 노드 순서가 같아도 서로 다른 경로다.

현재 경로 안의 방문 집합만으로 순환을 막는다. 다른 경로에서 이미 방문한 노드는 제외하지 않는다.
자기 루프는 경로에 포함하지 않지만, 깊이 상한 전까지 검사했다면 검사 횟수에 포함한다.
최대 깊이가 0이면 결과 없이 completed 상태가 된다.

PathTraversal은 한 번만 소비할 수 있는 Iterator[Path]이며, 다음 상태를 가진다.

```text
created → running → completed | path_limit | edge_limit | cancelled | failed
```

- 생성 시 시작점과 모든 option을 검증한다. 순회 중에는 I/O나 사용자 callback을 실행하지 않는다.
- `summary`는 순회가 끝나기 전에는 None이고, 종료 후에는 변경할 수 없는 PathSummary다.
- PathSummary에는 stop_reason, emitted_paths, examined_edges가 들어간다.
- 간선 상한은 후보를 처리하기 전에, 경로 상한은 다음 유효 경로를 yield하기 직전에 확인한다.
- 마지막 경로 수가 max_paths와 같더라도 더 만들 유효 경로가 없으면 completed일 수 있다. 다음 유효 경로가 있으면 path_limit이다.
- limit에 도달하면 StopIteration으로 끝나며 summary에 이유를 남긴다. 정상 완료와 같은 상태로 취급하지 않는다.
- `close()`는 미완료 순회를 cancelled 상태로 만든다. 종료 후에는 반복 호출해도 상태를 바꾸지 않는다.
- context manager를 제공한다. 명시적 close 또는 with 블록을 벗어날 때만 미완료 순회를 cancelled로 만든다.
- 반복문에서 break한 뒤 with 블록 안에 머물거나 명시적 close 없이 소비를 잠시 멈추면 summary는 None이며 재개할 수 있다. Iterator가 소비자의 중단을 스스로 감지한다고 가정하지 않는다.
- `next()` 내부에서 오류가 나면 GraphSearchError를 던지고 failed 상태가 된다. 그 뒤에는 재개할 수 없다.
- 종료 후 next를 다시 호출하면 StopIteration을 던진다. GC의 정리에 의존하지 않는다.

코어는 모든 경로를 메모리에 모으지 않는다. 소비자도 max_paths를 무제한으로 두지 말고 summary를
반드시 확인한다. 상한에서 멈춘 DFS가 처음 반환한 K개 경로를 “점수 상위 K개”로 해석해서는 안 된다.

## 8. 오류와 읽기 전용 경계

| 조건 | 공개 결과 | 재시도 / 외부 영향 |
| --- | --- | --- |
| 타입, 값, ID, 끝점이 잘못됨 | InvalidGraphError / InvalidSearchError | 입력을 수정한다. 부분 snapshot이나 결과는 반환하지 않는다. |
| 생성 중 GraphLimits 초과 | GraphCapacityError | 입력 범위나 명시한 상한을 조정한다. 간선을 조용히 버리지 않는다. |
| 시작점이 등록되지 않음 | UnknownNodeError | 호출자가 이름과 범위를 확인한다. |
| 탐색 중 작업 상한 도달 | 부분 결과와 limit 사유 | 호출자가 범위를 줄이거나 명시적으로 다시 실행한다. |
| 명시적 close 또는 미완료 상태의 with 블록 종료 | cancelled | 완료 또는 완전한 순위 결과로 공개하지 않는다. 잠시 미소비한 상태는 종료가 아니다. |
| 내부 오류 | GraphSearchError, PathTraversal은 failed | 원래 예외를 cause로 보존한다. 성공한 빈 결과로 바꾸지 않는다. |
| 메모리 고갈 또는 프로세스 강제 종료 | 성공을 보장하지 않음 | MemoryError나 OS 종료를 정상적인 부분 결과처럼 꾸미지 않는다. |

공개 오류는 모두 `GraphSearchError` 계열로 통일하고, code와 안전한 설명을 제공한다.
예상하지 못한 구현 오류를 포괄적으로 숨기지 않는다. 인증, Vault 경계, DB 장애는
코어가 다루는 조건이 아니다. 스냅샷 생성과 검색은 파일, DB, 네트워크, 모델 로딩,
로그 전송 또는 숨겨진 인덱스 갱신을 수행하지 않는다.

## 9. 자원과 성능 설계

준비 단계에서는 입력으로 받은 유효 노드 수 V, 간선 수 E, ID 총 바이트 수가 상한 안에 드는지 먼저 확인한다.
정렬과 인접 목록 준비에는 `O(V log V + E log E)`, 보관에는 `O(V+E+ID bytes)` 공간이 든다.
입력 tuple 자체의 메모리는 호출자가 부담하며, 이 검사를 통해 이미 할당된 메모리를 되돌릴 수는 없다.
RSS를 엄격히 제한해야 한다면 별도 프로세스에 OS 메모리 상한을 적용한다.

준비 후 BFS는 최대 간선 검사 횟수와 방문 노드 상한으로 작업량을 제한한다.
경로 복원 비용은 해당 경로의 길이에 비례한다. PathTraversal의 작업 메모리는 현재 경로와
DFS 스택에 `O(min(depth,V))`가 들며, 스냅샷 보관 공간이 추가로 필요하다.
단순 경로 수는 매우 커질 수 있으므로 깊이, yield 수, 검사 횟수 상한을 필수로 둔다.
매번 전체 그래프를 다시 정렬하거나 모든 경로를 list에 담는 구현은 허용하지 않는다.

기존 SPEC의 검증용 p95 목표를 이 모듈의 목표로 가져오지 않는다.
준비, BFS, 경로 열거, 경로 복원, 어댑터의 실행 시간과 최대 RSS를 따로 측정한다.
측정에는 그래프 크기, 노드 차수, 경로 수, Python/rustworkx 버전, OS/CPU, 반복 횟수를 기록한다.
대상 호스트와 수치 SLO는 Open Decisions로 남겨 두며, 근거 없는 성능 보장을 하지 않는다.

## 10. 사용 예

```python
graph = GraphSnapshot.build(
    node_ids=("A", "B", "C"),
    edges=(Edge("e1", "A", "B"), Edge("e2", "B", "C")),
    limits=GraphLimits(3, 2, 32, 256),  # 이 fixture에만 적용하는 상한
)
result = graph_search(
    graph,
    source_id="A",
    options=SearchOptions("outbound", 2, 3, 2),
)
assert result.stop_reason == "completed"
lookup = result.path_to("C")
assert lookup.status == "found" and lookup.path is not None
assert lookup.path.node_ids == ("A", "B", "C")

with search_paths(graph, source_id="A", options=PathOptions("outbound", 2, 2, 2)) as paths:
    for path in paths:
        consume(path)  # 호출자 측 처리이며, 코어에 callback을 전달하는 API는 아니다.
assert paths.summary.stop_reason == "completed"
```

관계 종류, 허용 범위, 근거 상태는 그래프를 만들기 전에 호출자가 선택한다.
ID 대응표도 호출자가 보유한다. ID에 특정 분야의 단어가 들어 있어도
코어는 그 내용을 해석하지 않고 문자열 비교만 수행한다.

## 11. 수용 기준과 검증 계획

| ID | 기준 | 필요한 증거 |
| --- | --- | --- |
| FA-01 | 별도 환경에서 wheel만 설치해 API를 사용할 수 있다. | Vault Graph가 없는 새 환경에서 wheel 설치, import, 예제 실행. |
| FA-02 | 입력 오류와 용량 초과를 그래프 구성 전에 거부한다. | 타입, bool, 중복 ID, 누락된 끝점, UTF-8, 각 용량 경계에 대한 공개 API 테스트. |
| FA-03 | BFS의 도달 노드, 최소 거리, 방향이 정확하다. | 작은 그래프의 전체 탐색 결과를 독립 oracle과 비교. |
| FA-04 | 같은 거리의 대표 경로와 순서를 재현할 수 있다. | 입력 순서를 바꾸거나 병렬·별도 프로세스에서 반복해도 같은 결과. |
| FA-05 | 자기 루프, 평행 간선, 역방향 이동을 정확히 처리한다. | 간선 ID와 reversed를 포함한 경로 검증. |
| FA-06 | 상한에 정확히 도달한 완료와 초과로 인한 중단을 구분한다. | 깊이 0, 용량 1, 검사 0, 다음 유효 경로 유무, 중복 후보의 경계 테스트. |
| FA-07 | 제한 안에서 비어 있지 않은 모든 단순 경로를 정확히 열거한다. | 작은 그래프의 독립 DFS oracle과 경로 집합 비교, 평행 간선별 경로 검증. |
| FA-08 | 부분 결과나 미관측 상태를 완전한 부재로 취급하지 않는다. | not_observed, 각 stop_reason, cancel/failed 종료 상태 테스트. |
| FA-09 | 입력·출력과 외부 상태를 변경하지 않는다. | 불변 API, I/O 금지, 병렬 읽기 테스트. |
| FA-10 | 계수가 실제 작업량과 일치하고 모든 경로를 내부에 저장하지 않는다. | counter oracle, 높은 차수와 경로 급증 fixture, 메모리 측정. |
| FA-11 | 기존 이용 경로와 호환된다. | [연동 설계의 IT-01–IT-12](2026-10-03-graph-search-integration-ko.md#8-연동-수용-기준과-검증)의 증거. |

기능 테스트 fixture에는 고립 노드, chain, diamond, cycle, star, dense DAG,
자기 루프, 같은 끝점을 잇는 평행 간선, 반대 방향 간선, 비ASCII ID를 포함한다.
작은 그래프 oracle은 제품 코드를 호출하지 않는다. BFS는 NetworkX와 비교하고,
단순 경로는 테스트 코드의 명시적 전수 탐색과 비교한다. NetworkX는 테스트 의존성으로만 사용한다.
순서와 종료 조건은 전용 oracle로 비교한다. 같은 rustworkx 코드를 서로 비교하고
독립 검증이라고 부르지 않는다. 상한을 둔 BFS의 방문 결과는 제한 없는 BFS 결과의 결정적인 앞부분이어야 한다.

### 검증 단계

FA-06에는 `A→B`, `B→A`, 깊이2, max_paths=1, 검사 상한2를 포함한다.
남은 후보가 순환으로 제외되므로 경로1건과 completed를 반환해야 한다.
FA-08에는 with 블록 안에서 break한 뒤 재개하는 경우, 블록 종료로
cancelled가 되는 경우, 명시적 close 이후 재개 불가를 각각 포함한다.

1. 공개 API 단위 검증: FA-02–FA-08의 정상, 오류, 경계 사례.
2. 결정성과 속성 검증: fixture 순열, 작은 그래프 전수 탐색, 도달 거리, 경로와 간선 대응.
3. 경계 검증: import와 검색 중 파일 쓰기, socket, subprocess를 금지하고,
   불필요한 Vault/DB/LLM/MCP 모듈이 로드되지 않는지 확인한다.
   최초 wheel import에 필요한 실행 환경의 모듈 읽기는 별도로 구분한다.
4. 배포 검증: wheel 내부 파일, Requires-Dist, py.typed, 새 환경에서의 smoke test.
5. 운영 검증: 스냅샷 동시 읽기, Iterator 독립성, fault/cancel, 성능과 RSS.
6. 연동 검증: 공개 CLI/MCP/HTTP 결과, 근거, 안전성, 순위의 차이를 비교한다.

## 12. 설계 판단 제안과 대안

| ID | 제안 | 이유 / 대안 / 영향 |
| --- | --- | --- |
| D-01 | 타입을 ID와 끝점으로 제한한다. | 임의 payload나 kind를 받는 것보다 도메인 정보 유입과 callback을 통한 숨은 I/O를 막기 쉽다. 어떤 값을 선택할지는 이용자가 정한다. |
| D-02 | BFS와 단순 경로를 별도 API로 제공한다. | BFS만으로는 기존의 여러 경로 결과를 얻을 수 없다. 만능 mode보다 각 결과의 의미가 분명하다. |
| D-03 | 시작점을 하나만 받는다. | 여러 시작점의 최단 거리를 합칠 때 생기는 모호함을 피하고, 기존 seed 처리는 연동 계층에 남긴다. |
| D-04 | 불변 snapshot과 호출별 상태를 사용한다. | 변경 가능한 Graph를 공개하는 것보다 반복·병렬 사용 조건이 단순하다. |
| D-05 | 용량과 작업 상한을 명시한다. | 시간 기준 중단보다 결과를 재현하기 쉽다. 용량 제한이 시간이나 OS 메모리 보장을 대신하지는 않는다. |
| D-06 | rustworkx를 비공개 의존성으로 둔다. | 기존 기술은 활용하되 열거 순서는 공개하지 않는다. NetworkX로의 전환이나 backend 선택은 추가하지 않는다. |
| D-07 | PathTraversal은 streaming 방식으로 제공하고 종료 요약을 필수로 한다. | 모든 경로를 모으는 방식보다 소비자가 top-K를 관리하기 쉽다. 일찍 중단하면 cancelled 상태가 된다. |

이 항목들은 이번 상세 설계의 제안이며, 기존 승인 기록에 추가하지 않는다.

## 13. 가정과 Open Decisions

| ID | 가정 / 미결 사항 | 사실이 아닐 때의 영향 / 확인 방법 |
| --- | --- | --- |
| ASM-01 | 메모리에 올릴 수 있는 유한 그래프가 대상이다. | 외부 DB를 지연 탐색해야 한다면 별도 계약이 필요하다. 현재 투영 입력과 예상 사용 사례를 확인한다. |
| ASM-02 | 첫 버전은 Python 3.12와 동기 API로 충분하다. | 다른 언어나 async 요구가 있으면 배포 및 호출 계약을 다시 검토한다. 이용자 요구를 확인한다. |
| Q-01 | 운영 호스트, 대표 부하, 시간/RSS SLO | 먼저 벤치마크를 측정하고 실측값으로 정할 것을 권장한다. 성능 통과를 선언하기 전에 확정해야 한다. |
| Q-02 | 기존 투영에서 발견한 모호한 ID와 동률 순서 처리 | v1 호환성을 우선하고, 수정은 별도 버전과 명시적 승인을 권장한다. 자세한 내용은 연동 설계 §6을 참고한다. |

미정인 출시 판단을 설계 문서 제출이나 구현 승인과 혼동하지 않는다.
질문 중 I/O 권한 확인, DB 트랜잭션, 영구 데이터 이전은 코어 범위가 아니며,
연동 계층의 기존 책임으로 확인했다. 운영 수치와 기존 동작 수정은 제안으로 남긴다.

## 14. 구현 시 검증 명령 계획

현재 연동 테스트는 다음 명령으로 확인할 수 있다. 이번에는 실행하지 않았다.

```bash
uv run --python 3.12 pytest -q tests/test_graph_projection.py tests/test_graph_retrieval_service.py tests/test_multi_vault_graph_retrieval.py tests/test_search_include_graph.py tests/test_graph_retrieval_read_only_boundary.py
uv run --python 3.12 ruff check src tests
uv run --python 3.12 mypy src tests
uv run --python 3.12 pytest -q
uv build
uv run --python 3.12 --with twine python -m twine check dist/*
```

독립 package를 추가한 뒤 사용할 검증 명령은 다음과 같다. 아직 대상 package가 없으므로
실행 가능하거나 검증된 명령으로 취급하지 않는다. package의 pyproject에는 pytest, ruff, mypy와
테스트 전용 NetworkX를 정의하고, CI에도 해당 package 검사를 명시적으로 추가한다.

```bash
uv run --project packages/graph-search --python 3.12 pytest -q packages/graph-search/tests
uv run --project packages/graph-search --python 3.12 ruff check packages/graph-search/src packages/graph-search/tests
uv run --project packages/graph-search --python 3.12 mypy packages/graph-search/src packages/graph-search/tests
uv build --project packages/graph-search --out-dir packages/graph-search/dist
```

새 환경 검사는 실제 생성된 wheel 경로를 사용한다. 별도 디렉터리의 새 venv에
wheel과 선언된 runtime 의존성만 설치하고 PYTHONPATH를 제거한 뒤 사용 예제를 실행한다.
`vault_graph`를 import할 수 없어야 하며, Vault, catalog, graph-home이 없어도 실행되어야 한다.
성능 측정 명령과 지원 버전 조합은 구현 경로를 확정한 뒤 기록한다. 실행하지 않은 검사를 passed로 표시하지 않는다.

## 15. Done When

상세 API, 경계, 오류, 계수, 중단 규칙, 배포 방법, 성능 측정 방법을 정의하고,
FA와 테스트를 연결해야 한다. 별도 연동 계약과 SPEC 링크도 포함한다.
독립 검토에서 확인된 구체적 모순을 고친 뒤 링크와 차이를 확인하면 설계 제출을 완료한다.

구현 완료는 FA-01–FA-11의 증거를 갖추고, Q-02 관련 동작을 임의로 바꾸지 않은 채
독립 wheel과 기존 공개 경로를 모두 검증했을 때 인정한다.
production-ready를 선언하려면 Q-01의 측정 대상과 수치 SLO를 추가로 확정하고,
성능, 메모리, 동시 실행, 배포 환경의 합격 증거를 제시해야 한다.

## 16. 외부 참고 자료

2026-10-03에 공식 자료를 확인했다. 아래 자료는 설계 참고용이며 공개 API로 그대로 사용하지 않는다.

- [NetworkX bfs_edges](https://networkx.org/documentation/stable/reference/algorithms/generated/networkx.algorithms.traversal.breadth_first_search.bfs_edges.html): 탐색 트리의 간선과 전체 간선을 구분한다.
- [NetworkX all_simple_paths](https://networkx.org/documentation/stable/reference/algorithms/generated/networkx.algorithms.simple_paths.all_simple_paths.html): 경로에서 노드 반복을 허용하지 않는 규칙과 열거량에 관한 주의점을 참고한다.
- [rustworkx bfs_search](https://www.rustworkx.org/apiref/rustworkx.bfs_search.html): visitor, 중단, 여러 시작점의 동작을 참고한다. 호출 순서를 별도 계약에 암묵적으로 포함하지 않는다.
- [igraph graph analysis](https://python.igraph.org/en/latest/analysis.html): BFS의 계층 및 부모 정보와 경로 검색을 구분한다.
