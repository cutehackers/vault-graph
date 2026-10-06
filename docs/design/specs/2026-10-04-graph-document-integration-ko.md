# graph_document와 기존 Vault Graph 연동 설계

- Design ID: DG-20261004-INTEGRATION
- Status: Proposed — 기존 DB·공개 API·기본 경로를 변경하는 승인이 아니다.
- Created: 2026-10-04
- Parent contract: [DG-20261004](2026-10-04-graph-document-ko.md)
- Related contract: [graph_search 기존 투영 연동](2026-10-03-graph-search-integration-ko.md). 별개 기존 계약을 수정하지 않는다.
- Independent Design Review: Passed on 2026-10-04 — 별도 리뷰 에이전트 재검토, 설계 제출 범위만 검증

## 1. 연동 목표와 경계

Vault 없이 일반 문서 그래프를 사용할 수 있어야 하고, 기존 Vault 조회 경로는 원래 결과를 유지해야 한다.
패키지 분리만으로 기존 ID, 정규화, confidence, status, 근거 검증, scope, 순위를 바꾸지 않는다.
코어 책임과 기존 호환성 정책은 다르므로 어댑터가 단순 field rename보다 많은 일을 할 수 있다.
이 문서는 부모 계약의 보조 설계이며 독립된 대체 부모가 아니다.

```text
MetadataStore / Vault 문서 구조
  → VaultGraphDocumentAdapter (범위·링크 해결·legacy 규칙 변환)
  → graph_document (기여·근거·트랜잭션·리비전)
  → 일반 DocumentGraphSnapshot
  → search_bridge → graph_search
  → Vault 응답 변환 (원래 ID·근거·점수·순위)
```

Vault catalog, 데이터 홈, 허용 경로, cross-vault, readiness, 원문 근거 유효성 검사,
CLI/MCP/HTTP 응답은 vault_graph의 책임이다. graph_document는 문서와 명시한 DB만 받는다.
코어에 QueryScope나 vault_id를 다시 넣어 연동을 해결하지 않는다.

## 2. 현재 구현과 재사용 판단

| 현재 위치 | 확인한 역할 | 재사용과 필요한 변경 |
| --- | --- | --- |
| [entity_extractor.py](../../../src/vault_graph/extraction/entity_extractor.py) | 문서·태그·제목·링크·frontmatter에서 항목 추출 | 규칙과 fixture를 활용한다. Vault 경로 해결과 입력 타입은 어댑터에 남긴다. |
| [relationship_extractor.py](../../../src/vault_graph/extraction/relationship_extractor.py) | mentions와 typed 관계 생성 | 규칙별 관계 생성·중복 처리를 활용하되 confidence·status는 legacy 정책이다. |
| [graph_source_store.py](../../../src/vault_graph/extraction/graph_source_store.py) | chunk와 document 공급, 범위 기반 참조 해결 | 기존 공급자로 일반 Document를 만든다. 코어 runtime에서 가져오지 않는다. |
| [graph_indexer.py](../../../src/vault_graph/indexing/graph_indexer.py) | desired 상태·안정 ID·근거·변경·tombstone 계획 후 apply | 기여 집계·차이 계산과 fixture를 활용한다. collection CAS와 문서별 교체는 새 계약이다. |
| [graph_store.py](../../../src/vault_graph/storage/interfaces/graph_store.py) | 기존 저장·검색 Protocol | 공개 계약을 그대로 이동하지 않는다. per-Vault scope를 변환한다. |
| [sqlite_graph_store.py](../../../src/vault_graph/storage/local/sqlite_graph_store.py) | sqlite-graph-v2, reconcile 계획의 단일 transaction 적용 | transaction·FK·read-only·오류 처리 패턴을 활용한다. 새 DB 스키마는 별도다. |
| [graph_retrieval_service.py](../../../src/vault_graph/app/graph_retrieval_service.py) | 범위·시작점·관계 수집·근거 검증·투영 결과 조립 | 기존 서비스 계약과 출력 정책을 유지한다. 기능별 단계 전환 후 어댑터로 연결한다. |
| [index_service.py](../../../src/vault_graph/app/index_service.py) | MetadataGraphSourceStore와 추출기를 GraphIndexer에 주입 | 통합 factory와 색인 orchestration을 변경하는 지점이다. |

현재 extractors는 chunk 기준이고, 새 저장 갱신은 document 기준이다.
모든 chunk를 모은 한 문서를 한 contribution으로 변환해야 한다. 한 chunk만 받아 나머지 근거를 지우면 안 된다.
현재 graph evidence는 ID·hash·section·anchor·path를 보관하며 원문 전문/발췌는 저장하지 않는다.
Vault 연동은 max_excerpt_chars=0으로 고정하고 기존 metadata blob에서만 plaintext를 조회한다.
새 패키지의 선택적 발췌 저장을 기존 DB·응답의 새로운 기본값으로 적용하지 않는다.

## 3. 어댑터 계약과 ID 대응

제안 위치는 `src/vault_graph/extraction/vault_graph_document_adapter.py`다.
고정된 일반 package 인터페이스로 공급·동기화하고, 별도의 Vault 호환 읽기 어댑터로 결과를 변환한다.
하나의 변경 가능한 객체에 index와 query의 모든 legacy 상태를 넣지 않는다.

- `materialize_documents(actual_scope) -> VaultDocumentBatch`: 기존 MetadataStore에서 전 문서 chunk를 조합한다.
- `sync(batch, expected_revision) -> VaultSyncResult`: 일반 패키지에 명시한 변경·제거만 적용한다.
- `read_projection_input(request) -> GraphProjectionInput`: 원래 ID·scope·종류·상태·신뢰도·근거 계약으로 복원한다.

VaultDocumentBatch와 VaultSyncResult는 vault_graph 내부 타입이며 일반 패키지 공개 API가 아니다.
최초에는 legacy 색인 실행 결과와 별도 DB를 비교하는 경로에만 호출하고 production factory는 유지한다.
새 패키지로 분리한 의미 중립 계산은 별도 wheel 내부로 옮기되, wrapper가 기존 함수를 호출하는 형태의
역방향 runtime 의존성은 금지한다. legacy 정책은 vault_graph에 남기거나 주입하는 순수 Extractor로 구현한다.

collection_id는 Vault ID와 scope의 충돌 없는 canonical serialization으로 정한다.
구현에서는 `profile_digest`도 포함하여 profile 변경 시 별도 collection을 만들고 이전 revision을 유지한다.
문서 subset 변경은 collection identity로 표현하지 않는다. 동일 문서가 여러 scope에 속하면
각 scope collection의 색인 상태를 별도로 관리하고 호출자가 조회 범위를 합친다.
collection은 권한 기능이 아니다. 읽기·쓰기 허용 여부는 기존 서비스가 검사한다.

일반 document_id는 기존 `(vault_id, document_id)`를 충돌 없이 encode한다.
기존 node/relationship/evidence ID와 일반 ID는 서로 같다고 가정하지 않는다.
원래 owner identity, chunk identity, anchor, content_hash, extraction method, confidence, status,
metadata/parser/chunker/spec revision의 대응표를 vault_graph 측 파생 cache에 보관한다.
일반 key에는 불투명한 encoded legacy entity identity를 사용하여 기존 동명이인 통합 규칙을 보존한다.
legacy-v1 profile는 원래 정규화와 관계 규칙을 사용한다. 일반 기본 profile의 NFKC 등을 적용하지 않는다.

원래 ID는 응답 밖으로 나가는 마지막 변환에서 복원한다. 대응표 누락은 오류이며 최신 이름으로 추정하지 않는다.
일반 패키지가 legacy ID를 해석하거나 confidence를 계산하게 하지 않는다.

`VaultProjectionRequest`는 기존 GraphStore에서 확인한 `source_graph_revisions`와
`relationship_revisions=(source_vault_id, relationship_id, graph_index_revision)` 대응표를 요구한다.
graph_document의 revision을 기존 graph revision으로 대체하지 않는다. 관계 대응표는 선택한 관계의
전체 identity와 일치해야 한다. 이 값으로 복원한 투영 결과의 빌드 ID까지 기존 oracle과 비교한다.

순서6의 명시적인 shadow 공급 factory는 `app/graph_document_service_factory.py`의 `GraphDocumentServiceFactory.open_adapter()`다.
기존 활성 generation의 MetadataStore를 읽고, 새 DB와 manifest는 Data Home의
`cache/graph-document/derived.sqlite3` 및 `cache/graph-document/manifests/`에 둔다.
factory 생성·열기는 색인을 실행하거나 캐시를 생성하지 않는다. 호출자가 `materialize_documents()`와
`sync()`를 명시적으로 실행한다. 이 factory의 열기만으로 기본 조회 경로가 바뀌지는 않는다.

순서7의 운영 연결은 `app/graph_store_factory.py`에서 활성 generation의 `graph/backend.json`을
읽어 선택한다. `vg index --graph-backend document`는 private staging generation의
`graph/document-store/derived.sqlite3`, 전체 대응 manifest와 `compatibility.json`을 구성한다.
검증된 `DocumentGraphSnapshot`과 같은 revision에 묶인 호환 정보로 메모리 SQL 조회 상태를
만든다. 기존 SQL 조회 정책은 재사용하지만 기존 `graph.sqlite3`에서 공개 결과를 읽지 않는다.
별칭·status·confidence·근거는 해당 문서 기여와 대조한다. timestamp·run ID·기존 graph revision은
기존 export 또는 GraphIndexer가 생성한 호환 정보이며 일반 패키지의 revision으로 대체하지 않는다.

새 저장소 색인과 metadata를 함께 검증한 뒤 기존 generation 게시 절차로 활성화한다.
이후 옵션 없이 실행한 색인·조회도 선택한 새 경로를 사용한다. 이전하지 않은 설치는 legacy를
유지한다. 여러 enabled Vault가 있으면 전환과 rollback에 `--all-vaults`가 필요하다.
선택 파일·전체 대응 정보·revision이 없거나 맞지 않으면 오류로 처리하며 legacy로 돌아가지 않는다.
읽기 전용 open은 색인이나 DB 생성, 복구를 실행하지 않는다.

`vg index --graph-backend legacy`는 private staging copy에서 기존 그래프 캐시를 다시 만들고
전체 색인과 readiness를 확인한 뒤 게시한다. 오래된 legacy DB를 선택하는 방식의 rollback은
허용하지 않는다. 전환 dry-run은 현재 저장소로 변경 계획을 계산하고 전환 의도를 표시하며
새 캐시를 쓰거나 전환 검증이 완료되었다고 표시하지 않는다. 원문과 이전 활성 generation은 보존한다.

## 4. 추출·갱신·동기화

어댑터는 허용된 실제 scope와 전체 문서 구조로 local link를 해결한다.
원래 wiki/raw/docs 경로 규칙, generic heading 제외, frontmatter 키, unresolved link 의미를 유지한다.
VaultDocumentBatch는 문서별 모든 chunk와 구조 위치를 일반 문서 입력으로 변환한다.
일반 text가 기존 chunk와 다른 좌표를 쓰면 원래 chunk·anchor는 별도 locator mapping으로 복원한다.
span을 원본 파일의 byte offset으로 오인하지 않는다.

legacy-v1 Extractor는 기존 occurrence 결과에 해당하는 일반 key·관계·근거를 생성한다.
새 일반 기본 규칙과 legacy-v1은 별도 profile다. 규칙을 섞거나 일반 unresolved kind를 기존 Concept 응답으로
직접 내보내지 않는다. 기존 stated/confidence는 대응표와 original occurrence로 계산한다.

초기 shadow 색인은 기존 결과를 canonical export하여 비교하고 새 DB에 색인한다.
새 package 갱신과 legacy DB commit을 하나의 transaction이라고 주장하지 않는다.
정식 전환 전까지 legacy DB가 조회 기준이며 shadow 실패는 별도 진단으로 보고한다.
정식 전환 후에도 두 DB를 동등한 authoritative writer로 유지하지 않는다.

새 package DB와 대응표가 다른 DB면 원자적 dual-write를 가정하지 않는다.
대응표 cache는 `(collection_id, graph_revision, profile_digest)`별 **전체 collection manifest**로 만든다.
manifest는 문서별 input/extraction digest, source/metadata revision, original occurrences와 대응표를 보관한다.
본문과 발췌는 보관하지 않는다. 전체 manifest의 canonical digest는 selection별 read_digest와 별개다.

증분 갱신 전에는 이전 revision의 검증된 전체 manifest가 필요하다. 그 문서별 기여 중 변경 문서만 교체하고
삭제 문서만 제거하여 다음 전체 manifest를 구성한다. 변경되지 않은 B의 mapping은 보존한다.
새 DB commit 후 실제 revision을 붙인 manifest를 임시 파일에 완전히 기록하고 같은 cache 디렉터리에서
원자적 rename으로 게시한다. manifest digest와 내부 문서 digest의 일치 검증 후에만 readiness=true로 한다.

처음부터 재구성하려면 해당 revision에 대응하는 **모든 문서의 original occurrences와 digest**가 필요하다.
변경 batch만으로 전체 대응표를 만들 수 있다고 가정하지 않는다. DB commit 후 manifest 생성에 실패하면
새 경로의 해당 revision은 readiness=false다. 이전 manifest와 저장한 변경 occurrences로 재구성하거나,
원문/metadata revision이 모두 일치하는 전 문서 입력으로 재생성한다. 필요한 기여를 복구할 수 없으면
새 collection 전체 재색인을 요구한다. 최신 mapping으로 누락을 추정하거나 빈 정상 결과로 바꾸지 않는다.

구현의 `recover(full_batch, expected_revision=latest_revision)`는 전체 원래 기여와 현재 DB의
input/source/extraction digest를 대조한 뒤 누락 manifest를 게시한다. 부분 batch나 다른 원문 revision으로
복구하지 않는다. 최초 빈 범위는 core collection을 생성하지 않고 어댑터의 revision-0 manifest로 표현한다.

공급 단계는 chunk의 path·문서/색인 revision, 두 번 읽은 전체 inventory와 chunk 목록을 대조한다.
sync 직전에도 재확인한다. factory가 사용하는 활성 generation은 색인 중인 DB와 분리된 읽기 입력이다.
임의의 변경 가능한 MetadataStore 공급자는 최종 확인 뒤에도 바뀔 수 있으므로, 이 어댑터가 두 저장소의
원자적 transaction이나 원문의 최신성을 보장한다고 해석하지 않는다. ready는 DB revision과 전체 manifest의
정합성이다. 공개 조회에 게시할 때의 원문 최신성 검사는 기존 GraphRetrievalService에 유지한다.

부분 DocumentGraphSnapshot는 collection/revision/profile 일치 후, 선택 문서의 input/extraction digest를 전체 manifest와
대조한다. 선택 기여의 일반 node/edge/evidence ID가 manifest에서 복원 가능해야 한다.
selection마다 다른 read_digest는 DocumentGraphSnapshot의 자체 완전성 검사에 사용하고 전체 manifest key로 사용하지 않는다.
조회 서비스는 검증한 선택 부분만 결과로 복원한다. 범위 밖 aliases·근거를 추가하지 않는다.

문서 제거는 공급자의 전체 문서 목록 또는 명시적 삭제 이벤트로 확인한 ID만 적용한다.
검색 결과·부분 로드·읽기 실패를 삭제로 해석하지 않는다. 불완전 batch는 삭제 동기화를 중단한다.
기존 tombstone·revision·diagnostic 응답을 public 계약에서 유지하며 물리 삭제와 혼동하지 않는다.
일반 collection profile 변경은 새 collection 재색인으로 처리한다. 이전 collection은 rollback을 위해 유지한다.

## 5. 조회·graph_search·근거 연결

기존 GraphRetrievalService가 scope와 시작점을 결정하고 근거 유효성을 검사하는 순서를 유지한다.
일반 패키지의 exact name query를 기존 fuzzy/부분 조회의 대체로 사용하지 않는다.
기존 matching은 어댑터의 기존 검색 계약으로 처리하고 일반 node_id를 선택한다.
문서 선택만으로 legacy 관계 종류·status·cross-vault 필터가 구현된다고 가정하지 않는다.

두 연동 방식은 단계에 따라 구분한다.

1. 준비 단계에서는 기존 GraphStore가 제공한 validated GraphProjectionInput으로
   [GS 연동 어댑터](2026-10-03-graph-search-integration-ko.md)를 사용한다. graph_document를 먼저 기본 DB로 바꾸지 않는다.
2. graph_document 경로를 검증할 때는 DocumentGraphSnapshot와 그 revision manifest로 기존 domain records를 복원한다.
   기존 필터와 근거 검증을 거친 GraphProjectionInput을 GS 연동 어댑터에 전달한다.
   이 경로는 일반 search_bridge와 달리 legacy 점수·순위를 유지한다.

일반 소비자는 search_bridge를 사용한다. Vault consumer는 기존 legacy projection 계약을 유지한다.
관련 항목 조회·순위·build hash·truncated 등의 규칙은 GS 연동 계약과 대조한다.
BFS 대표 경로만으로 기존 복수 경로와 top-K를 대체하지 않는다.
검색 후 근거는 같은 DocumentGraphSnapshot 및 revision manifest에서 가져오며, 실제 원문이 최신인지 확인하는 기존 검증은 유지한다.
현재 원문이 바뀌어 근거 검증에서 제외된다면 diagnostics를 유지하고 탐색 전에 제외한다.
관련 문서 밖의 관계를 임의로 확장하거나 missing evidence를 새로운 본문 인용으로 채우지 않는다.

## 6. 데이터 이전과 단계적 전환

기존 DB는 sqlite-graph-v2로 유지하고 새 DB는 Data Home 안의 별도 파생 cache 경로에 둔다.
정확한 경로는 기존 data-home 경계와 cache 관리 규칙을 확인한 구현 계약에서 정한다.
원문 경로에 DB를 만들지 않으며 DB·manifest 경로의 실경로와 symlink를 검사한다.
새 패키지에는 catalog나 Data Home 경로 규칙을 넣지 않는다.

| 단계 | 결과와 종료 증거 |
| --- | --- |
| DG-M-01 | 일반 패키지를 독립 wheel로 구현하고 DG-FA-01–DG-FA-12를 검증한다. Vault default는 유지한다. |
| DG-M-02 | 읽기 전용 export와 legacy-v1 변환을 구현한다. 원래 ID·근거·정규화·충돌 fixture를 비교한다. |
| DG-M-03 | 새 DB shadow 색인, 대응표 readiness, 전체/증분/삭제/fault 차등 검증을 완료한다. |
| DG-M-04 | CLI/MCP/HTTP 결과와 기존 GS 연동 gate를 통과하고 전환/rollback 정책을 승인받는다. |
| DG-M-05 | factory 한 곳에서 새 경로를 선택하고 rollback을 실행 검증한다. 기존 DB 제거는 별도 범위다. |

인덱싱 factory는 IndexService._graph_indexer, 조회 factory는 app/read_only_service_factory.py 및 cli/main.py를
확인하는 지점이다. 코어 구현 완료와 factory 전환 완료는 별개다. 기존 이름의 import 경로는 호환 wrapper로 유지한다.
rollback은 기존 DB와 factory로 돌아가는 방법이다. shadow 단계에서 원래 DB를 수정하지 않았음을 확인한다.
전환 이후 원문 변경을 legacy DB에 반영하지 않았다면 먼저 기존 full 색인을 수행하고 readiness를 확인해야 한다.
오래된 DB로 바로 전환해 최신이라고 응답하는 rollback은 허용하지 않는다.

## 7. 연동 수용 기준

| ID | 수용 기준 | 필요한 증거 |
| --- | --- | --- |
| DG-IT-01 | 전체 chunk가 일반 문서로 변환되고 기존 태그·heading·frontmatter·link 의미가 유지된다. | 규칙별 기존 fixture + legacy-v1 differential. |
| DG-IT-02 | 원래 노드·관계·근거 ID와 confidence/status를 복원한다. | same-name, scope, cross-vault, ID collision fixture. |
| DG-IT-03 | 전체·증분·삭제 계획이 기존 state와 조회 결과를 보존한다. | 기존 GraphIndexer vs 새 상태의 canonical export 비교. |
| DG-IT-04 | 부분 문서 batch/읽기 실패가 삭제나 최신 readiness로 처리되지 않는다. | missing chunk·source failure·검색 subset·불완전 manifest injection. |
| DG-IT-05 | 두 저장 경계 사이 실패 시 잘못된 revision 근거를 공개하지 않는다. | A만 갱신 후 B 복원, 부분 selection, DB commit 전/후, manifest write 전/후 fault·재개방·복구. |
| DG-IT-06 | 기존 scope·관계 필터·근거 검증·복수 경로·점수·순위를 유지한다. | retrieval golden + GS-IT 전 항목(기존 이름 IT-01–IT-12). |
| DG-IT-07 | 기존 CLI/MCP/HTTP/검색 include-graph와 plain 검색 응답이 회귀하지 않는다. | 실제 공개 entrypoint contract suite와 factory smoke. |
| DG-IT-08 | 원문·기존 DB를 변경하지 않고 새 DB 쓰기는 허용된 cache에만 수행한다. | Vault sentinel 해시, symlink 경계, read-only 및 shadow side effects. |
| DG-IT-09 | 새 package 없이 기존 경로를 실행하고, 독립 package는 Vault 없이 실행한다. | 두 설치 환경과 import graph 검사. |
| DG-IT-10 | 새 schema/profile/cache 교체와 rollback이 명시한 최신성을 지킨다. | 스키마 불일치 거부, 새 collection 재색인, 전환 후 legacy 재색인 rollback. |

정규화·unresolved 처리·일반 query 계약의 차이는 호환성 adapter로 처리하거나 별도 버전 승인에 남긴다.
“기존도 잘 설계돼 있으니 동일할 것”을 증거로 삼지 않는다. 기존 엔진을 새 wrapper로 덮은 뒤 서로 비교하지 않는다.

## 8. 기존 회귀 검증과 미결 사항

부모 §12의 명령 외에 실제 존재하는 다음 검사를 사용한다. 이번 설계 제출에서 실행하지 않았다.

```bash
uv run --python 3.12 pytest -q tests/test_graph_occurrences.py tests/test_graph_source_store.py tests/test_graph_contracts.py tests/test_graph_query_contract.py tests/test_index_service_graph_reconcile.py
uv run --python 3.12 pytest -q tests/test_graph_projection.py tests/test_graph_retrieval_service.py tests/test_multi_vault_graph_retrieval.py tests/test_search_include_graph.py tests/test_graph_retrieval_read_only_boundary.py
```

공개 CLI/MCP/HTTP, manifest fault, 실제 factory 주입, rollback 테스트는 구현된 경로를 확인한 뒤
정확한 테스트 파일과 명령을 추가한다. 기존 unit suite만으로 end-to-end 호환성을 선언하지 않는다.

| ID | 미결 사항 | 권장과 gate |
| --- | --- | --- |
| DG-INT-Q-01 | 실제 cache/manifest 배치와 GC | 기존 Data Home 정책을 따르고 immutable revision 단위로 구성. 구현 전 경로·실패 복구 확정. |
| DG-INT-Q-02 | default 전환 시점과 지원 호환 버전 | 독립 wheel, 차등·공개 경로·운영 측정 후 별도 전환 승인. |
| DG-INT-Q-03 | 장기적으로 legacy occurrence metadata를 단순화할지 | 첫 버전은 유지. ID·근거·순위 변경은 별도 계약으로 다룬다. |

설계 완료는 원래 public 계약을 보존하는 변환, 데이터 생명주기, 단계 전환, 각 검증 기준과 독립 리뷰를 갖춘 상태다.
실제 연결 완료는 DG-IT-01–DG-IT-10의 런타임 증거와 필요한 승인 후에만 선언한다.


## 독립 리뷰와 설계 검증 기록

2026-10-04 별도 read-only review agent가 일반 계약, 기존 코드 경계, graph_search 계약을 검토했다.
첫 리뷰의 세 보정사항은 전체 Document digest와 원문 버전 갱신, 선택별 alias 기여 집계,
증분 갱신 후 전체 revision manifest의 구성·복구다. 반영 후 재리뷰에서 설계 제출 Passed를 받았다.

문서 링크·anchor·code fence·추가 영역 공백, DG-FA-01–14/DG-IT-01–10/DG-SEM-01–05 번호,
검증 명령의 기존 테스트 파일 존재를 확인했다. 기존 graph_search 두 계약의 hash가 동일하고,
SPEC의 신규 목차·§11을 제외한 본문도 작업 시작 시점과 동일함을 확인했다.
패키지 코드·DB·테스트·factory는 변경하지 않았다. 런타임 검증 계획은 실행 증거가 아니다.
