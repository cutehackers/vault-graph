# 설계 용어

<a id="sel-20261015"></a>
## SEL-20261015: 검색 대상·근거 연결

범위: [SEL 부모 명세](specs/2026-10-15-search-evidence-linking-ko.md). 결정: [프로젝트 기록](../DECISIONS.md#sel-20261015-scope).

| 용어 | 실제 의미·경계 | 출처 | 상태 |
|---|---|---|---|
| 검색 대상·근거 연결 | Vault의 검색 대상 ID와 문서·청크 근거를 대응시키는 내부 기능. 점수 통합과 경로 탐색은 별도이다. | 사용자 요청·범위 답변 | Confirmed |
| 근거 키 | (evidence_vault_id, document_id, chunk_id). 현재 문서·청크를 MetadataStore에서 찾는 키이다. | MetadataStore·GraphEvidenceRef | Confirmed |
| 소유자 키 | (owner_kind, owner_vault_id, owner_id). 노드 또는 관계가 근거를 참조한다. 근거 Vault와 같다고 가정하지 않는다. | GraphEvidenceRef·EntityRecord·RelationshipRecord | Confirmed |
| 역조회 | 근거 키에서 그 근거를 참조하는 그래프 소유자들을 찾는 조회. 주변 그래프 확장은 하지 않는다. | 사용자 ‘추가하라’ 답변 | Confirmed |
| 양방향 연결 | 소유자→근거와 근거→소유자를 모두 다루는 다대다 연결. 양방향 간선이나 벡터 유사도 검색이라는 뜻은 아니다. | 사용자 범위 선택·기존 근거 모델 | Confirmed |
| EvidenceLinker | 공통 연결 기능의 제안 내부 진입점. 별도 배포 패키지가 아니다. | 부모 §5–6 | Candidate |
| coverage | 모든 입력을 해당 허용 범위에서 결론 낼 수 있었는지 표시하는 제안 결과 필드. 근거 존재나 전역 관계 부재를 뜻하지 않는다. | 부모 §6.3 | Candidate |

`key_complete`는 제안된 위치별 완료 표시다. `linked/false`는 일부 연결만 반환했다는 뜻이며, 전역 coverage와 함께 해석한다. 출처: 부모 §6.3. 상태: Candidate.
