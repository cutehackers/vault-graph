# graph_search와 graph_document 구현 순서

- Plan ID: GRAPH-MODULES-ORDER-20261004
- Status: Complete — 필수 순서1–7의 구현·연동·복구·로컬 운영·독립 리뷰·wheel 검증을 완료했다. 배포명 충돌은 `nolemy`로 해소했다. 순서8의 의미 추출은 대안 설계까지 포함하며 실제 모델 구현은 이번 필수 범위가 아니다.
- Created: 2026-10-04
- Source: 패키지와 연동 스펙을 함께 포함해 구현 순서를 조율하라는 현재 사용자 요청

## 1. 적용 계약과 조율 원칙

| 코드 | 구현 기준 |
| --- | --- |
| GS | [graph_search 독립 패키지](../specs/2026-10-03-graph-search-ko.md) |
| GS-INT | [graph_search 기존 시스템 연동](../specs/2026-10-03-graph-search-integration-ko.md) |
| DG | [graph_document 독립 패키지](../specs/2026-10-04-graph-document-ko.md) |
| DG-INT | [graph_document 기존 시스템 연동](../specs/2026-10-04-graph-document-integration-ko.md) |

핵심 의도는 **각 모듈이 하나의 기능을 독립적으로 제공하도록 분리하는 것**이다.
단순히 파일이나 wheel을 나누는 것이 아니라 독립 입력·출력·의존성·수명주기·검증 기준을 갖춰야 한다.
여기서 atomic은 소비자가 하나의 기능 단위로 사용할 수 있다는 뜻이며 DB transaction 원자성만을 뜻하지 않는다.

먼저 두 패키지 각각의 완전한 독립 사용 경로를 구현한다. 그 뒤 모듈 간 연결과 기존 시스템 연동을
각각 별도 단계로 구현한다. 기존 시스템에 연결되어야만 기능 검증이 가능한 패키지는 목표를 달성한 것이 아니다.
기존 탐색과 저장의 기본 경로는 따로 전환하여 회귀 원인을 구분한다.

각 단계는 실행 증거가 갖춰져야 끝난다. 아래 코드는 작업 순서이며 별도 승인된 Vertical Slice 계약이 아니다.
기존 네 스펙의 범위·승인 상태·수용 기준은 이 계획으로 변경하지 않는다.

## 2. 독립 모듈 분리의 완료 기준

| 코드 | 모듈 책임 | 독립 완료를 입증할 사용 경로 |
| --- | --- | --- |
| 독립1 | graph_search: 그래프 연결과 경로 계산 | Vault·문서·DB·LLM 없이 wheel과 노드·간선 입력만으로 탐색. |
| 독립2 | graph_document: 문서에서 근거 있는 그래프 생성·갱신·조회 | Vault·graph_search 없이 일반 문서를 받아 지정 DB에 저장하고 재개방·근거 조회. |
| 독립3 | search_bridge: 두 모듈의 입력·결과 연결 | 두 wheel만 설치해 DocumentGraphSnapshot→GraphSnapshot→경로→같은 snapshot 근거 조회. |
| 독립4 | Vault 어댑터: 기존 시스템 계약과 일반 모듈 사이 변환 | scope·ID·근거·순위·MetadataStore 타입이 패키지 core로 유입되지 않음을 검사. |

search_bridge와 Vault 어댑터는 연결 기능이다. 각각을 추가 독립 배포 패키지로 만들 필요는 없다.
연결 코드 없이 core의 기본 기능을 사용하고 검증할 수 있어야 한다.
기존 구현의 재사용은 계산과 규칙을 해당 모듈로 가져오는 방식이며 vault_graph에 대한 역방향 import는 금지한다.

## 3. 권장 구현 순서

| 순서 | 작업과 적용 스펙 | 선행 조건 | 종료 증거 |
| --- | --- | --- | --- |
| 순서1 | 기존 동작 기준선과 호환성 fixture 확보 — GS-INT, DG-INT | 현재 코드·테스트 확인 | 원래 엔진의 고정 oracle, 공개 응답 golden, 테스트 환경·결과와 데이터 경계 기록. |
| 순서2 | graph_search 독립 패키지 구현 — GS | 순서1 | 노드·간선 snapshot, BFS, search_paths, 제한·종료 규칙과 wheel 검증. GS FA-01–FA-10. |
| 순서3 | graph_document 기본 저장·조회 패키지 구현 — DG | 순서1, SQLite 정책 결정 | 일반 Document·규칙 추출·기여 갱신·삭제·CAS·근거·DocumentGraphSnapshot·독립 wheel. DG-FA-01–10, DG-FA-12. |
| 순서4 | 두 독립 패키지의 search_bridge 연결 — DG §9 | 순서2, 순서3 | 두 wheel만 설치해 문서→그래프→경로→같은 revision 근거 조회. DG-FA-11. |
| 순서5 | graph_search를 기존 투영 계약에 연결 — GS-INT | 순서2, 순서4 | 기존 DB를 사용한 adapter·실제 factory·공개 응답 검증. IT-01–IT-12와 GS FA-11. 전환 gate 통과 후 탐색 엔진만 변경. |
| 순서6 | MetadataStore/Vault 공급 및 호환 읽기 어댑터 구현 — DG-INT | 순서5, 순서4, cache/manifest 정책 결정 | 기존 chunk·ID·근거·정규화 복원, 새 DB 병행 검증, 전체/증분/삭제·manifest 복구. DG-IT-01–06, DG-IT-08–09. |
| 순서7 | 전체 공개 경로 검증 후 문서 그래프 경로 전환 — DG-INT | 순서6, 운영 측정·전환 판단 | DG-IT-07·10, DG-FA-13·14, 전체 회귀·배포·rollback. 기존 본문 조회 유지. |
| 순서8 | 필요할 때 의미 추출 어댑터 평가·추가 — DG §15 | 기본 경로 검증 완료, 별도 의미 추출 구현 계약 | DG-SEM-01–05. 모델·근거 정확도·비용·재현성의 평가 gate 통과. 기본 규칙은 유지. |

순서8은 첫 버전 완료의 필수 선행 조건이 아니다. 현재 요구는 의미 추출 대안을 설계에 포함하는 것이며,
모델 추출기를 구현하거나 기본 활성화하는 승인까지 포함하지 않는다.

## 4. 단계별 구현 경계

### 순서1: 비교 기준 준비

현재 RustworkxGraphProjection을 새 adapter가 호출하는 wrapper로 바꾸기 전에 테스트용 기준을 고정한다.
ID 충돌, 동점 순서, 평행 간선, 역방향, 근거 없음, 범위, 제한 중단 fixture를 확보한다.
GS의 순수 결정성 기준과 legacy 입력순 의존 호환성 기준은 다르게 검증한다.
기존 GraphIndexer와 SQLite 결과도 canonical export로 비교할 수 있도록 준비한다.
과거 테스트 개수나 이전 실행 결과를 현재 전체 기준선으로 사용하지 않는다.

### 순서2: 탐색 패키지 완성

GraphSnapshot과 입력 검증을 만든 뒤 BFS와 모든 제한된 단순 경로 열거를 구현한다.
BFS 대표 경로만 완료하고 기존 복수 경로 adapter를 연결하지 않는다.
새 환경 설치, independent oracle, 입력 불변성, 제한 경계·iterator 종료, counter·메모리를 검증한다.
GS FA-11은 순서5에서 완료하므로 순서2 종료를 GS 계약 전체 완료라고 기록하지 않는다.

### 순서3–4: 문서 그래프와 독립 패키지 연결

순서3에서는 DB 생명주기까지 포함한 독립 기능을 완성한다. 문서별 기여와 공유 관계·alias 철회,
원문 버전만 바뀐 update, 추출 결과 충돌, CAS·transaction failure를 검증한다.
read는 DocumentGraphSnapshot을 만들고 이후 DB 변경과 무관하게 노드·근거를 유지한다.

순서4에서 optional search extra와 prepare_search를 연결한다. 같은 snapshot에서 시작 항목을 찾고
실제 graph_search 결과의 간선 ID·역방향·부분 상태를 원문 근거 참조와 연결한다.
이 단계까지 DG-M-01의 DG-FA-01–12 범위를 충족한다. DG-FA-13·14는 순서6–7에서 완료한다.

### 순서5: 기존 저장소를 유지한 탐색 연동

VaultGraphProjectionAdapter가 기존 GraphProjectionInput을 순수 그래프로 변환하고
search_paths 결과를 기존 점수·순위·ID·build hash로 복원한다.
GraphStore와 MetadataStore는 그대로 사용한다. MetadataStore에서 근거를 확인한 관계만 탐색에 넣는다.
후보 factory와 실제 CLI/MCP/HTTP를 검증한 뒤 별도 전환 gate를 통과해야 기본 탐색 경로를 바꿀 수 있다.
승인이 지연되면 후보 adapter 검증 상태를 유지한다. DB 변경 없이 기존 엔진으로 되돌릴 수 있어야 한다.

### 순서6: 기존 문서 공급과 저장 연동

MetadataStore의 문서별 모든 chunk를 일반 문서로 조합하고 legacy-v1 profile을 적용한다.
같은 기존 ID·confidence·status·anchor로 복원하는 전체 revision manifest를 만든다.
증분 갱신은 이전 전체 manifest에서 변경 문서만 교체하며 DB commit과 manifest 게시 실패를 각각 검증한다.
Vault 연동은 max_excerpt_chars=0을 유지하고 본문을 MetadataStore에만 보관한다.
새 DB는 별도 파생 cache에서 비교하며 기존 DB를 조회 기준으로 유지한다.
부분 문서 입력이나 로드 실패로 기존 관계를 삭제하지 않는다.
이 단계는 DG-M-02–03에 해당한다.

### 순서7: 공개 경로와 전환

실제 서비스 주입으로 related, decision-trace, include-graph, plain search, context/answer 소비 경로를 검증한다.
GS 연동의 모든 IT 항목을 새 문서 그래프 경로에서도 확인한다. 기존 DB 경로에서 통과한 결과만으로 대체하지 않는다.
읽기 전용 조회가 새 DB 색인을 암묵적으로 실행하거나 쓰지 않는지도 확인한다.

문서 공급→새 DB→snapshot→legacy 응답 변환→탐색→MetadataStore 근거 조회의 전체 경로가 검증되어야 한다.
운영 측정과 별도 전환 판단 후 새 저장·조회 경로를 선택한다. 오래된 기존 DB로 즉시 rollback하지 않는다.
전환 후 원문이 바뀌었다면 기존 full 색인과 readiness 확인을 거쳐 rollback한다.
이 단계는 DG-M-04–05에 해당한다. 기존 DB나 엔진 제거는 별도 작업이다.

## 5. 병렬 진행 가능 범위

순서1 이후 순서2와 순서3의 코어 작업은 독립적으로 진행할 수 있다.
다만 SQLite 정책을 먼저 확정하고, 공개 타입·ID·snapshot 계약 변경은 한 담당자가 조율한다.
각 worker의 패키지 파일 소유권을 분리해야 한다. 같은 vault_graph factory·연동 파일을 동시에 수정하지 않는다.
이 문서는 병렬 실행을 시작했다는 기록이 아니다.

graph_document core 작업이 빨리 끝나도 순서4는 graph_search wheel 검증 후 진행한다.
기존 Vault 연동 순서6은 순서5의 adapter 검증을 재사용하되 해당 adapter를 새 domain record 복원과 함께 재검증한다.
기본 전환이 승인되지 않아도 비교용 후보 경로에서 검증 작업을 계속할 수 있다.

## 6. 미결 사항의 결정 시점

| 코드 | 결정할 사항 | 필요한 시점 |
| --- | --- | --- |
| 결정시점1 | GS Q-01, Q-INT-01: 대표 부하·자원 상한·예산 밖 요청의 실패 계약 | 측정은 순서2부터, 기본 탐색 전환 전인 순서5에서 확정. |
| 결정시점2 | GS Q-02 / Q-INT-02: legacy COMP-01–03 수정 여부 | 순서5 차등 검증 전에 정한다. 권장은 첫 버전 보존이며 임의 보정하지 않는다. |
| 결정시점3 | DG-Q-02: SQLite journal·durability·지원 버전 | 순서3 저장 구현 전 확정. 읽기 전용과 장애 fixture로 판단. |
| 결정시점4 | DG-INT-Q-01: 새 DB·manifest 경로, 복구·GC | 순서6 실제 저장 연동 전 확정. Data Home 경계·symlink 검사 포함. |
| 결정시점5 | DG-Q-01·03 / DG-INT-Q-02: 운영 목표·호환 버전·기본 전환 | 측정은 순서3–6부터, 순서7 전환 전 확정. |
| 결정시점6 | 의미 추출 평가집·모델·품질·비용 상한 | 순서8의 별도 구현 계약에서 확정. 첫 버전 구현을 막지 않는다. |

이 결정들은 기존 스펙의 미결 항목을 작업 시점에 배치한 것이다. 이 표 자체가 선택을 승인하지 않는다.

### 배포명 결정과 외부 배포 경계

**배포명1:** 사용자가 `nolemy`를 확정했다. [승인 기록](../../DECISIONS.md#2026-10-04---use-nolemy-for-independent-package-distribution-names)에 따라
`nolemy-graph-search`와 `nolemy-graph-document`를 사용한다. import 이름과 저장소 경로는 유지한다.
root 및 extra 의존성·wheel metadata·lockfile·CI 패키지 선택을 새 배포명으로 변경했다.
기존 `graph-search==0.1.0`은 다른 프로젝트의 배포이므로 runtime 의존성에 사용하지 않는다.
선택한 두 이름은 확인 시점의 PyPI JSON endpoint에서 404였지만 이름 예약을 보장하지 않는다.
[기존 등록 정보](https://pypi.org/project/graph-search/0.1.0/),
[새 프로젝트 등록 절차](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/).

**원래 배포 검증의 범위:** GS §11–13과 DG §10–12는 독립 wheel의 파일·메타데이터,
새 환경의 기본/extra 설치, 공개 경로 및 CI 검사 추가를 요구한다. 실제 PyPI/TestPyPI 게시나
원격 CI 실행은 명시적 완료 조건이 아니다. 순서7의 배포는 이 원래 기준으로 판정한다.
공개 게시를 진행할 때는 새 프로젝트의 Trusted Publisher를 각각 등록해야 한다.
원격 CI·공개 게시·실제 운영 호스트 검증은 이번 로컬 증거로 통과했다고 주장하지 않는다.

## 7. 검증과 진행 기록

각 단계에는 구현한 public behavior, 정확한 실행 명령, 실제 결과, 남은 수용 기준을 기록한다.
기존 스펙의 런타임 명령은 구현 시점에 테스트 파일과 배포 경로를 다시 확인한다.
새 테스트 명령은 파일이 존재하고 실제 실행한 뒤 확정한다.

최초 기준선과 연동 회귀에 사용할 기존 명령은 다음과 같다. 이번 순서 작성에서는 실행하지 않았다.

```bash
uv run --python 3.12 pytest -q
uv run --python 3.12 pytest -q tests/test_graph_projection.py tests/test_graph_retrieval_service.py tests/test_multi_vault_graph_retrieval.py tests/test_search_include_graph.py tests/test_graph_retrieval_read_only_boundary.py
uv run --python 3.12 pytest -q tests/test_entity_extractor.py tests/test_relationship_extractor.py tests/test_graph_indexer.py tests/test_graph_store_contract.py tests/test_sqlite_graph_store.py tests/test_index_service_graph_reconcile.py
uv run --python 3.12 ruff check src tests
uv run --python 3.12 mypy src tests
```

현재 상태는 **필수 순서1–7 완료**다. 일반 패키지의 독립 사용과 실제 Vault 공개 경로,
명시적 document backend 전환·rollback·복구, 고정한 로컬 운영 목표와 패키지 설치를 검증했다.
완료 판정은 이 원래 계약과 측정 환경에 한정하며 외부 게시나 미측정 환경의 운영을 보장하지 않는다.


## 8. 구현 증거와 남은 작업

현재 사용자 요청은 두 독립 패키지와 기존 시스템 연동 구현을 승인하며 gpt-6-astra 사용을 금지한다.
서로 다른 packages 경로를 전담하는 두 구현 에이전트가 독립 작업을 진행하고, root가 기존 시스템 연동과 최종 통합을 맡는다.
검증 seam은 기존 상세 계약의 공개 API·CLI/MCP/HTTP·MetadataStore 근거 조회다.

| 요구 | 상태 | 현재 증거 | 남은 검증 / 다음 작업 |
| --- | --- | --- | --- |
| 기존 기준선 | 완료 | 착수 시 1187 passed, 1 skipped. 고정한 legacy oracle 유지. | 없음. |
| GS FA-01–10 | 완료 | package 24 tests, Ruff·mypy, 별도 Python 3.12 venv wheel 실행. Vault 없음. | 새 환경은 같은 검증 명령 재실행. |
| GS FA-11 / IT-01–12 | 완료 | 240 generated multigraph cases, 15 adapter tests. 실제 CLI/HTTP/MCP 조회와 legacy rollback 결과·상태 해시 일치. | 기존 COMP-01–03의 정책 변경은 별도 scope. |
| DG FA-01–12 | 완료 | normalized SQLite·CAS·두 process·kill/rollback·selection·read-only·별도 wheel·optional bridge. 별도 handle reader/writer 실제 겹침 및 이전 snapshot 불변성 시험도 독립 재실행 통과. | 의미 추출은 별도 구현 범위. |
| DG FA-13–14 / 연동 | 완료 | MetadataStore/GraphStore 및 공개 결과 비교, CLI/HTTP/MCP, 별도 process transport, legacy DB 없이 조회. document→legacy→document 재전환과 schema/profile/누락·잘못된 내부 checkpoint의 명시적 full 복구. 여러 Vault 복구의 all-vaults 요구와 실패 시 이전 세대·원문 보존. 최신 복구 6개 시험은 독립 reviewer도 통과. [RSS·DB 크기](../reports/2026-10-04-graph-module-rss.json) 11개 단계 통과. | 원래 필수 범위의 미완료 항목 없음. |
| 독립 검토·배포 파일 | 완료 | snapshot·근거 검증·복구·동시 읽기/쓰기·RSS·배포명·wheel 증거의 독립 리뷰에서 미해결 blocker 없음. 전체 검사 1309 passed, 1 conditional skip. 새 이름의 세 wheel을 workspace 밖 venv에서 독립 실행하고 root requirement 하나만으로 localhost SimpleIndex에서 SHA256 검증 설치. 세 package의 wheel/sdist 총6개 빌드·twine 통과. Release workflow의 modules→root 순서 및 중복 게시 재시도 설정을 재리뷰. | 원격 CI·실제 공개 게시는 미실행이며 원래 완료 기준이 아니다. |

원래 v1 투영의 COMP-01–03은 보존한다. 기본 adapter는 request의 실제 유한 그래프에서
전량 탐색 가능한 상한을 산출하여 기존 유효 입력을 임의 admission 제한으로 거부하지 않는다.
별도 명시 실행 상한을 지정한 소비자는 초과를 오류로 받으며 완전 순위로 게시하지 않는다.
원문 의미 추출은 기본 구현 범위가 아니며 Protocol과 별도 대안 계약을 유지한다.
SQLite는 새 파생 DB에 rollback journal(DELETE)과 synchronous FULL을 사용하고
read-only 디렉터리·fault·재개방 검증을 수행한다. 기존 sqlite-graph-v2를 migration하지 않는다.
사용자가 유사 제품의 수치를 참고해 목표를 정하도록 위임했다.
[성능 계약](../specs/2026-10-04-graph-modules-performance-ko.md)의 고정한 목표를 모두 충족했으며
[원시 결과](../reports/2026-10-04-graph-modules-performance.json)를 보관했다. 로컬 대표 입력의 목표와 배포 SLA는 구분한다.

현재 부하 측정: macOS 27.0.1 arm64, Python 3.12.11, 3 nodes/500 edges,
250 seed→middle 평행 간선과 250 middle→target 평행 간선, outbound depth=2,
62,750 후보에서 50 반환. tracemalloc을 켠 단일 실행에서 legacy 0.983s/26.96MiB,
새 adapter 3.357s/48.84MiB이며 전체 응답 일치. 계측 오버헤드를 포함한 값으로
운영 SLA나 모든 그래프의 최대 시간·메모리를 증명하지 않는다.

최신 통합 명령 `uv run --python 3.12 pytest -q tests packages/graph-search/tests packages/graph-document/tests`:
**1309 passed, 1 skipped, 21.48s**. 조건부 stdio smoke의 생략과 기존 Starlette httpx deprecation warning 1개는 그대로다.
root·package Ruff, root mypy(341 source files), 두 package의 strict mypy가 통과했다.
`tests/verify_graph_module_wheels.py`는 workspace 밖에서 독립 사용·optional bridge·Vault adapter와 실제 CLI entrypoint를 검증한다.
CI에 package별 검사와 이 wheel 검증 명령을 추가했다. 이번 작업에서는 원격 CI를 실행하지 않았다.

순서7의 운영 경로는 `uv run --python 3.12 python -m tests.benchmarks.measure_document_graph_backend`로
고정한 1,000문서 입력을 20회 측정했다. [원시 결과](../reports/2026-10-04-document-graph-backend-performance.json)는
open p95 1,321.372ms, related p95 128.210ms, Python allocation peak 73.451MiB로 성능8–9를 통과했다.
읽기 전후 Vault와 Data Home의 파일 해시도 동일했다. [실패한 초기 측정](../reports/2026-10-04-document-graph-backend-performance-before-fixes.json)을 보존했다.
성능1–9의 수치는 배포명 변경 전 같은 계산 코드에서 측정한 기록이며 이름 변경을 이유로 수치를 수정하지 않았다.
RSS 보고서는 새 배포명으로 재실행했다. 이 결과는 명시한 로컬 환경의 검증이며 외부 게시나 원격 배포의 완료를 대신하지 않는다.
