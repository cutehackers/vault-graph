# Round 0-G 완료 보고서

## 결론

Round 0-G의 목표였던 저장·검색 중복 제거를 완료했다. Vault는 계속 유일한
지속 지식 원본이며, Vault Graph는 삭제 후 재구축할 수 있는 읽기 전용 접근
계층이다. 다음 단계는 공동 완료 지표를 기준선으로 고정한 뒤 Round 1 코드
인덱스를 설계·구현하는 것이다.

## 완료 내용

- 문서를 7개 권위 역할로 분류하고 `canonical_source`, `derived_from`,
  `supersedes`, `redirects` 링크를 provenance family로 연결했다.
- 서로 같은 chunk 본문은 `metadata-v2.content_blobs`에 한 번만 저장한다.
- `sqlite-keyword-v2`는 contentless FTS이며 plaintext를 별도로 저장하지 않는다.
- `chroma-vector-v2`는 embedding과 참조/역할/계보 메타데이터만 유지한다.
- `sqlite-graph-v2` evidence reference에서 excerpt 저장을 제거했다.
- 기본 `knowledge` 검색은 canonical knowledge만 검색하고 family당 한 결과만
  반환한다. 원문과 source manifest, 생성 view와 감사 기록은 compact reference로
  연결한다. `evidence`, `operating`, `audit`, `all` 모드로 명시적 확장이 가능하다.
- `vg projection-audit`를 추가했고 전체 재구축은 격리 generation을 완성한 뒤
  active manifest 하나를 원자적으로 교체한다.

## 실제 `~/vault` 검증

검증 대상 Vault commit은
`8ff2ba59279652ae8565a6e9e9dfb60f02a02f3c`이다. 임시 상태 디렉터리에서
208개 문서, 1,941개 chunk/vector, 2,775개 graph entity, 2,533개
relationship, 11,591개 graph evidence reference를 full rebuild했다.
수정 완료 후 full rebuild를 다시 수행했을 때 문서·chunk/vector·entity·relationship·
evidence reference 수가 같았고, revision/timestamp를 제외한 `Vault Graph` 검색의
10개 경로 순서, supporting reference 수, duplication 및 warning 결과도 같았다.

| 지표 | 결과 |
| --- | ---: |
| canonical blob | 1,755 |
| canonical blob bytes | 1,146,107 |
| logical chunk bytes | 1,170,471 |
| search projection plaintext bytes | 0 |
| plaintext amplification | 1.0 |
| dangling keyword refs | 0 |
| dangling vector refs | 0 |
| dangling graph refs | 0 |
| `Vault Graph` knowledge 결과 | 10 |
| result family duplication | 0.0 |
| 검색 warning | 0 |

역할별 문서는 audit record 102, canonical knowledge 41, generated view 8,
operating contract 9, operation log 1, raw evidence 23, source manifest 24개였다.
활성 schema는 metadata-v2, sqlite-keyword-v2, chroma-vector-v2,
sqlite-graph-v2이다.

실제 검증 중 YAML 날짜가 JSON 저장 경계를 통과하지 못하는 문제와 Chroma 내부
queue 압축 후 read-only vector payload가 사라지는 문제를 발견했다. 날짜는
ingestion 경계에서 ISO 문자열로 정규화하고, embedding payload는 Vault Graph가
소유하는 명시적 sidecar table로 유지하도록 회귀 테스트와 함께 수정했다.

검증 전후 Vault Git status는 clean이었고 commit은 동일했다. `.git`을 제외한
전체 파일 SHA-256 집계도 양쪽 모두
`443b7238b7575a26fa0e25233110d9da398bd4b03424256789d436b15cc97532`로
동일했다. Vault Graph는 `~/vault`를 수정하지 않았다.

## Vault Builder 릴리즈

Vault 계약 전환 문서는 vault-builder `main`의 merge commit
`bd7f162`로 통합해 origin에 push했다. merge 전후 release gate에서 wiki 166개,
migration 151개 테스트와 lint, health, maps, metrics가 통과했다.

## 현재 작업 흐름

```text
Round 0-V: Vault 계약과 검증 보강       완료
  -> Round 0-G: 저장·검색 중복 제거     완료
  -> 공동 완료 지표 검증                완료
  -> Round 1: 코드 인덱스                다음
  -> Round 2: MCP·코딩 하네스            이후
```

Round 1은 아직 시작하지 않았다. 코드 저장소는 실행 가능한 코드의 권위 원본으로
유지하고, Round 0-G에서 확립한 단일 plaintext 소유권·reference-only projection·
원자적 generation 원칙을 코드 인덱스에도 그대로 적용해야 한다.
