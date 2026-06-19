# Phase 6 설계 문서

이 폴더는 `docs/SPEC.md`에 모두 넣기에는 긴 Phase 6 상세 설계 문서를
보관합니다.

`docs/SPEC.md`는 여전히 제품과 아키텍처의 최상위 계약입니다. 이 폴더의
문서들은 Vault Graph가 Vault 위의 읽기 전용, 재생성 가능, evidence-first
access layer라는 경계를 유지하면서 Phase 6 memory와 explorer projection을
어떻게 추가해야 하는지 설명합니다.

Phase 6의 memory는 projection 용어이지 writable memory database를 추가한다는
의미가 아닙니다. Mem0나 MemMachine 같은 외부 system은 future adapter/export
target으로만 남깁니다.

## 문서

| 파일 | 역할 |
| --- | --- |
| `2026-06-18-phase-6-memory-and-explorer-views-overview-design.md` | 전체 slice 개요, 공통 불변조건, 의존성, 구현 handoff map |
| `2026-06-18-phase-6a-result-explanation-contract-design.md` | Phase 6A result explanation records, bounded MCP explanation cache, `explain_result` service boundary |
| `2026-06-18-phase-6b-project-decision-issue-memory-design.md` | Phase 6B project, decision, issue memory projection |
| `2026-06-18-phase-6c-timeline-health-explorer-design.md` | Phase 6C recent timeline, projection freshness, backend health, scale-up readiness views |

한글 사본은 동일한 파일명에 `-ko.md`를 붙입니다.

## 읽는 순서

1. 최상위 제품 계약은 `docs/SPEC.md`를 읽습니다.
2. Phase 6 공통 불변조건과 의존성은
   `2026-06-18-phase-6-memory-and-explorer-views-overview-design.md`를
   읽습니다.
3. 구현 계획을 작성하기 전에 대상 slice 문서를 읽습니다.
