# 설계 용어

<a id="vg-mod-functional-groups"></a>
## VG-MOD-20261015: 기능 그룹

상태: Confirmed. 출처: 사용자가 간결한 그룹 이름을 선택하고 관련 문서 수정과 실제 디렉터리 배치를 승인했다. [부모 명세](specs/2026-10-15-vault-graph-modular-architecture-ko.md)와 [현재 구조도](reports/2026-10-15-modularization-completion-ko.md)에 적용한다.

| 구분 | 이름 | 의미·소유 범위 |
|---|---|---|
| 그룹1 | `indexing` | 문서 준비·색인·세대 발행. M02·M03·M04 |
| 그룹2 | `retrieval` | 검색·그래프 조회·근거 연결·결과 설명. M05·M06·M07·M13 |
| 그룹3 | `context` | 문맥 팩·기억 조회·발췌 답변. M08·M09·M10 |
| 그룹4 | `project` | 코드 투영·영향 조회·프로젝트 문맥 조합. M11·M12 |
| 그룹5 | `operation` | 범위·준비 상태·진단·실행 운영·명시적 연동 설정. M01·M14·M15·M16·M17 |
| 지원1 | `interface` | CLI·MCP·HTTP 진입점과 서비스 구성 지점 |
| 지원2 | `storage` | 메타데이터·벡터·그래프·코드 파생 저장소의 포트와 구현 |
| 지원3 | `engine` | 독립 배포 패키지 5개: `graph_search`, `graph_document`, `text_embeddings`, `vector_search`, `vector_index` |

다섯 기능 그룹과 `interface`·`storage`는 실제 Python 디렉터리이다. 하위 모듈의 정식 경로와 의존 규칙은 [현재 구현 아키텍처](../ARCHITECTURE.md)를 따른다. `engine`은 기존 `packages/`의 배포 패키지 5개를 묶는 논리적 분류이며 실제 디렉터리를 추가하지 않는다. 배포명과 M 번호는 유지한다. `project/context`의 문맥 조합은 `project`, `operation/integration/project_binding_catalog.py`의 설정 기록은 `operation`에 속한다.

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
