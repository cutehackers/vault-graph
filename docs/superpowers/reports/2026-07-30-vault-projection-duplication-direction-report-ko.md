# Vault와 Vault Graph 중복 해소 방향 보고서

작성일: 2026-07-30

상태: 다음 제품 확장의 선행 게이트

## 1. 결론

코드 인덱스와 하네스 통합을 시작하기 전에 **Round 0 — Authority &
Projection Hygiene**를 완료해야 한다.

근본 원칙은 다음과 같다.

> 하나의 내용 본문은 권한 계층에서 한 번만 소유하고, 검색·벡터·그래프·탐색
> 뷰는 본문을 다시 소유하지 않고 안정된 정체성을 참조한다.

다만 모든 반복이 잘못된 중복은 아니다.

- `raw/`는 원본 증거다.
- `wiki/`는 원본에서 검증·컴파일한 지속 지식이다.
- 둘은 내용이 일부 겹쳐도 역할이 다르므로 함께 존재할 수 있다.
- 문제는 두 계층을 같은 검색 결과로 반복 노출하거나, Vault Graph의 여러
  저장소가 같은 청크 본문을 각각 다시 보관하는 것이다.

따라서 해결 방향은 **권한 중복 제거**, **검색 결과 중복 제거**, **파생
저장소의 본문 중복 제거**를 분리해서 다루는 것이다.

## 2. 현재 구조에서 확인된 중복

### 2.1 Vault 내부

현재 Vault의 계층은 다음과 같다.

```text
raw source
-> source page
-> durable wiki synthesis
-> index / maps / log / reports
```

각 계층의 의도는 다르지만 다음 중복 위험이 있다.

- `raw/` 원문과 `wiki/sources/` source page가 원문 내용을 함께 보관할 수 있다.
- 동일한 설명이 여러 durable wiki page에 복사될 수 있다.
- `wiki/index.md`와 `wiki/maps/`가 페이지 frontmatter의 제목·요약·링크를
  수동으로 다시 보관할 수 있다.
- `scratch/reports/`가 wiki 결과를 다시 서술하고 장기간 남을 수 있다.

현재 source page 생성기는 원문 전체를 복사하지 않고 canonical path, hash,
요약, 등록 상태를 기록하므로 기본 방향은 올바르다. 이 계약을 명시적으로
고정해야 한다.

### 2.2 Vault Graph의 기본 수집 범위

현재 기본 `content_scopes`는 다음 네 범위를 모두 포함한다.

```text
raw
wiki
docs
scratch/reports
```

이 구성은 원본 증거, 정제 지식, 운영 계약, 일회성 감사 보고서를 한 검색
후보군에 섞는다. 같은 사건이나 개념이 raw, source page, wiki page, report에
각각 나타나면 사용자는 비슷한 검색 결과를 여러 개 받게 된다.

이는 디스크 중복보다 더 위험한 **의미적 검색 중복**이다. 결과 수와 토큰을
소비하고, 어느 결과가 권위 있는지 에이전트가 다시 판단하게 만든다.

### 2.3 Vault Graph의 파생 저장소

현재 로컬 저장 구조는 다음 본문 중복을 만든다.

1. `metadata.sqlite`의 `chunks.text`가 canonical chunk 본문을 보관한다.
2. 같은 SQLite DB의 FTS5 `keyword_chunks.text`가 본문을 다시 보관한다.
3. `graph_evidence_refs.excerpt`가 청크 일부를 다시 복사한다.
4. context pack과 answer는 같은 excerpt를 응답용 객체에 다시 조립한다.

Chroma vector store는 현재 임베딩과 식별 metadata만 저장하고 본문을
재저장하지 않는다. 이 방식이 파생 저장소의 올바른 기준이다.

## 3. 정보 역할 모델

모든 파일과 레코드는 다음 역할 중 하나를 가져야 한다. 역할은 디렉터리만으로
추정하지 않고 frontmatter type, canonical source 관계, path를 함께 사용해
결정한다. 예를 들어 `wiki/sources/`는 `wiki/` 아래에 있지만 canonical
knowledge가 아니라 source manifest다.

| 역할 | 예시 | 권위 본문 소유 | 기본 검색 |
| --- | --- | ---: | ---: |
| 원본 증거 | `raw/` | 예 | 아니오 |
| 지속 지식 | canonical `wiki/` page | 예 | 예 |
| 출처 manifest | `wiki/sources/` | 아니오 | 아니오 |
| 운영 계약 | `AGENTS.md`, `docs/` | 예 | 작업 유형별 |
| 생성 탐색 뷰 | `wiki/index.md`, `wiki/maps/` | 아니오 | 아니오 |
| 운영 이력 | `wiki/log.md` | event만 | 아니오 |
| 임시 감사 산출물 | `scratch/reports/` | 제한적 | 아니오 |

### 원본 증거

- 수집 당시 원문을 그대로 보존한다.
- 검색의 기본 답변 후보가 아니라 wiki claim의 근거로 사용한다.
- 사용자가 원문 확인이나 provenance drill-down을 요청할 때만 검색한다.

### 지속 지식

- 재사용되는 하나의 주제·결정·워크플로는 한 canonical page가 본문을
  소유한다.
- 다른 페이지는 본문을 복사하지 않고 링크, 짧은 요약, 관계만 둔다.
- 중복 후보는 자동 병합하지 않고 기존 Vault review gate로 보낸다.

### 생성 탐색 뷰

- `wiki/index.md`와 `wiki/maps/`는 frontmatter와 링크 그래프에서
  결정적으로 생성한다.
- 사람이 별도의 의미 설명을 수동으로 복사하지 않는다.
- stale 여부를 `maps build --check`와 같은 검증으로 확인한다.
- 파일에는 렌더링된 제목·요약·링크가 존재할 수 있지만 이는 재구축 가능한
  탐색 projection이며 권위 있는 claim 본문이 아니다.

### 운영 이력

- `wiki/log.md`는 의미 본문을 복사하지 않고 event type, 대상 ID, revision,
  결과만 기록한다.
- 설명이 필요하면 canonical page나 report를 링크한다.
- 검색 결과의 지식 후보가 아니라 변경 추적 증거로만 사용한다.

### 임시 감사 산출물

- 보고서는 작업 당시 증거와 결과를 감사하기 위한 산출물이다.
- durable claim의 원본이 되지 않는다.
- 기본 Vault Graph 색인에서 제외한다.
- 보존 기간과 승격 규칙은 Vault가 소유한다. Vault Graph가 삭제하지 않는다.

## 4. “하나의 본문, 여러 참조” 저장 모델

Vault Graph의 목표 구조는 다음과 같다.

```text
documents
  document identity, role, path, revision, hashes
        |
        v
chunks
  chunk identity, document, anchor, blob_hash
        |
        v
content_blobs
  blob_hash -> plaintext body
        |
        +--> contentless FTS row -> chunk_id
        +--> vector -> chunk_id
        +--> graph evidence -> chunk_id + offsets
        +--> context/answer -> resolve on demand
```

### Canonical plaintext

`content_blobs` 또는 동등한 내부 경계가 distinct chunk plaintext를 한 번만
보관한다. `chunks`는 본문 대신 `blob_hash`를 참조한다.

전역 해시 하나만으로 서로 다른 증거를 병합해서는 안 된다. 논리적 증거
정체성은 다음을 유지한다.

```text
(vault_id, source_role, path, revision, anchor, content_hash)
```

동일한 본문을 가진 두 문서는 physical blob을 공유할 수 있지만, provenance,
human lock, lifecycle, path는 각각 유지한다.

### Keyword index

FTS는 검색을 위한 역색인만 소유한다. 원문을 검색 테이블에 다시 보관하지
않는 contentless 또는 external-content FTS 계약으로 변경한다.

검색 hit는 `chunk_id`를 반환하고 본문은 canonical chunk/blob store에서
해결한다.

### Vector index

현재처럼 embedding, `chunk_id`, model spec, revision만 보관한다. 본문을
vector store metadata나 document 필드에 추가하지 않는다.

### Graph index

`graph_evidence_refs`는 다음만 보관한다.

- owner graph record
- evidence `chunk_id`
- anchor 또는 byte/line offsets
- evidence content hash와 revision

`excerpt`는 저장하지 않는다. 조회 시 canonical chunk에서 필요한 길이만
해결한다.

### Context pack과 answer

- 기본적으로 요청 시 생성하는 일시적 projection이다.
- 메모리 cache는 bounded size와 수명만 갖는다.
- 지속 저장이 필요하면 본문 복사본이 아니라 request, selected evidence IDs,
  revisions, render policy를 저장하고 다시 렌더링한다.
- durable knowledge로 승격할 때만 Vault draft/publish workflow를 사용한다.

## 5. 역할 기반 검색 정책

기본 검색은 모든 디렉터리를 같은 비중으로 검색하지 않는다.

### 권장 기본 범위

```text
default knowledge search: canonical wiki knowledge roles only
operating search: docs + selected wiki
evidence drill-down: raw + source manifests
audit search: explicitly requested scratch/reports
```

현재 `raw`, `wiki`, `docs`, `scratch/reports` 전체를 기본값으로 사용하는
계약은 변경해야 한다.

호환성을 위해 기존 catalog를 자동으로 조용히 바꾸지 않는다. migration
preview에서 다음을 보여준 뒤 사용자가 적용한다.

- 현재 등록 범위
- 새 role 기반 기본 범위
- 기본 검색에서 제외되는 문서 수
- rebuild 대상
- 복구 방법

## 6. 검색 결과의 논리적 중복 제거

디스크에서 본문을 한 번만 저장해도 raw와 wiki의 관련 결과가 동시에 상위에
나오면 사용자 관점의 중복은 남는다.

### Evidence Family

검색 전에 다음 관계로 provenance family를 만든다.

- source page의 `canonical_source`
- wiki page의 `derived_from`
- claim evidence reference
- 명시적 supersedes / redirects / related 관계

같은 family 안에서는 역할 우선순위에 따라 기본 대표 결과 하나를 선택한다.

```text
canonical durable wiki
  > active source page
  > raw evidence
  > operational report
```

대표 결과는 다른 항목을 버리지 않고 다음처럼 제공한다.

```text
result: canonical wiki page
supporting_evidence:
  - source page
  - raw source
audit_records:
  - ingest report
```

이 방식은 provenance를 보존하면서 결과 목록과 컨텍스트 토큰의 반복을
줄인다.

### 병합하지 않는 경우

- 서로 다른 출처가 우연히 같은 본문을 가진 경우
- contested 또는 deprecated 상태가 다른 경우
- human-locked 문서
- 서로 다른 시점의 revision이 비교에 필요한 경우
- source와 synthesis처럼 역할이 다른 경우

exact hash는 저장 최적화 신호이지 의미 동일성의 최종 판정이 아니다.

## 7. Round 0 실행 순서

### 0A — Inventory와 측정

먼저 읽기 전용 audit 명령으로 현재 상태를 측정한다.

- 역할별 문서·청크 수
- unique plaintext bytes
- metadata/FTS/graph에 반복 저장된 plaintext bytes
- provenance family별 검색 결과 중복률
- dangling evidence reference
- default scope에 포함된 report와 generated view 수

현재 실행 환경에는 확인 가능한 영구 Vault Graph state가 없었으므로, 실제
수치는 구현 전 사용자 state path에서 별도로 측정해야 한다.

### 0B — Role과 authority 계약

- `source_role`과 provenance family 계약을 정의한다.
- 기본 검색 범위를 canonical wiki 중심으로 변경한다.
- raw, docs, reports는 명시적 mode로 분리한다.
- source page와 generated view의 비복제 규칙을 Vault 계약에 고정한다.

### 0C — Single-body projection

- canonical chunk/blob store를 추가한다.
- FTS를 contentless/external-content 방식으로 이전한다.
- graph evidence의 persisted excerpt를 제거한다.
- vector store의 metadata-only 본문 정책을 contract test로 고정한다.

### 0D — Retrieval collapse

- provenance family를 만든다.
- 기본 결과는 family별 대표 한 개를 반환한다.
- raw와 report는 supporting evidence 또는 audit link로 묶는다.
- 명시적 `evidence` 또는 `audit` mode에서는 전체를 펼칠 수 있게 한다.

### 0E — Migration과 rebuild

- 기존 state를 in-place로 부분 수정하지 않는다.
- 새 schema namespace에 전체 rebuild한다.
- 검증 후 원자적으로 active projection을 전환한다.
- 실패하면 기존 projection을 유지한다.
- Vault 파일은 수정하지 않는다.

## 8. 완료 게이트

다음 조건을 모두 만족하기 전에는 코드 인덱스 Round 1을 시작하지 않는다.

### 권한

- raw, wiki, docs, generated view, report 역할이 기계적으로 구분된다.
- source page는 원문 전체를 복사하지 않는다.
- Vault Graph state는 durable knowledge로 사용되지 않는다.

### 물리적 중복

- distinct chunk plaintext는 Vault Graph state에서 canonical body store 한
  곳만 소유한다.
- FTS와 graph store에 검색 가능한 plaintext 복사본이 없다.
- vector store는 embedding과 식별 metadata만 보관한다.

### 논리적 중복

- 기본 top-k 결과에서 같은 provenance family는 한 번만 나타난다.
- raw와 reports는 기본 결과가 아니라 supporting evidence/audit로 연결된다.
- 명시적 evidence mode에서는 출처를 손실 없이 펼칠 수 있다.

### 무결성

- 모든 keyword, vector, graph hit가 canonical chunk로 해결된다.
- dangling evidence reference가 0건이다.
- 동일 Vault revision과 spec으로 rebuild하면 기능적으로 동등한 결과를 만든다.
- stale generated view와 stale projection이 명시적으로 감지된다.

### 측정

다음 지표의 baseline과 변경 후 결과를 보고한다.

```text
plaintext_amplification =
  stored searchable plaintext bytes / unique canonical chunk bytes

result_family_duplication =
  repeated provenance-family results / returned results
```

목표:

- `plaintext_amplification`: canonical body 1회 보관
  - FTS 역색인과 embedding binary는 plaintext 복사로 계산하지 않는다.
- `result_family_duplication`: 기본 검색에서 0
- `dangling_evidence_refs`: 0
- 기존 evidence recall과 citation resolution의 비열화 없음

## 9. 이후 프로젝트 방향과의 관계

Round 0가 완료되면 이후 코드 인덱스도 같은 계약을 따른다.

- 저장소 파일 본문은 canonical code body store 한 곳만 소유한다.
- AST, FTS, embedding, code graph는 `file_id` 또는 `symbol_id`를 참조한다.
- 코드와 Vault 문서가 같은 개념을 다뤄도 하나로 병합하지 않는다.
- `ProjectContextService`가 대표 증거를 선택하고 supporting evidence를
  연결한다.

따라서 중복 해소는 별도 최적화 작업이 아니라 향후 프로젝트 증거 계층의
필수 토대다.

## 10. 권장 결정

1. 코드 인덱스 구현을 즉시 시작하지 않는다.
2. Round 0를 별도 설계·구현 계획으로 만든다.
3. 기본 검색을 canonical wiki 중심으로 전환한다.
4. Vault Graph 내부는 single-body, reference-only projection으로 이전한다.
5. Round 0 완료 지표가 확인된 뒤 코드 인덱스 Round 1을 시작한다.
