# Phase 6 Memory And Explorer Views 개요 설계

Status: Draft for implementation planning

Date: 2026-06-18

Scope: Phase 6 cross-slice overview

## 1. 목적

Phase 6는 Vault Graph의 기존 retrieval, graph, context-pack, MCP, status
service를 memory와 explorer projection으로 확장합니다. 목표는 사용자와
agent가 다음 질문에 답할 수 있게 하는 것입니다.

- 현재 프로젝트 상태는 무엇인가?
- 이 작업과 관련된 중요한 결정은 무엇인가?
- 아직 해결되지 않은 질문이나 follow-up은 무엇인가?
- 최근 무엇이 바뀌었는가?
- 이 결과는 왜 반환되었는가?
- 어떤 backend나 projection이 stale, unavailable, not scale-up-ready 상태인가?

산출물은 answer generation, UI, hosted monitoring, remote backend migration,
새 memory database가 아닙니다. 산출물은 기존 Vault-derived state 위에 만든
bounded, evidence-linked projection을 노출하는 읽기 전용 application service와
MCP resource/tool입니다.

Mem0, MemMachine 같은 외부 memory-layer project는 참고할 만하지만, Phase 6는
그들의 writable persistent-memory model을 따르지 않습니다. Vault Graph에서
memory는 read-only projection을 뜻합니다. Generic writable memory API, hidden
episode log, profile memory database, external memory server dependency를 core에
추가하지 않습니다.

모든 Phase 6 output은 working context입니다. memory projection 안의 insight가
durable knowledge가 되어야 한다면, 반드시 Vault의 source capture, validation,
release gate, Git history workflow를 통과해야 합니다.

## 2. 문서 맵

| 문서 | 역할 |
| --- | --- |
| `README.md` | Phase 6 design folder index와 reading order |
| `2026-06-18-phase-6-memory-and-explorer-views-overview-design.md` | 전체 slice 개요, 공통 불변조건, handoff map |
| `2026-06-18-phase-6a-result-explanation-contract-design.md` | result explanation contract, bounded MCP explanation cache, `explain_result` service boundary |
| `2026-06-18-phase-6b-project-decision-issue-memory-design.md` | project, decision, issue memory projection |
| `2026-06-18-phase-6c-timeline-health-explorer-design.md` | timeline, projection freshness, backend health, scale-up readiness views |

`docs/SPEC.md`는 최상위 제품 계약입니다. 이 폴더는 Phase 6의 구현 설계
계층입니다.

## 3. Phase Slices

| Slice | Change | User Value | Explicitly Not Included |
| --- | --- | --- | --- |
| Phase 6A | result explanation record와 bounded MCP explanation cache 추가 | agent가 현재 MCP session에서 반환된 결과에 대해 `explain_result`를 호출할 수 있음 | durable result history, answer synthesis, project memory summaries |
| Phase 6B | indexed evidence 위에 deterministic project, decision, issue memory projection 추가 | agent가 whole-Vault scan 없이 현재 상태와 open questions를 확인할 수 있음 | LLM-written summaries, automatic Vault publication, autonomous issue resolution |
| Phase 6C | recent timeline, freshness, backend health, scale-up readiness explorer view 추가 | 사용자와 agent가 최근 변화와 projection 신뢰도를 확인할 수 있음 | hosted monitoring, remote backend migration, UI dashboards |

이 순서는 Phase 6를 단순하게 유지합니다. 먼저 기존 결과를 explainable하게
만들고, 그 다음 memory projection을 조립하고, 마지막으로 recent-change와
운영 explorer view를 노출합니다.

## 4. 공통 불변조건

- Vault는 durable source of truth입니다.
- Memory projection은 derived, read-only, disposable, rebuildable입니다.
- Evidence chunk가 authority unit입니다:
  `(vault_id, document_id, chunk_id)`.
- Memory output은 Vault IDs, evidence references, warnings, store revisions,
  generated timestamps, freshness status를 보존해야 합니다.
- resolved evidence가 없는 memory item은 숨겨진 사실이 아니라 warning입니다.
- MCP tool은 application service 위의 adapter입니다. service boundary가 있으면
  SQLite, Chroma, rustworkx, Vault files를 직접 조회하지 않습니다.
- MCP resource와 tool은 Vault content를 write, rename, rewrite, delete,
  publish하지 않습니다.
- 기본 scope는 active Vault입니다. Cross-Vault output은 명시적인 Vault IDs 또는
  all-Vault 선택이 필요합니다.
- Cross-Vault memory projection은 evidence를 Vault ID별로 그룹화합니다.
  서로 다른 Vault의 decision, issue, entity, document를 title이나 name만으로
  merge하지 않습니다.
- Missing, stale, unavailable, incompatible projection state는 structured
  warning과 safe next command로 보여야 합니다.
- Phase 6는 generic `Memory.create`, `Memory.query`, `Memory.upsert`,
  `Memory.link`, `Memory.audit`, `MemoryStore` contract를 노출하지 않습니다.
  `ExplainResultService`, `ProjectMemoryService`, `DecisionMemoryService`,
  `IssueMemoryService`, `TimelineMemoryService` 같은 구체적인 read service를
  사용합니다.

## 5. 책임 맵

| Component | Owns | Must Not Own |
| --- | --- | --- |
| `MetadataStore` | document/chunk evidence authority, frontmatter, content hashes, revisions | memory grouping policy, answer prose |
| `RetrievalService` | ranked evidence and signal explanations | project memory assembly |
| `GraphRetrievalService` | related entities and decision traces | durable decision authority |
| `ContextPackBuilder` | bounded task context assembly | current project memory summary |
| `IndexService.status(...)` | backend health and projection freshness inputs | MCP serialization policy |
| `vault_graph.memory` | project, decision, issue, timeline, explanation projection services | direct backend mutation, Vault publication, generic writable memory storage |
| `vault_graph.mcp` | MCP argument DTOs, cache ownership, tool/resource registration, error mapping | memory algorithms or evidence selection |

## 6. 공통 데이터 흐름

Phase 6 service는 기존 application service와 storage interface를 통해 읽습니다.

```text
MCP tool/resource or future CLI surface
  -> resolve QueryScope
  -> open read-only application service
  -> assemble projection from MetadataStore, RetrievalService, GraphRetrievalService, or IndexService
  -> resolve evidence through MetadataStore
  -> return structured JSON with warnings, revisions, and resource links
```

Phase 6 service는 side effect로 indexing을 실행하지 않습니다. state가 없으면
응답은 `vg index` 또는 `vg status` 실행을 안내해야 합니다.

## 7. Memory Taxonomy And External Layer Boundary

Phase 6는 유용한 memory-layer taxonomy를 받아들이되, 새 memory store를 만들지
않습니다.

- Working memory는 `ResultExplanationCache`와 generated context-pack resource
  cache 같은 bounded runtime cache에 대응합니다. Current-process state이며 언제든
  사라질 수 있습니다.
- Semantic 또는 project memory는 `MetadataStore`, retrieval signal, graph trace,
  frontmatter, path, heading 위에 만든 Phase 6B deterministic projection입니다.
  Vault-derived index에서 다시 만들 수 있습니다.
- Episodic 또는 timeline memory는 indexed document snapshot change와 derived
  projection change 위에 만든 Phase 6C timeline projection입니다. Hidden
  transcript, raw session log store, durable business-event ledger가 아닙니다.
- Profile과 preference memory는 Vault Graph core 범위 밖입니다. 필요해지면 durable
  Vault note 또는 명시적으로 설정한 external adapter에 두어야 합니다.
- Procedural memory는 prompt와 workflow policy가 명시적으로 설계되기 전까지 범위
  밖입니다.

향후 Mem0, MemMachine, MCP memory-server 연동은 evidence-linked projection 위의
adapter 또는 export target이어야 합니다. 이런 adapter는 projection output을
소비할 수 있지만 Vault를 대체하거나, Vault Graph store를 mutate하거나, agent가
생성한 memory를 정상적인 Vault workflow 없이 fact로 되돌려 넣으면 안 됩니다.

## 8. Result Explanation Position

`explain_result(result_id)`는 Phase 6에서 durable result-history database에
의존하지 않습니다. 현재 search result ID는 rank를 포함하므로 한 응답 안에서는
유용하지만 durable product memory는 아닙니다.

따라서 Phase 6A는 explanation record와 bounded in-process MCP explanation
cache를 도입합니다.

- search, context-pack, related, decision-trace tool은 결과 반환 시 explanation
  record를 등록할 수 있습니다.
- `explain_result(result_id)`는 현재 MCP process의 record만 resolve합니다.
- server가 재시작되었거나 cache에서 evict되면 not-found error와 original query
  rerun 안내를 반환합니다.
- explanation record는 durable Vault knowledge가 되지 않습니다.

이는 기존 generated context-pack resource cache 정책과 같은 방향입니다.

## 9. Memory Projection Position

Phase 6B memory는 deterministic합니다. indexed document의 path, frontmatter,
heading, graph entity type, existing retrieval signal로 분류할 수 있지만,
존재하지 않는 project state를 만들어내면 안 됩니다.

초기 project memory projection은 다음 구조화된 group을 반환합니다.

- current state
- decision highlights with evidence
- open questions and follow-ups
- constraints
- next likely priorities
- warnings and stale areas
- evidence links

Timeline-based recent indexed document snapshot changes는 Phase 6C의 책임입니다.

group에 evidence가 없으면 group은 비어 있고, gap을 설명하는 warning이 있어야
합니다.

## 10. Timeline And Health Position

Phase 6C timeline output은 indexed document snapshot change와 derived projection
change를 결합합니다. 각 timeline item은 origin을 표시해야 합니다.

- `document_snapshot_change`
- `index_change`
- `projection_change`
- `warning`

Backend health와 scale-up readiness view는 기존 status field를 재사용하고
adapter readiness record를 추가합니다. local backend와 future scale-up backend가
동일한 logical contract를 만족할 수 있는지를 보고할 뿐, data migration은 하지
않습니다.

## 11. Error And Degradation Policy

- Invalid scope, unknown Vault IDs, malformed result IDs, unsupported time
  filters는 validation error입니다.
- Missing metadata state는 evidence를 resolve할 수 없으므로 memory projection에는
  fatal입니다.
- Missing vector state는 keyword나 metadata evidence가 충분하면 degradation입니다.
- Missing graph state는 project memory에서는 warning이고, graph-required view에서만
  fatal입니다.
- Missing explanation-cache entry는 not found와 safe rerun hint를 반환합니다.
- Stale projection은 freshness field와 warning이 함께 있을 때만 반환됩니다.

## 12. Multi-Vault Policy

- `scope=None`은 active Vault를 사용합니다.
- `scope.vault_ids`는 명시적인 Vault IDs를 선택합니다.
- all-Vault expansion은 application service 실행 전에 끝납니다.
- 같은 path, title, decision, issue name, entity label이 여러 Vault에 있으면
  memory projection은 Vault별로 그룹화합니다.
- Cross-Vault graph relationship은 opt-in이며 source, target, evidence Vault
  IDs를 보존합니다.

## 13. Handoff

Phase 6 implementation planning은 다음 순서로 진행합니다.

1. Phase 6A: explanation DTOs, explanation cache, service boundary, MCP
   `explain_result`, current search/context/graph tool output regression tests.
2. Phase 6B: metadata-backed document listing contract, memory DTOs, project
   memory service, decision memory service, issue memory service, MCP tools,
   `context/current` resource upgrade.
3. Phase 6C: timeline service, `timeline/recent` resource upgrade, recent
   changes MCP tool, health/freshness explorer service, scale-up readiness
   records, status serialization tests.

각 slice는 Vault Graph가 derived state만 쓰고 Vault content는 절대 편집하지 않는
규칙을 보존해야 합니다.
