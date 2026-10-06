# 독립 graph_document 패키지 상세 설계

- Contract ID: DG-20261004
- Contract Status: Proposed — 패키지 계약과 연동 설계 제안. 구현과 기존 기본 경로 변경은 포함하지 않는다.
- Created: 2026-10-04
- Intent Status: Hardened for design scope — 사용자 답변으로 규칙 추출 기본값과 의미 추출 대안 설계 범위를 확인했다.
- Independent Design Review: Passed on 2026-10-04 — 별도 리뷰 에이전트 재검토, 설계 제출 범위만 검증
- Source: 현재 사용자 요청과 앞선 문서 그래프 모듈 분리 논의
- Product specification: [SPEC §11](../../SPEC.md#11-independent-graph-document-design-proposal)
- Supporting design: [기존 Vault Graph 연동](2026-10-04-graph-document-integration-ko.md)
- Related contract: [graph_search](2026-10-03-graph-search-ko.md). 별개 부모 계약이며 기존 계약을 변경하지 않는다.
- Decision records: [사용자가 확인한 범위](../../DECISIONS.md#2026-10-04---separate-graph-document-with-rule-based-defaults). 상세 설계 선택은 §13의 제안 기록으로 유지한다.
- Glossary: §3
- Review corrections: [PATCH_LOG](../../PATCH_LOG.md#2026-10-04---correct-graph-document-revision-and-contribution-contracts)

## 1. 문제와 목표

기존 시스템에는 문서에서 항목·관계를 추출하고, 근거와 함께 저장하고, 변경에 맞춰
그래프를 갱신하는 기능이 있다. 그러나 입력과 저장 계약이 Vault 모델에 묶여 있다.
다른 문서 공급자가 이용하려면 Vault catalog, QueryScope, chunk, 리비전 모델을 알아야 한다.

독립 패키지의 책임은 **전달받은 문서로부터 근거가 있는 그래프를 만들고 관리하는 일**이다.
경로 계산은 graph_search에 맡긴다. 추출, ID 통합, 문서별 기여 제거, 트랜잭션, 근거 조회를
단순한 인터페이스 뒤에 숨긴다. 함수마다 패키지를 만드는 것은 목표가 아니다.

| ID | 의도와 관찰 가능한 목표 |
| --- | --- |
| INT-01 | Vault 없이 문서 그래프 기능을 재사용한다. |
| GOAL-01 → INT-01 | 일반 문서 입력으로 항목·관계·근거를 저장하고 재개방하여 조회한다. |
| GOAL-02 → INT-01 | 문서 변경·제거 후에도 다른 문서의 관계와 근거가 유지된다. |
| GOAL-03 → INT-01 | 같은 그래프 리비전의 경로 결과를 원문 근거와 연결한다. |
| INT-02 | 기존 시스템의 동작과 데이터 경계를 보존하며 분리한다. |
| GOAL-04 → INT-02 | 어댑터를 통해 기존 추출·저장·조회 결과를 차등 검증한다. |

이번 완료는 상세 스펙, 검증 계획, 별도 리뷰의 제출이다. 패키지 설치나 런타임 검증 완료를 뜻하지 않는다.

## 2. 범위와 의도 확인

대상 사용자는 문서 색인 서비스와 그래프 조회 서비스 개발자다. 입력은 이미 읽은 문서이며,
읽을 수 있는 문서 범위와 저장 DB 위치를 정하는 책임은 호출자에게 있다.

첫 버전에는 일반 문서 계약, 결정론적 추출, 문서별 갱신과 제거, SQLite 저장,
정확 이름 조회, 리비전이 고정된 그래프·근거 읽기, 선택적 graph_search 연결을 포함한다.
기존 구현을 첫 연동 대상으로 삼지만 독립 패키지에서 vault_graph를 가져오지 않는다.

일반 문서는 특정 저장소에 속하지 않는 텍스트와 명시적 구조 정보다. HTML/PDF/Word 읽기,
파일 탐색, OCR, URL 가져오기, 검색 엔진, LLM·임베딩, 자연어 답변, 점수 기반 순위는 범위 밖이다.
형식별 읽기·구조 파싱은 문서 공급자가 수행한다. 관계 없는 본문에서는 문서 노드만 생성할 수 있다.
`GraphStore`라는 기존 클래스명이나 SQLite 테이블 구조를 그대로 공개 계약으로 삼지 않는다.

의도 확인은 앞선 대화의 일반 문서 입력, 근거 관리, graph_search와의 분리, 기존 기능 재사용을
기준으로 했다. 사용자는 규칙 기반 추출을 기본으로 진행하고, 의미 추출의 적합한 대안을
스펙에 포함하도록 답했다. 의미 추출 구현이나 기본 활성화는 이번 범위가 아니다.
재시도, 동시 갱신, 근거 소실, 미해결 참조, 용량 초과, 기존 DB 호환성을 반례로 검토한다.

## 3. 용어와 소유권

| 용어 | 정의 |
| --- | --- |
| collection | 같은 ID 공간에서 그래프를 만드는 문서 집합. 권한·Vault를 뜻하지 않는다. |
| document_id | 호출자가 지정한 불투명 문서 ID. collection 안에서 유일하다. |
| source_revision | 공급자가 지정한 불투명 원문 버전. 최신 순서를 판단하는 값은 아니다. |
| graph_revision | DB의 collection별 비음수 정수. 논리 상태 변경 commit마다 1 증가한다. |
| entity key | `(kind, key)`로 구성한 명시적 항목 정체성. 같은 이름이 곧 같은 항목인 것은 아니다. |
| contribution | 한 문서가 제공한 노드·관계·근거 묶음. 갱신은 이 묶음을 교체한다. |
| evidence | 문서 ID·원문 버전·입력 digest·구조 위치·추출 규칙으로 구성한 근거 기록. |
| DocumentGraphSnapshot | 하나의 graph_revision에서 읽은 불변 노드·관계·근거 묶음. |

추출된 데이터는 원문에서 재생성할 수 있는 파생 데이터다. 저장소를 원문의 공식 기준으로 삼지 않는다.
문서 본문은 추출 중에만 사용하며 DB에는 전문을 저장하지 않는다. 제한된 근거 발췌는 저장할 수 있다.
원문 링크·위치는 출력용 문자열이다. 패키지는 이를 열거나 수정하지 않는다.
기존 Vault 연동은 max_excerpt_chars=0으로 고정한다. 원문 plaintext의 소유자는 기존 metadata blob이며
일반 패키지의 선택적 발췌가 이 정책을 변경하지 않는다.

## 4. 패키지와 의존성

```text
packages/graph-document/
  pyproject.toml
  src/graph_document/
    __init__.py
    contracts.py
    extraction.py
    indexing.py
    sqlite_store.py
    querying.py
    search_bridge.py
    errors.py
    py.typed
  tests/
```

배포명은 사용자 결정에 따라 `nolemy-graph-document`, import 이름은 `graph_document`다. Python 3.12 이상을 대상으로
별도 wheel, 개발 의존성, 버전, CI 작업을 관리한다. 위 파일은 책임을 설명한 설계이며 아직 생성하지 않았다.
기본 runtime은 표준 라이브러리만 사용한다. SQLite는 Python sqlite3를 사용한다.
선택적 `search` extra만 `nolemy-graph-search` runtime 의존성을 선언한다. 호환 범위는 `>=0.1,<1`이며 실제 wheel 검증으로 확인한다.
`search_bridge`를 가져올 때만 graph_search를 가져오며 기본 import에는 이를 요구하지 않는다.

의존성 방향은 `vault_graph → graph_document → 표준 라이브러리`와
`graph_document.search_bridge → graph_search`다. graph_search는 문서 패키지를 알지 않는다.
기존 추출기 호출을 뒤로 숨긴 채 vault_graph를 runtime 의존성으로 두는 방식은 독립성에 부합하지 않는다.

## 5. 입력과 추출 계약

모든 공개 값은 타입이 고정된 불변 dataclass와 tuple이다. 임의 dict payload나 callback 기반 필터를 받지 않는다.
ID와 key는 비어 있지 않은 UTF-8 문자열이며 원형을 보존한다. bool은 정수 상한으로 허용하지 않는다.
input_digest는 document_id, source_revision, title, text, 모든 features와 위치, source_locator를 포함한
전체 Document의 versioned canonical serialization 후 SHA-256으로 계산한다. None과 빈 문자열은 구분한다.
canonical 표현은 UTF-8 JSON으로 필드명을 정렬하고 공백 없는 separators를 사용하며 숫자 float와 임의 payload는 받지 않는다.
features는 타입·key·값·위치로 정렬하고 완전히 동일한 feature 중복은 하나로 만든다. 상충한 위치는 오류다.
문서 text·title·locator는 원형 그대로 포함한다. 입력 순열에 의존하는 first-wins 처리를 금지한다.
profile_digest는 별도이며 input_digest 안에 넣지 않는다. 출력 facts도 canonical 정렬한 extraction_digest를 보관한다.

| 타입 | 주요 필드와 의미 |
| --- | --- |
| Document | document_id, source_revision, title, text, features, source_locator |
| DocumentFeatures | tags, headings, references, stated_relations. 공급자가 파싱한 구조 정보. |
| LocatedValue | value, location. 태그·제목처럼 원문 구조 위치가 있는 값. |
| EntityKey | kind, key. document kind의 key는 document_id. concept key는 규칙별 정규화 값. |
| Reference | target_document_id 또는 unresolved_key 중 정확히 하나, label, location |
| StatedRelation | source: EntityKey, target: EntityKey, relation_type, location |
| EvidenceLocation | structural_id, text_span: `(start,end)` 또는 None, label |
| ExtractionProfile | profile_id, extractor_fingerprint, name_normalization, excluded_headings, allowed_kinds, allowed_relation_types, max_excerpt_chars, profile_digest. 전체 설정의 고정 지문. |
| ExtractedDocument | document_id, input_digest, profile_digest, entities, relations, evidence, warnings |
| GraphLimits | max_batch_documents, max_document_utf8_bytes, max_batch_utf8_bytes, max_nodes, max_edges, max_evidence, max_id_utf8_bytes |

text_span은 전달된 `Document.text`의 Unicode 코드포인트 인덱스이며 `0 ≤ start < end ≤ len(text)`다.
태그·frontmatter처럼 본문 밖의 정보에는 text_span=None과 비어 있지 않은 structural_id를 사용한다.
원문 byte offset이나 원본 PDF 좌표라고 주장하지 않는다. 어댑터는 기존 anchor·chunk 대응표를 유지한다.
모든 위치는 존재해야 하며 동일 structural_id에 상충하는 내용이 있으면 오류다.

ExtractedDocument.entities는 EntityKey, label, aliases, rule_id, locations를 가진 EntityFact의 tuple이다.
relations는 source/target EntityKey, relation_type, rule_id, locations를 가진 RelationFact의 tuple이다.
출력 facts의 location은 입력 Document의 구조 위치와 대응해야 한다. 모든 관계는 최소 1개 근거가 필요하며
끝점은 해당 문서의 facts에 포함해야 한다. 문서 identity도 구조 위치 `document`로 근거를 가진다.
코어가 owner ID를 계산하고 facts의 location에서 evidence를 구성한다. 추출기가 임의 owner ID를 지정하지 않는다.
ExtractedDocument의 evidence는 이 위치들의 집합으로, 참조되지 않은 위치나 상충한 위치를 거부한다.

기본 `RuleExtractor`는 다음을 수행한다.

- 문서마다 document 항목을 생성한다. 다른 문서에도 참조된 document 노드는 원문 입력이 없어도 유지될 수 있다.
- 태그와 일반 제목이 아닌 heading은 concept 항목과 문서의 mentions 관계를 만든다.
  concept key 정규화는 v1에서 NFKC, casefold, 연속 공백 축약, 앞뒤 공백 제거 순서다.
  제외 heading 목록과 정규화 버전은 profile_digest에 포함한다. 문서 ID는 정규화하지 않는다.
- 명시적으로 해결된 Reference는 document 간 links_to 관계를 만든다.
  unresolved_key는 별도 unresolved kind와 unresolved_reference 관계로 유지하며 자동으로 document와 합치지 않는다.
- StatedRelation은 전달된 정확한 끝점 key와 관계 종류를 사용한다. concept 등 비문서 항목은 명시한 key로 생성한다.
  허용되지 않은 종류는 전체 배치 오류다. 기본 종류는 mentions, links_to, related_to, depends_on,
  blocks, implements, supersedes, revisit_when, unresolved_reference다.
- 본문의 임의 문장으로부터 관계를 추측하지 않는다. Reference 해결은 공급자의 책임이며 경로·URL을 직접 조회하지 않는다.

`Extractor.extract(document, *, profile) -> ExtractedDocument`는 동기 Protocol이다.
코어는 문서마다 호출하고 출력의 ID·끝점·근거·지문·용량을 다시 검증한다. 잘못된 추출 결과는 저장하지 않는다.
사용자 정의 추출기는 호출자가 명시적으로 주입하며, 기본 추출에는 네트워크가 없다.
외부 추출기의 실행 권한·시간 제한·모델 선택은 공급자의 책임이다. 공급자 코드는 신뢰된 실행 코드로 취급한다.
추출기는 문서 간 상태를 의존하지 않아야 한다. 단순 문서 추가로 이전 미해결 참조를 암묵적으로 재해석하지 않는다.

## 6. 정체성, 중복과 근거

node_id는 `(identity_version, collection_id, kind, key)`의 canonical JSON을 SHA-256으로 만든다.
edge_id는 `(identity_version, collection_id, relation_type, source_node_id, target_node_id)`로 만든다.
ID 해시 충돌이 감지되면 서로 다른 key를 합치지 않고 IdentityConflictError로 거부한다.
같은 끝점이라도 관계 종류가 다르면 다른 간선이다. 자기 루프와 반대 방향 관계는 허용한다.

같은 관계가 여러 문서에서 나오면 논리 간선 1개에 여러 contribution/evidence를 연결한다.
한 문서가 관계를 철회해도 다른 문서 근거가 남으면 간선을 유지한다. 모든 기여가 없어지면 간선을 제거한다.
노드는 직접 기여 또는 간선 끝점으로 필요할 때 유지하며, 둘 다 없을 때 제거한다.
레이블·표시 이름은 key가 아니며 여러 표시 이름은 정렬된 aliases로 보존한다.
label과 aliases도 문서별 contribution에 보관한다. collection 집계는 현재 살아 있는 기여만 사용하고,
DocumentGraphSnapshot 집계는 선택한 문서의 기여만 사용하여 중복 제거·정렬·대표 이름을 다시 계산한다.
대표 표시 이름은 label을 포함한 정렬된 aliases의 첫 값이다. 철회된 문서만 제공한 alias는 제거한다.
선택 밖 문서의 이름으로 find_items가 매칭되면 안 된다. 끝점으로만 필요한 노드의 이름은
선택된 reference fact의 label에서 가져오고 그 값이 없으면 key를 표시한다. 신뢰도 점수는 첫 버전 계약에 넣지 않는다.

evidence_id는 문서 ID·source_revision·입력 digest·owner ID·structural_id·span·rule ID의 지문이다.
같은 위치의 여러 관계는 각각의 owner에 연결한다. 동일 evidence_id의 다른 내용은 오류다.
발췌는 원문 범위의 앞부분을 명시한 max_excerpt_chars까지 보관하고 생략 여부를 표시한다.
max_excerpt_chars는 개방 시 지정하며 profile_digest에 포함한다. 위치가 본문 밖이면 발췌는 None이다.
source_revision만 같고 입력 digest가 다르면 SourceRevisionConflictError로 거부한다.
source_revision의 정렬로 최신 여부를 판단하지 않는다. 삭제 후 재사용한 ID에는 이 검사를 현재 문서 상태 기준으로 적용한다.
source_revision만 변경되어도 input_digest와 evidence_id가 바뀌므로 갱신으로 commit하고 graph_revision을 증가시킨다.
같은 source_revision에서 title·locator·구조 정보가 바뀌어도 입력 충돌이다. 공급자는 새 source_revision을 지정해야 한다.
같은 input_digest/profile_digest로 다시 추출한 facts의 extraction_digest가 다르면 ExtractionResultConflictError다.
원문 동일 버전에서 모델 재실행 결과로 관계를 조용히 교체하지 않는다.

## 7. 공개 저장·조회 API

아래는 설계상의 signature다. 구현 예제가 아니며 모든 options와 결과는 이 문서의 의미를 따른다.

```python
GraphDocument.open(path, *, mode, limits, profile, extractor, max_excerpt_chars, busy_timeout_ms) -> GraphDocument
GraphDocument.update_documents(documents, *, collection_id, expected_revision) -> UpdateResult
GraphDocument.remove_documents(document_ids, *, collection_id, expected_revision) -> UpdateResult
GraphDocument.read(*, collection_id, selection, limits) -> DocumentGraphSnapshot
GraphDocument.close() -> None
DocumentGraphSnapshot.find_items(query) -> ItemPage
DocumentGraphSnapshot.evidence_for(*, node_ids, edge_ids) -> EvidenceLookup
DocumentGraphSnapshot.resolve_documents(document_ids) -> DocumentLookup
```

open의 mode는 `create`, `read_write`, `read_only` 중 하나다.
`create`는 존재하지 않는 명시한 DB에만 생성한다. 부모 디렉터리를 자동 생성하지 않는다.
read_write와 read_only는 기존 지원 스키마만 개방하고 자동 migration·추출·색인을 하지 않는다.
read_only는 SQLite URI mode=ro로 개방하며 WAL sidecar 등 쓰기 권한을 요구하거나 생성하지 않는 fixture도 검증한다.
환경에 따라 지원하지 못하면 ReadOnlyOpenError로 실패하며 쓰기 모드로 재시도하지 않는다.
호출자는 파생 DB를 원문 저장 경로와 분리해야 하며 Vault 어댑터가 실제 경로 경계를 검사한다.
기본 import에는 파일 생성이 없다. handle은 context manager이며 close는 멱등이다. 닫힌 handle 호출은 ClosedStoreError다.

name_normalization은 `nfkc_casefold_space_v1` 또는 `identity_v1`이다. 기본 RuleExtractor는 전자를 사용한다.
legacy adapter는 이미 정규화한 key와 aliases를 공급하고 identity_v1을 사용한다. 새로운 정규화 알고리즘은 새 profile 버전으로 추가한다.
profile_digest는 위 설정과 identity/serialization 버전의 canonical encoding에서 코어가 계산하며 임의 지문을 신뢰하지 않는다.
open의 max_excerpt_chars는 profile의 값과 같아야 한다. read-only/read-write 조회도 해당 collection의 profile과 일치해야 한다.
busy_timeout_ms는 유한 비음수 정수이고 bool을 거부한다.

collection의 profile_digest는 첫 유효 update commit에 고정한다. 다른 profile로 갱신하면
ProfileMismatchError다. 규칙 변경은 새 collection에서 전체 문서를 다시 색인하고 호출자가 선택을 전환한다.
원래 collection을 덮어쓰는 자동 migration API나 일반 전체 교체 API는 첫 버전에 넣지 않는다.
빈 collection의 graph_revision은 0이다. collection은 첫 비어 있지 않은 update로 생성한다.
존재하지 않는 collection read/remove는 UnknownCollectionError다.

update는 명시한 문서만 교체한다. 검색 결과 일부를 입력했다고 나머지 문서를 삭제하지 않는다.
동일 배치에 같은 document_id가 두 번 나오면 동일 내용이어도 오류다. 입력 순서는 결과와 ID에 영향을 주지 않는다.
remove는 명시한 파생 문서 기여만 제거하고 원문을 삭제하지 않는다. 같은 ID 반복은 오류,
미등록 ID는 no-op이다. 빈 배치는 입력 오류다. 완전히 같은 상태의 update/remove는 revision을 증가시키지 않는다.
UpdateResult는 collection_id, previous_revision, graph_revision, changed_document_ids,
removed_document_ids, counts, warnings를 제공한다. counts는 commit 후 collection의 논리 노드·간선·근거 수다.

selection은 문서 ID tuple 또는 `all`이다. 선택 문서가 제공한 기여의 합집합과 그 간선의 끝점 노드를 읽는다.
문서 노드까지 다른 문서 기여가 이어진다고 외부 문서의 관계를 암묵적으로 포함하지 않는다.
문서 선택에 없는 기여와 근거는 포함하지 않는다. 선택 ID 중 미등록 문서가 있으면 오류다.
선택 범위의 그래프 전체를 읽으므로 용량 초과 시 CapacityError다. 몰래 잘라 부분 그래프를 반환하지 않는다.
선택 범위에 문서 metadata가 없는 document 끝점은 `source_available=False`로 구분한다.
다른 corpus에 원문이 없다는 의미는 아니다.
DocumentGraphSnapshot는 collection_id, graph_revision, profile_digest, selection, nodes, edges, evidence,
documents와 digest를 포함한다. DB 읽기 트랜잭션에서 모두 복사한 뒤 트랜잭션을 종료한다.
리비전 이후의 갱신·handle close와 무관하게 읽은 값은 변하지 않는다.

ItemQuery는 name, kinds, limit, cursor다. cursor는 최초 요청에서 None이다. name은 선택 DocumentGraphSnapshot의 key 또는 aliases에 대해
exact match한다. key는 원형 그대로, aliases는 profile의 이름 정규화를 적용해 비교한다.
node_id 오름차순으로 pagination한다. limit은 양수이며 ItemPage는 items와 next_cursor를 제공한다.
마지막 페이지에서 next_cursor=None을 반환한다.
관련도 순위나 자연어 검색을 의미하지 않는다. 다른 리비전 DocumentGraphSnapshot에 cursor를 넘기지 않도록
cursor에는 collection_id, graph_revision, read digest, query digest, last_node_id를 포함하고 불일치를 오류로 처리한다.

evidence_for는 지정한 owner별 근거를 evidence_id 순서로 반환하며 unknown_node_ids,
unknown_edge_ids도 구분한다. 원래 간선 방향을 유지한다. resolve_documents는 저장된 문서 버전·locator만
반환하며 원문 전문은 읽지 않는다. 현재 원문이 저장된 버전과 같은지 검증하는 책임은 호출자에게 있다.

## 8. 트랜잭션, 동시성, 자원과 실패

배치 전체의 추출·입력 검증·용량 검사를 commit 전에 완료한다. 읽은 collection revision을
expected_revision과 대조하고, write transaction 안에서 다시 확인한 후 변경한다.
단일 transaction에 documents, contributions, nodes, edges, evidence, revision을 함께 commit한다.
실패하면 이전 상태를 유지한다. 중간 문서만 성공한 배치를 만들지 않는다.
이미 계산한 추출 결과가 있어도 revision conflict 때 자동으로 최신 상태에 적용하지 않는다.

writer는 BEGIN IMMEDIATE로 직렬화한다. 경합 시 개방 옵션의 유한 busy_timeout_ms 뒤
StoreBusyError를 반환한다. timeout 값은 명시하며 숨은 무제한 retry는 없다.
expected_revision이 다르면 RevisionConflictError와 현재 revision을 반환한다. 원문 내용은 오류에 넣지 않는다.
동일 문서 버전 재시도는 현재 revision을 다시 읽고 명시적으로 재요청한다. CAS 검사는 no-op보다 먼저 한다.
첫 버전은 handle의 동시 호출을 지원하지 않는다. thread/process별 별도 handle을 사용하며 immutable DocumentGraphSnapshot는 공유 가능하다.

GraphLimits는 배치 문서 수·문서/배치 byte 수 및 commit 후 collection 노드·간선·근거 수를 제한한다.
상한은 호출자가 모두 명시한다. ReadLimits는 읽을 노드·간선·근거·문서 metadata 수와 총 직렬화 byte를 제한한다.
검사 중 상한을 넘으면 전체 작업을 실패시킨다. 정확히 상한과 같으면 허용한다.
공급자 입력이 이미 차지한 메모리나 SQLite 실제 파일 크기를 이 상한으로 보장하지 않는다.
추출 단계와 읽기 복사 단계의 최대 RSS·시간·DB 크기는 별도 측정한다. 강제 시간 제한은 프로세스 격리로 제공한다.

| 조건 | 결과와 부수 효과 |
| --- | --- |
| 잘못된 타입/ID/위치/관계/추출 결과 | InvalidDocumentError 또는 InvalidExtractionError. DB 변경 없음. |
| batch·collection·read 용량 초과 | CapacityError. 부분 성공 없음. |
| revision, source_revision, profile 충돌 | 해당 ConflictError. 자동 overwrite 없음. |
| read_only handle의 update/remove | ReadOnlyStoreError. 원문·DB 변경 없음. |
| 스키마 불일치/손상 | SchemaMismatchError / StoreCorruptError. 자동 migration·복구 없음. |
| transaction 실패/디스크 부족/추출기 실패 | StoreWriteError / ExtractionFailedError. commit 전 실패는 전부 rollback. |
| commit 성공 직후 프로세스 종료로 응답 불명 | 재개방 후 revision과 document digest로 상태 확인. 성공했다고 추측하지 않는다. |
| graph_search 미설치 | 선택적 bridge import의 MissingSearchDependencyError. 코어 API 사용 가능. |

공개 오류는 GraphDocumentError 계열이며 안전한 code와 원래 예외 cause를 제공한다.
원문·DB는 별도 권한 영역이다. 패키지는 지정된 DB 이외의 파일을 조회하거나 쓰지 않는다.
DB 자체와 SQLite journal/WAL/SHM sidecar는 명시적 저장 작업의 허용 쓰기 범위다.

## 9. graph_search 연결

선택적 bridge는 `prepare_search(read, *, graph_limits) -> SearchBundle`을 제공한다.
SearchBundle에는 graph_search의 GraphSnapshot과 정확히 같은 read가 들어 있다.
node_id와 edge_id는 그대로 전달하며 별도 이름 매칭이나 해시 재계산을 하지 않는다.
GraphSnapshot.build에는 선택된 모든 끝점이 포함되고 read의 관계를 누락하지 않는다.
종류·문서 범위 필터는 read 전에 selection과 추출된 관계를 선택하는 상위 서비스에서 처리한다.
첫 버전 selection 자체는 문서 선택만 지원하며 임의 종류 필터를 코어 API에 약속하지 않는다.

소비자는 read.find_items로 시작 ID를 찾고, graph_search 또는 search_paths를 호출하고,
같은 bundle.read.evidence_for로 결과의 owner ID를 조회한다. DB 최신 revision으로 다시 조회하지 않는다.
역방향 경로에서도 edge_id와 원문 근거의 source/target은 변하지 않는다.
여러 문서에서 합쳐진 간선은 관련 evidence 전부를 반환한다.
selection 때문에 외부 경로가 제외될 수 있다. 탐색 completed는 선택 그래프 내에서의 완료일 뿐 전체 corpus의 완료가 아니다.
node_limit, edge_limit, path_limit, cancelled, not_observed를 완전한 부재나 전체 순위로 바꾸지 않는다.
bridge는 search option·counter·stop_reason을 수정하거나 DB 쓰기를 수행하지 않는다.

## 10. 저장 모델과 배포

새 SQLite DB는 schema_version, collections, documents, document_contributions,
nodes, edges, evidence와 owner/contribution 연결을 관리한다. `(collection_id,document_id)`가 문서 PK이며
collection 격리와 FK 무결성을 강제한다. 근거가 여러 관계에서 사용될 때 owner 연결을 분리한다.
문서 전문은 저장하지 않으므로 재색인은 공급자 문서를 다시 받아야 한다.
read-write DB의 journal 정책, synchronous 설정, 지원 SQLite 버전은 구현 전 fault test로 정하고 기록한다.
원자성은 코드 경로 검증만이 아니라 transaction failure와 subprocess kill fixture로 증명한다.

기존 sqlite-graph-v2 DB와 새 DB를 같은 스키마로 취급하지 않는다. 기존 DB를 직접 개방·개정하지 않는다.
어댑터의 별도 cache로 먼저 평가하며 기존 public ID 보존은 [연동 설계](2026-10-04-graph-document-integration-ko.md)의 책임이다.
기존 문서 API 테스트를 새 패키지 계약으로 가져오되 Vault fixture 타입은 일반 문서 fixture로 변환한다.
독립 wheel에는 vault_graph, tests, 프로젝트 catalog, DB fixture, 원문을 포함하지 않는다.
py.typed와 공개 예제를 포함하고 깨끗한 환경에서 기본/extra 설치를 각각 검증한다.

## 11. 수용 기준과 필요한 증거

| ID | 관찰 가능한 수용 기준 | 검증 방법 |
| --- | --- | --- |
| DG-FA-01 | Vault와 graph_search가 없는 환경에서 기본 wheel만으로 저장·조회한다. | 새 venv 기본 설치, import, 임시 DB update/read/reopen. |
| DG-FA-02 | 일반 문서 구조로 규칙에 명시한 항목·관계·근거를 정확히 만든다. | 독립 기대 데이터 fixture, 규칙별 golden. |
| DG-FA-03 | 위치·ID·추출 출력 오류와 상한 초과는 저장 전에 거부한다. | Unicode span, bool, 중복, exact-limit/over-limit, 악성 extractor 결과. |
| DG-FA-04 | 이름이 같아도 다른 key는 분리하고 동일 key·관계는 근거를 합친다. | collection, kind, key 충돌 및 ID canonicalization oracle. |
| DG-FA-05 | 문서 갱신·제거가 그 문서의 기여만 교체하며 공유 관계를 유지한다. | 2문서 공유 간선과 서로 다른 alias→부분 selection→한 문서 변경/제거→마지막 근거 제거. |
| DG-FA-06 | 재시도/no-op/revision 충돌이 정의한 결과를 낸다. | digest 비교, source_revision만 변경, 동일 버전 locator 변경, extraction digest 충돌, CAS 우선, 재개방. |
| DG-FA-07 | 실패·중단 중에 부분 배치나 손상된 관계를 노출하지 않는다. | extraction/SQL 단계 fault injection, kill 후 재개방·FK 검사. |
| DG-FA-08 | 동시 writer와 reader가 하나의 일관된 revision을 관찰한다. | 두 process CAS race, read copy 중 write, immutable 결과 검증. |
| DG-FA-09 | 부분 문서 입력을 전체 corpus 교체로 해석하지 않는다. | 검색 결과 1문서 갱신 후 나머지 문서·관계 보존. |
| DG-FA-10 | 정확 조회, pagination, selection, unknown ID를 명확히 처리한다. | 동명이인, 순열, cursor 리비전/digest mismatch, missing source fixture. |
| DG-FA-11 | graph_search 결과의 간선·역방향·부분 상태를 같은 revision 근거와 연결한다. | 실제 두 wheel 설치 후 chain/diamond/cycle/parallel-kind 탐색. |
| DG-FA-12 | 원문·네트워크·모델 없이 동작하고 읽기 전용 조회는 쓰지 않는다. | sentinel 파일 해시, socket 금지, read-only 디렉터리, import write 감시. |
| DG-FA-13 | 기존 이용 경로는 연동 계약의 결과를 보존한다. | DG-IT-01–DG-IT-10의 실제 차등·공개 API 증거. |
| DG-FA-14 | 용량 제한과 실제 부하의 시간·메모리·DB 크기를 측정한다. | 문서 수/byte/근거 수/노드 차수와 host·버전이 있는 benchmark. |

oracle은 새 추출기를 호출하지 않는 명시적 기대 노드·관계·근거다. 기존 코드는 호환성 비교 대상이지
일반 계약의 유일한 정답이 아니다. 일반 계약과 legacy 결과가 다른 항목은 어댑터 테스트에서 따로 검증한다.

## 12. 검증 단계와 명령 계획

문서·패키지 생성 전인 현재 단계에서는 아래 런타임 명령을 실행했다고 표시하지 않는다.
기존 회귀 명령은 실제 테스트 파일을 기준으로 한다.

```bash
uv run --python 3.12 pytest -q tests/test_entity_extractor.py tests/test_relationship_extractor.py tests/test_graph_indexer.py tests/test_graph_store_contract.py tests/test_sqlite_graph_store.py
uv run --python 3.12 pytest -q tests/test_graph_retrieval_service.py tests/test_multi_vault_graph_retrieval.py tests/test_search_include_graph.py tests/test_graph_retrieval_read_only_boundary.py
uv run --python 3.12 ruff check src tests
uv run --python 3.12 mypy src tests
uv run --python 3.12 pytest -q
```

패키지 구현 후의 제안 명령이다. pyproject와 테스트 경로를 만들고 정확한 실행 결과를 기록해야 한다.

```bash
uv run --project packages/graph-document --python 3.12 pytest -q packages/graph-document/tests
uv run --project packages/graph-document --python 3.12 ruff check packages/graph-document/src packages/graph-document/tests
uv run --project packages/graph-document --python 3.12 mypy packages/graph-document/src packages/graph-document/tests
uv build --project packages/graph-document --out-dir packages/graph-document/dist
```

별도 venv와 별도 cwd에서 PYTHONPATH 없이 실제 생성한 wheel을 설치한다.
기본 환경에서는 vault_graph와 graph_search를 import할 수 없어야 한다.
extra 환경에서는 두 독립 wheel만으로 DG-FA-11을 실행한다.
실제 wheel metadata의 Requires-Dist와 포함 파일을 검사하고 CI에 두 설치 경로를 명시한다.
성능·subprocess fault·DB integrity 검사는 테스트 파일과 호스트를 구현 시 확정하여 명령을 추가한다.

## 13. 설계 제안, 가정과 Open Decisions

| ID | 제안 / 이유 / 대안 |
| --- | --- |
| DG-D-01 | 문서 그래프 생명주기를 하나의 깊은 패키지로 묶는다. 추출·저장·조회별 독립 배포는 경계 수만 늘린다. |
| DG-D-02 | 새 일반 계약을 설계하고 기존 내부 처리를 재사용한다. 기존 Vault 타입의 이름만 바꾸는 방법은 종속성을 남긴다. |
| DG-D-03 | 문서 기여 단위의 갱신과 CAS를 사용한다. 검색 결과를 전체 교체하는 방식은 관계를 잃는다. |
| DG-D-04 | graph_search는 optional bridge로 연결한다. 필수 의존성보다 기본 저장·조회 설치가 작고 독립성 검증이 쉽다. |
| DG-D-05 | 새 DB에서 검증하고 기존 DB를 유지한다. 제자리 migration보다 rollback과 차등 검증이 쉽다. |

모두 새 계약의 제안이며 승인된 제품 결정을 덮어쓰지 않는다.

| ID | 가정 또는 미결 사항 | 영향과 검증 / 권장 |
| --- | --- | --- |
| DG-USER-01 | 규칙 추출을 기본으로 하고 의미 추출 대안을 기입한다. | 현재 사용자 답변으로 확인. §15에서 외부 추출기 대안과 검증 gate를 정의한다. |
| ASM-02 | 공급자가 문서와 구조 정보를 파싱해 전달한다. | 기존 공급자로 일반 Document를 만들 수 있는지 DG-IT-01에서 확인한다. 형식 reader를 패키지에 몰아넣지 않는다. |
| DG-Q-01 | 지원 부하와 시간/RSS/DB 크기 목표 | 실제 사용 fixture와 host를 측정하고 출시 전에 수치 확정. 기존 불변성 엔진 SLO를 가져오지 않는다. |
| DG-Q-02 | SQLite journal·durability와 지원 버전 | WAL/rollback journal을 fault/read-only 테스트로 비교하고 구현 전 확정. 원자성과 read-only 경계는 완화할 수 없다. |
| DG-Q-03 | 기존 기본 경로 전환 | 연동 증거 후 별도 승인. 현재 DB·공개 API·기본 경로는 이 문서로 변경하지 않는다. |

## 14. 완료 기준

설계 제출은 상세 입력·갱신·조회·ID·근거·실패·배포 계약, 일반 및 기존 연동 검증 계획,
독립 리뷰와 발견사항 반영, 링크·문서 범위 확인을 갖췄을 때 완료한다.
기존 graph_search 계약은 변경하지 않는다. 구현이나 Vertical Slice 계약은 이번 산출물이 아니다.

구현 완료는 DG-FA-01–DG-FA-14와 DG-IT-01–DG-IT-10의 실행 증거가 필요하다.
운영 준비 완료는 DG-Q-01·DG-Q-02의 결정과 측정/장애 복구 합격 증거가 추가로 필요하다.
기존 시스템 기본 전환은 DG-Q-03 승인 전에는 완료했다고 주장할 수 없다.

## 15. 의미 추출 대안과 연결 준비

사용자는 규칙 추출을 기본값으로 유지하고 의미 추출의 적합한 대안을 설계에 포함하도록 했다.
추천은 **스키마로 제한한 LLM 추출기를 외부 어댑터로 연결하는 방식**이다.
첫 평가 후보는 LlamaIndex의 SchemaLLMPathExtractor다. 허용 항목·관계와 연결 규칙을 지정하고
strict 모드에서 구조를 검증할 수 있기 때문이다. 이는 이번 모듈 경계에 대한 설계 판단이며
추출 정확도나 한국어 성능이 가장 좋다는 실측 주장은 아니다.

[공식 LlamaIndex 문서](https://developers.llamaindex.ai/python/framework/module_guides/indexing/lpg_index_guide/)는
SchemaLLMPathExtractor의 스키마 제한과 strict, 오류 전달 옵션을 설명한다.
LangChain의 [LLMGraphTransformer](https://reference.langchain.com/python/langchain-neo4j/graph_transformers/llm/LLMGraphTransformer)는
허용 노드·관계와 strict_mode를 제공하는 대체 후보다.
두 도구 모두 현재 확인한 API만으로 이 패키지의 정확한 원문 span·ID·문서별 갱신 계약을 충족한다고 볼 수 없다.
그 부분은 직접 변환·검증해야 한다. LlamaIndex의 전체 index, vector retriever, graph store는 가져오지 않는다.

| ID | 대안 | 적합성 판단 |
| --- | --- | --- |
| DG-SEM-OPT-01 | SchemaLLMPathExtractor를 감싼 외부 Extractor | 스키마 제한 기능을 재사용할 수 있다. 추천 평가 후보. framework 타입을 일반 facts로 변환해야 한다. |
| DG-SEM-OPT-02 | LLMGraphTransformer를 감싼 외부 Extractor | LangChain을 이미 쓰는 소비자에게 적합하다. 이 패키지 때문에 Neo4j 저장 경로를 추가하지 않는다. |
| DG-SEM-OPT-03 | 공급자의 structured-output API를 직접 사용 | 의존성을 줄일 수 있지만 prompt·validation·재시도·평가 구현을 직접 관리해야 한다. 첫 선택으로 단정하지 않는다. |

연결은 다음 순서다.

```text
문서 → 외부 스키마 제한 추출 → 원문 근거 검증·ID 해결
     → EntityFact / RelationFact → graph_document → graph_search
```

일반 Extractor Protocol을 구현한 wrapper가 결과를 변환한다. 문서별 기본 규칙 facts와 의미 facts를
합치는 CompositeExtractor도 외부에서 구현한다. 규칙·모델·prompt·schema·adapter 버전을 모두 profile_digest에
포함하고 새 profile은 새 collection으로 색인한다. 저장·조회 코어에는 모델 client나 prompt를 넣지 않는다.
의미 relations의 rule_id는 semantic prefix와 버전을 가지며 evidence에서 규칙 결과와 구분한다.

LLM이 생성한 quote와 source segment ID를 입력의 실제 text와 대조한다. quote가 존재하지 않거나
반복되어 위치를 유일하게 정할 수 없으면 그 후보를 저장하지 않고 rejection diagnostic을 남긴다.
유효 quote는 정확 span으로 변환한다. 단순 문자열 일치는 근거의 존재만 확인하며 관계 의미의 정확성을 증명하지 않는다.
문서 identity를 제외한 의미 relation에는 실제 본문 span이 최소 1개 있어야 한다.
문서 안의 명령문은 데이터로만 다루고 추출기는 외부 action/tool 실행 기능을 제공하지 않는다.

항목 key는 모델이 제안한 이름을 곧바로 전역 ID로 쓰지 않는다.
명시적 문서 참조나 공급자의 정체성 사전으로 해결한 항목만 공유 key를 쓰고,
나머지는 `(document_id, local_mention_key)`로 구분한 불투명 key를 사용한다.
동명이인을 자동 통합하지 않는다. 거부한 후보 수와 이유는 ExtractedDocument warnings에 넣는다.
성공했지만 관계가 없는 문서와 provider timeout·잘못된 출력은 구분하며,
오류를 빈 facts로 바꾸어 기존 관계를 삭제하는 fallback은 금지한다.
strict schema의 문법 검증만으로 잘못된 의미 관계가 제거된다고 가정하지 않는다.

외부 추출 결과는 `(document_id, input_digest, profile_digest)`에 대한 불변 artifact로 cache한다.
input_digest에도 문서 ID와 source_revision이 들어가므로 같은 본문을 가진 다른 문서의 facts를 재사용하지 않는다.
재시도는 같은 artifact를 재생한다. temperature=0만으로 결정성을 보장한다고 주장하지 않는다.
같은 입력/profile에 다른 artifact를 채택하려면 extractor profile을 바꾸고 새 collection에 색인한다.
외부 cache에도 원문 보존 기간·위치·접근 정책을 명시하며 graph_document가 그 cache를 관리하지 않는다.
credentials, 모델 공급자, 외부 전송 허용, 비용·시간·retry 상한은 외부 어댑터의 명시적 설정이다.
무제한 자동 요청이나 코어 기본 설치 시 모델 호출은 없다.

### 의미 추출을 활성화하기 전 필요한 검증

| ID | 검증 항목 | 필요한 증거 |
| --- | --- | --- |
| DG-SEM-01 | 일반 Protocol·schema·오류 변환 | fake provider의 정상·malformed·허용 밖 관계·timeout·빈 정상 결과 fixture. |
| DG-SEM-02 | 근거와 동명이인 | 없는 quote, 반복 quote, Unicode span, 같은 이름의 다른 항목, source segment 불일치. |
| DG-SEM-03 | 원문으로 지지되는 관계의 정확도 | 실제 한국어/영어 문서의 사람 라벨 평가집에서 relation precision/recall, 근거 일치율, 미지원 주장 비율. |
| DG-SEM-04 | 재현성과 비용·시간 | cache replay, 동일 본문/다른 document_id, source_revision만 변경, 모델·prompt profile 격리, token·비용·latency·retry 계수. |
| DG-SEM-05 | 기본 기능과 저장 실패 경계 | 모델 없이 기본 설치, provider 실패 때 기존 DB 유지, 근거 있는 facts만 commit, 네트워크 허용 여부. |

평가집, 모델 후보, 허용 오차와 비용/시간 수치는 의미 추출 구현 계약에서 확정한다.
이를 확정하고 통과하기 전에는 “바로 사용 가능한 검증된 의미 추출 기능”이나 기본 활성화를 선언하지 않는다.
이번에는 연결 계약과 평가 방법을 설계했으며 의미 추출기를 구현하거나 모델 평가를 실행하지 않았다.


## 독립 리뷰와 설계 검증 기록

2026-10-04 별도 read-only review agent가 일반 계약, 기존 코드 경계, graph_search 계약을 검토했다.
첫 리뷰의 세 보정사항은 전체 Document digest와 원문 버전 갱신, 선택별 alias 기여 집계,
증분 갱신 후 전체 revision manifest의 구성·복구다. 반영 후 재리뷰에서 설계 제출 Passed를 받았다.

문서 링크·anchor·code fence·추가 영역 공백, DG-FA-01–14/DG-IT-01–10/DG-SEM-01–05 번호,
검증 명령의 기존 테스트 파일 존재를 확인했다. 기존 graph_search 두 계약의 hash가 동일하고,
SPEC의 신규 목차·§11을 제외한 본문도 작업 시작 시점과 동일함을 확인했다.
패키지 코드·DB·테스트·factory는 변경하지 않았다. 런타임 검증 계획은 실행 증거가 아니다.
