# Vault Graph 구현 성공 기준 인수 검토 (Acceptance Review)

상태: 검증 완료(Verified)
날짜: 2026-06-24
검토자: Codex
브랜치: main
커밋: 58ca7bc + 현재 worktree의 acceptance 수정

> 이 문서는 영문 원본 `2026-06-23-implementation-success-criteria-acceptance-review.md`의 한글 번역본입니다. 코드 식별자, 명령어, 파일 경로, 검증 판정(PASS/PARTIAL 등)은 원본과 동일하게 유지합니다.

## 1. 요약 (Executive Summary)

| 판정 | 개수 |
| --- | ---: |
| PASS | 8 |
| PARTIAL | 0 |
| GAP | 0 |
| NOT IN CURRENT SCOPE | 0 |
| UNKNOWN | 0 |

- 구현된 표면(surface)은 이제 `docs/SPEC.md`의 8개 성공 기준 모두를 현재 체크아웃 코드, 집중 acceptance 테스트, 그리고 통과된 전체 게이트(`ruff`, `mypy`, `pytest`: 778 통과, 1 건너뜀; 건너뛴 항목은 게이트로 막힌 MCP stdio smoke 테스트이며, 활성화하면 통과함)로 충족한다.
- 읽기 전용(read-only) 안전성은 강력하고 충분히 입증되어 있다. index, search, context-pack, graph-retrieval, MCP tool/resource 경로 모두 인덱싱 전후 파일 해시 또는 디렉터리 트리 스냅샷 테스트를 갖고 있어 Vault 바이트가 절대 변경되지 않음을 증명하며, 7개 MCP 프롬프트 모두 에이전트가 영속적(durable) 변경을 Vault 워크플로로 되돌리도록 지시한다.
- 이전 `PARTIAL` 항목은 `tests/test_acceptance_success_criteria.py`로 닫혔다: MCP 동일 상대 경로 리소스 격리, Vault Graph 인덱스 상태 삭제→재빌드, 결정론적 오프라인 키워드 전용 저하.
- 사용자 대면 `vg reset-index` 명령은 추가하지 않았다. 승인된 리셋 UX는 Vault Graph 내부 인덱스 상태를 문서화된 방식으로 삭제한 뒤 `vg index` / `vg index --vault-id`를 실행하는 것이다.
- `GAP`(미충족 기준)은 발견되지 않았다. Phase 6 메모리/탐색기 프로젝션은 읽기 전용·증거-연결 작업 컨텍스트로 유지되며 영속 메모리 데이터베이스로 작동하지 않는다.

## 2. 검토 범위 (Review Scope)

포함 단계(현재 구현된 제품 표면):

- Phase 1: Vault 카탈로그, 리더, 메타데이터 스토어
- Phase 2: 로컬 벡터 인덱싱 및 키워드/벡터 검색
- Phase 3: 엔티티/관계 그래프, `vg related`, 그래프 검색, 의사결정 추적(decision trace)
- Phase 4: context pack 계약 및 CLI context pack 조립
- Phase 5: MCP 서버, 리소스, 도구, 프롬프트
- Phase 6: 결과 설명, 프로젝트/의사결정/이슈 메모리, 타임라인/헬스 탐색기 서비스

명시적으로 제외된 향후 작업(현재 인수를 막지 않음):

- Phase 7B/7C UI 구현 (승인된 결정에 따라 연기됨).
- Phase 7A 로컬 HTTP 서빙 (`vg serve --http`).
- `Ask Project`, `ask_vault`, 답변 합성(answer synthesis), LLM 어댑터 정책, 인용(citation) 보장.
- MacBook 가속, 비-Markdown 리더, 청킹 마이그레이션, 외부 메모리 어댑터 (TODO 가이드이며 인수 범위가 아님).

## 3. 검증 명령 (Verification Commands)

모든 명령은 현재 체크아웃(`main` @ `58ca7bc`)에 대해 실행되었다.

| 명령 | 결과 |
| --- | --- |
| `git status --short --branch` | `main...origin/main [ahead 1]`; acceptance 수정 및 검토/계획 문서 존재 |
| `git rev-parse --short HEAD` | `58ca7bc` |
| `uv run --python 3.12 ruff check src tests` | `All checks passed!` |
| `uv run --python 3.12 mypy src tests` | `Success: no issues found in 204 source files` |
| `uv run --python 3.12 pytest` | `778 passed, 1 skipped in 6.22s` |
| `VG_RUN_MCP_STDIO_SMOKE=1 uv run --python 3.12 pytest tests/test_mcp_stdio_smoke.py -q` | `1 passed` (게이트로 막힌 전송 smoke; env 플래그가 없으면 기본 건너뜀) |

기준별 집중 명령 그룹(모두 현재 체크아웃에서 수집됨):

| 기준 | 명령 (축약) | 결과 |
| ---: | --- | --- |
| 1 | `pytest test_cli_catalog_metadata test_metadata_indexer test_read_only_boundary test_vector_indexing_read_only_boundary test_graph_indexing_read_only_boundary` | 31 통과 |
| 2 | `pytest test_vault_catalog test_cli_catalog_metadata test_query_scope_resolution test_multi_vault_search test_cli_context` | 44 통과 |
| 3 | `pytest test_multi_vault_identity test_multi_vault_search test_multi_vault_graph_identity test_multi_vault_graph_indexing test_multi_vault_graph_retrieval test_cli_context::...preserves_evidence_vault_ids test_acceptance_success_criteria::...mcp_document_resources...` | 전체 suite로 커버; acceptance 파일 3 통과 |
| 4 | `pytest test_context_pack_builder test_context_pack_evidence_budget test_context_pack_warnings test_cli_context test_mcp_tools::build_context_pack... test_context_pack_read_only_boundary` | 87 통과 |
| 5 | `pytest test_graph_retrieval_service test_cli_decision_trace test_mcp_tools::decision_trace...` | 19 통과 |
| 6 | `pytest test_cli_catalog_metadata::test_cli_index_accepts_full_option test_index_service_vector_reconcile test_index_service_graph_reconcile test_acceptance_success_criteria::...deleted_vault_graph_index_state...` | 전체 suite로 커버; acceptance 파일 3 통과 |
| 7 | `pytest test_fastembed_text_embeddings test_app_search_readiness_service test_retrieval_service_search test_search_read_only_boundary test_acceptance_success_criteria::...offline_search_threshold...` | 전체 suite로 커버; acceptance 파일 3 통과 |
| 8 | `pytest test_search_read_only_boundary test_graph_retrieval_read_only_boundary test_context_pack_read_only_boundary test_mcp_tool_read_only_boundary test_mcp_resource_read_only_boundary test_mcp_prompts` | 27 통과 |
| Phase 6 | `pytest test_result_explanation test_mcp_explain_result test_project_memory_service test_decision_memory_service test_issue_memory_service test_timeline_memory_service test_health_explorer_service test_mcp_memory_tools test_mcp_recent_changes_tool test_mcp_current_context_resource test_mcp_timeline_resource` | 88 통과 |

환경 또는 제품 사유로 실패한 명령은 없다. 유일한 기본 건너뜀(MCP stdio smoke)은 명시적으로 실행되어 통과했으므로 어떤 판정도 바꾸지 않는다.

## 4. 성공 기준 매트릭스 (Success Criteria Matrix)

| # | 성공 기준 | 판정 | 증거 | 격차 / 위험 | 권장 다음 조치 |
| ---: | --- | --- | --- | --- | --- |
| 1 | 사용자가 Vault를 지정해 Vault를 변형하지 않고 인덱스를 빌드할 수 있다. | PASS | `vg init`/`vg index` (`cli/main.py:262`, `:298`); `path_guard.assert_write_target_allowed` (`app/path_guard.py:19`); `test_read_only_boundary.py::test_index_commands_do_not_modify_vault_files`가 인덱싱 전후 Vault 파일을 해시하여 불변임을 단언; init은 Vault 내부의 state 경로/심볼릭 링크를 거부. | 제품 영향 없음. | 현재 읽기 전용 경계 테스트를 CI 게이트에 유지. |
| 2 | 사용자가 여러 Vault를 등록하고 하나 또는 전체 Vault를 명시적으로 인덱싱할 수 있다. | PASS | `vg vault add`/`list` (`cli/main.py:274`,`:290`), `--vault-id`/`--all-vaults` (`:301`,`:302`); 상호 배타 가드 (`:306`) + `test_cli_index_rejects_conflicting_vault_scope_options`; `scope_for_all_enabled`가 활성 ID로 확장 (`vault_catalog.py:155`); 각 Vault별 실제 스코프 (`query_scope_resolution.py`); 출력에 `vault_ids` 표시 (`:321`). | 제품 영향 없음. | 없음. |
| 3 | 동일한 상대 경로를 가진 두 Vault가 메타데이터, 벡터, 그래프, MCP, context-pack 출력에서 충돌하지 않는다. | PASS | 식별자는 `(vault_id, path)` (`sqlite_metadata_store.py` PK); 메타데이터, 그래프, context-pack, 벡터 충돌 테스트에 더해 `test_acceptance_success_criteria.py::test_mcp_document_resources_keep_same_relative_paths_separate_by_vault_id`가 MCP 리소스 URI를 직접 검증. | 제품 영향 없음. | MCP 충돌 테스트를 acceptance gate에 유지. |
| 4 | 에이전트가 전체 Vault를 읽는 대신 구체적 작업에 대한 context pack을 요청할 수 있다. | PASS | `vg context` (`cli/main.py:367`)와 `build_context_pack` MCP 도구 (`mcp_tools.py:240`) 모두 `ContextPackBuilder.build` 호출; 검색 한도(`context_pack_builder.py:290`), 토큰 예산(`:221`), 증거-항목 예산(`:183`), 발췌 절단(`:404`), 누락 경고(`:451`)로 경계 설정; `test_budget_packing_drops_items_when_evidence_budget_exceeded`가 예산 초과 증거를 `budget_omitted` 경고와 함께 누락함을 증명; 읽기 전용 경계 테스트가 Vault 덤프 없음을 확인. | 제품 영향 없음. | 없음. |
| 5 | 의사결정 추적이 증거를 포함하고 진술된 사실과 추론된 링크를 구분한다. | PASS | `vg decision-trace` (`cli/main.py:536`)와 `get_decision_trace` MCP 도구 (`mcp_tools.py:328`); `DecisionTraceStep.evidence` + `relationship_status` (`graph_retrieval.py:113-114`); 상태 값 `stated`/`inferred`/`contested`/`not_applicable` (`graph_retrieval_service.py:738`,`:776`); 토픽 폴백 시 `topic_not_durable_decision` 경고 (`:255`); 증거 누락 시 `graph_evidence_missing` 경고 (`:720`). 서비스, CLI(JSON에 `relationship_path[].status`), MCP 페이로드에서 모두 증명. | 제품 영향 없음. | 없음. |
| 6 | 모든 인덱스를 삭제하고 Vault로부터 재빌드할 수 있다. | PASS | Vault Graph 내부 인덱스 상태는 Vault 루트 밖 `state_path/{metadata,vector,graph}`에 존재 (`catalog_service.py`); `vg index --full`이 Vault로부터 재빌드; `test_acceptance_success_criteria.py::test_deleted_vault_graph_index_state_rebuilds_from_vault_without_mutating_vault`가 metadata/vector/graph 상태 삭제, `vg index --vault-id`, 메타데이터/키워드/벡터/그래프 신선도, Vault 해시 불변을 검증. | 제품 영향 없음. | 문서화된 state 삭제 + `vg index` 유지; 실제 UX 격차가 생길 때만 `vg reset-index` 검토. |
| 7 | 인터넷 접속 없이 로컬-우선(local-first) 동작이 가능하다. | PASS | 검색 시 임베딩이 `local_files_only=True` 강제; `can_embed_without_download()`가 다운로드 없이 로컬 아티팩트 확인; `test_acceptance_success_criteria.py::test_offline_search_threshold_degrades_without_embedding_or_cache_mutation`이 `HF_HUB_OFFLINE`, 모델 미가용, 키워드 전용 결과, 가시적 경고, embed/cache 변형 없음까지 검증. | 제품 영향 없음. | 결정론적 오프라인 smoke를 CI에 유지; 실제 캐시 모델 + OS 네트워크 차단은 수동 릴리스 점검으로 보류. |
| 8 | 검색 출력이 Vault의 영속 게시(publication) 워크플로를 우회하지 않는다. | PASS | search, graph retrieval, context pack, MCP 도구, MCP 리소스에 대한 읽기 전용 경계 테스트 모두 Vault 바이트를 전후 스냅샷하여 불변 단언; 7개 MCP 프롬프트 모두 영속 변경을 Vault 캡처/검증/릴리스/Git로 라우팅하고 "Do not publish through Vault Graph"라는 공유 지시 포함 (`mcp_prompts.py:37`, `test_mcp_prompts.py`); 검색 스토어는 읽기 전용으로 오픈 (`cli/main.py:146`). | 제품 영향 없음. | 없음. |

## 5. 상세 결과 (Detailed Findings)

### 5.1 기준 1 — Vault 변형 없이 인덱싱

- **판정:** PASS
- **증거:** `vg init` (`cli/main.py:262`)와 `vg index` (`:298`)가 존재한다. `app/path_guard.py:19` (`assert_write_target_allowed`)는 모든 쓰기를 구성된 state 경로로 한정하고 Vault 루트 내부 대상을 거부한다. `test_read_only_boundary.py::test_index_commands_do_not_modify_vault_files`는 `index --dry-run`과 `index` 전후 모든 Vault 파일을 해시하여 바이트 불변을 단언한다. init은 Vault 내부 state 경로와 Vault로의 심볼릭 링크 리다이렉트를 거부한다. `test_vector_indexing_read_only_boundary.py`와 `test_graph_indexing_read_only_boundary.py`는 전체 트리 스냅샷을 취해 인덱싱이 Vault Graph state만 기록함을 증명한다. 실제 임시 Vault 픽스처는 `test_cli_catalog_metadata.py`에서 CLI를 통해 인덱싱된다.
- **위험:** 제품 영향 없음.
- **권장 다음 조치:** 읽기 전용 경계 스위트를 필수 CI 게이트에 유지.

### 5.2 기준 2 — 멀티 Vault 등록 및 명시적 인덱싱

- **판정:** PASS
- **증거:** `vg vault add`/`vg vault list` (`cli/main.py:274`,`:290`); `vg index --vault-id`와 `--all-vaults` (`:301`,`:302`). CLI는 두 플래그 동시 사용을 거부한다 (`:306`), `test_cli_index_rejects_conflicting_vault_scope_options`로 커버됨. `--all-vaults`는 서비스 실행 전에 `VaultCatalog.scope_for_all_enabled()` (`vault_catalog.py:155`)를 통해 명시적 활성 `vault_id`로 확장되고, 다시 Vault별 실제 스코프 (`query_scope_resolution.py`)로 확장된다 — `test_all_vaults_expands_only_enabled_entries`와 `test_actual_scopes_keep_each_vault_narrow`로 검증. `vault_ids`는 index/search 출력에 표시된다. `test_all_vault_graph_apply_creates_revisions_per_normalized_vault_scope`는 리비전이 Vault 스코프별로 키잉됨을 보여주어, `--vault-id` 실행이 무관한 Vault를 stale로 표시하지 않음을 입증한다.
- **위험:** 제품 영향 없음.
- **권장 다음 조치:** 없음.

### 5.3 기준 3 — 동일 상대 경로 무충돌

- **판정:** PASS
- **증거:** 파일 식별자는 `(vault_id, path)`로, `sqlite_metadata_store.py`의 복합 기본 키와 고유 `document_id`를 갖는다. 동일 상대 경로/동일 이름 충돌에 대한 직접 테스트가 **메타데이터**(`test_multi_vault_identity.py::test_two_vaults_with_same_relative_path_do_not_collide`), **그래프**(`test_multi_vault_graph_identity.py::test_same_entity_name_in_two_vaults_does_not_collide` 및 매니페스트 분리 테스트), **context-pack**(`test_context_pack_builder.py::test_same_chunk_id_from_two_vaults_remains_distinct`, 그리고 `test_cli_context_all_vaults_uses_real_retrieval_and_preserves_evidence_vault_ids`)에 존재한다. **벡터**는 `test_multi_vault_search.py::test_all_vault_search_keeps_identical_paths_separate`(`wiki/same.md`를 가진 두 Vault, `vault_id`로 키잉·`result_id` 네임스페이스화된 결과)로 커버된다.
- **Acceptance 종료:** `test_acceptance_success_criteria.py::test_mcp_document_resources_keep_same_relative_paths_separate_by_vault_id`가 직접 MCP 리소스 시나리오를 추가한다. 두 Vault가 각각 `wiki/same.md`를 제공하고, `vault://main/documents/wiki%2Fsame.md`와 `vault://work/documents/wiki%2Fsame.md`가 각자의 `vault_id` 아래 서로 다른 내용과 다른 `document_id`로 해소된다.
- **위험:** 제품 영향 없음.
- **권장 다음 조치:** 이 acceptance 테스트를 멀티 Vault 게이트에 유지.

### 5.4 기준 4 — 전체 Vault 대신 에이전트 context pack

- **판정:** PASS
- **증거:** `vg context "goal"` (`cli/main.py:367`)와 `build_context_pack` MCP 도구 (`mcp_tools.py:240`)는 모두 `ContextPackRequest`를 구성하고 검색 결과에 대해 `ContextPackBuilder.build`를 호출한다 — 어느 쪽도 Vault 파일을 열거하지 않는다. `ContextPack` DTO (`context_pack.py:272`)는 goal, scope(요청 + 실제), vaults, vault_revisions, store_revisions, budget, evidence, warnings를 담는다. 경계는 강제되고 테스트된다: 검색 한도 상한 (`context_pack_builder.py:290`), 토큰 예산 검사 (`:221`), 증거-항목 예산 (`:183`), `excerpt_truncated` 경고를 동반한 발췌 절단 (`:404`), `budget_omitted` 경고 (`:451`). `test_budget_packing_drops_items_when_evidence_budget_exceeded`는 예산 초과 증거가 (덤프되지 않고) 가시적 경고와 함께 누락됨을 증명하고, `test_omitted_multi_evidence_item_does_not_leave_orphan_evidence`는 고아 증거가 없음을 증명한다. `test_context_pack_read_only_boundary.py`는 팩 빌드가 Vault를 변형하지 않음을 증명한다.
- **위험:** 제품 영향 없음.
- **권장 다음 조치:** 없음.

### 5.5 기준 5 — 의사결정 추적 증거 및 진술/추론 구분

- **판정:** PASS
- **증거:** `vg decision-trace TOPIC` (`cli/main.py:536`)와 `get_decision_trace` MCP 도구 (`mcp_tools.py:328`). `DecisionTraceStep`은 `evidence: tuple[EvidenceReference, ...]`와 `relationship_status`를 담는다 (`graph_retrieval.py:113-114`). 서비스는 초기 의사결정 단계를 `not_applicable`로 설정하고, 경로 단계 상태를 엣지 전반의 최소값으로 도출하여 (`graph_retrieval_service.py:738`,`:776`) `stated`를 `inferred`/`contested`와 구분한다. 대상이 영속 의사결정 엔티티가 아닐 때 토픽 폴백은 `topic_not_durable_decision` 경고를 발생시키고 (`:255`), 엔티티 증거가 누락되면 `graph_evidence_missing`을 발생시킨다 (`:720`). 이 구분은 서비스 결과, CLI JSON(`relationship_path[].status` 및 단계별 `evidence`), MCP 페이로드(`test_decision_trace_opens_graph_service_after_validation`)에서 가시적이다.
- **위험:** 제품 영향 없음.
- **권장 다음 조치:** 없음.

### 5.6 기준 6 — 모든 인덱스 삭제 및 Vault로부터 재빌드

- **판정:** PASS
- **증거:** 재빌드 가능한 상태는 Vault 루트 밖 `state_path/{metadata,vector,graph}`에 존재한다 (`catalog_service.py`). `vg index --full`은 Vault로부터 전체 재빌드를 강제한다. 스코프-로컬 재조정은 `MetadataStore` 청크로부터 벡터와 그래프 프로젝션을 재빌드한다.
- **Acceptance 종료:** `test_acceptance_success_criteria.py::test_deleted_vault_graph_index_state_rebuilds_from_vault_without_mutating_vault`가 구성된 Vault Graph metadata/vector/graph 인덱스 상태를 삭제하고, `vg index --vault-id default`를 실행한 뒤 메타데이터/키워드/벡터/그래프 신선도와 Vault 파일 해시 불변을 검증한다. 이 과정에서 같은 프로세스 삭제→재빌드가 stale Chroma handle을 보존하지 않도록 `ChromaVectorStore.close()`와 `IndexService.close()`가 추가되었다.
- **위험:** 제품 영향 없음. 승인된 UX는 파괴적 명령을 추가하지 않는다.
- **권장 다음 조치:** 공개 전에는 문서화된 state 디렉터리 삭제 + `vg index`로 충분하다. 실제 사용자 대면 격차가 나타날 때만 `vg reset-index`를 추가한다.

### 5.7 기준 7 — 로컬-우선 오프라인 동작

- **판정:** PASS
- **증거:** 검색 시 질의 임베딩은 CLI와 MCP 서비스 팩토리 모두에서 `local_files_only=True`로 구성된다. `can_embed_without_download()`는 다운로드를 유발하지 않고 로컬 아티팩트 가용성을 확인하며, `ReadOnlySearchReadiness.check()`가 이를 노출한다. 모델 아티팩트 또는 벡터 프로젝션이 미가용일 때 검색은 가시적 경고와 함께 키워드 전용으로 저하되고 Vault 또는 state를 변형하지 않는다.
- **Acceptance 종료:** `test_acceptance_success_criteria.py::test_offline_search_threshold_degrades_without_embedding_or_cache_mutation`은 `HF_HUB_OFFLINE`을 설정하고, `can_embed_without_download()`가 `False`를 반환하는 오프라인 `TextEmbeddings` fake를 사용한다. 테스트는 키워드 전용 결과, `embedding_model_unavailable` 및 `degraded_keyword_only` 경고, `embed()` 미호출, 캐시 경로 미생성을 검증한다.
- **위험:** 제품 영향 없음. 결정론적 smoke는 CI 친화적이며 실제 캐시 모델 네트워크 차단은 수동 릴리스 점검으로 남긴다.
- **권장 다음 조치:** 결정론적 오프라인 smoke를 CI에 유지.

### 5.8 기준 8 — 검색 출력이 Vault 게시를 우회하지 않음

- **판정:** PASS
- **증거:** search(`test_search_read_only_boundary.py`), graph retrieval(`test_graph_retrieval_read_only_boundary.py`), context pack(`test_context_pack_read_only_boundary.py`), MCP 도구(`test_mcp_tool_read_only_boundary.py`), MCP 리소스(`test_mcp_resource_read_only_boundary.py`)에 대한 읽기 전용 경계 테스트가 있으며, 각각 Vault 바이트를 전후 스냅샷하여 변화 없음을 단언한다. 7개 MCP 프롬프트 모두 Vault 소스 캡처/검증/릴리스-게이트/Git을 제안하고 "Do not publish through Vault Graph"라는 공유 지시를 포함하며 (`mcp_prompts.py:37`), `test_mcp_prompts.py`로 검증된다. 검색 스토어는 읽기 전용으로 열린다 (`cli/main.py:146`, `initialize=False, read_only=True`). 어떤 검색 명령도 Vault 파일을 쓰거나 위키 페이지를 게시하지 않는다.
- **위험:** 제품 영향 없음.
- **권장 다음 조치:** 없음.

### 5.9 Phase 6 프로젝션 커버리지 (보조 증거)

모든 Phase 6 서비스가 구현되어 있고 테스트를 통과하며(Phase 6 그룹에서 88 통과), 읽기 전용·증거-연결 프로젝션으로 남아 있다 — 영속 메모리 데이터베이스나 답변 합성이 아니다.

| 프로젝션 | 서비스 / 테스트 | vault_id + 증거 + 경고 포함 | 읽기 전용 |
| --- | --- | --- | --- |
| 결과 설명 | `test_result_explanation.py`, `test_mcp_explain_result.py` | 예 (식별자 + 증거 + 시그널) | 캐시 뷰, 쓰기 없음 |
| 프로젝트 메모리 | `test_project_memory_service.py` | 예 | 메타데이터 기반 프로젝션 |
| 의사결정 메모리 | `test_decision_memory_service.py` | 예 (claim_status + 증거) | 프로젝션 + 선택적 그래프 추적 |
| 이슈 / 미해결 질문 메모리 | `test_issue_memory_service.py` | 예 (상태 + 증거) | 프로젝션 |
| 타임라인 메모리 | `test_timeline_memory_service.py`, `test_mcp_timeline_resource.py` | 예 (리비전 + generated_at) | 프로젝션 |
| 헬스 탐색기 | `test_health_explorer_service.py` | 예 (백엔드 상태, 스코프 vault_ids) | 읽기 전용 점검 |
| MCP 메모리 도구 / 최근 변경 / 현재 컨텍스트 | `test_mcp_memory_tools.py`, `test_mcp_recent_changes_tool.py`, `test_mcp_current_context_resource.py` | 예 (JSON 페이로드에 보존) | 직렬화 / 리소스 읽기 |

이 프로젝션들은 기준 4, 5, 8(경계 있는 컨텍스트, 증거-연결 의사결정, 읽기 전용 작업 컨텍스트)을 뒷받침하며 어떤 일반 쓰기 가능 메모리 API도 도입하지 않는다.

## 6. 다각도 검토 (Multi-Angle Review)

### 6.1 보안 / 읽기 전용 안전성

- 본 검토의 어떤 권고도 Vault Graph를 통한 Vault 쓰기를 함의하지 않는다. 기준 6의 리셋/삭제 acceptance 테스트는 Vault Graph 내부 인덱스 상태로 명시적으로 한정되며, Vault 해시가 불변임을 단언한다. 경로 예시는 등록된 Vault 루트나 `raw/`/`wiki/`/`docs/`/`scratch/`를 결코 삭제하지 않는다. MCP는 로컬 stdio·읽기 전용으로 유지되고 HTTP 표면은 도입되지 않는다. Chroma read-only 검색은 이제 변형 가능한 Chroma client를 열지 않고 SQLite read-only 접근을 사용한다.

### 6.2 성능 / 확장성

- 어떤 기준도 전체 Vault 덤프로 인수되지 않는다. 기준 4는 명시적으로 경계 있는 컨텍스트(예산, 절단, 누락 경고)를 증명한다. 멀티 Vault 검사는 `QueryScope`와 명시적 `vault_id`를 보존하며, `--all-vaults`는 스토어 실행 전 Vault별 실제 스코프로 확장된다. 기준 6과 7의 acceptance 시나리오는 전체 카탈로그 규모 실행이 아니라 경계 한정 픽스처와 스코프-로컬 재빌드/저하를 사용한다.

### 6.3 테스트 용이성 / CI

- 모든 기준은 향후 에이전트가 재실행할 수 있는 재현 가능하고 구체적인 명령(섹션 3)을 최소 하나 갖는다. 이전 격차는 `tests/test_acceptance_success_criteria.py`의 세 테스트(MCP 충돌 리소스, 삭제→재빌드, 결정론적 오프라인 smoke)로 닫혔다.

### 6.4 유지보수성 / 깊은 모듈

- 변경은 깊은 모듈 경계를 유지한다. CLI와 MCP는 계속 애플리케이션 서비스(`RetrievalService`, `GraphRetrievalService`, `IndexService`)를 호출하고 스토어 내부를 직접 다루지 않는다. Chroma-specific 정리는 `ChromaVectorStore`와 `IndexService.close()` 내부에 머문다. 새로운 영속 지식 소스, 숨겨진 메모리 계층, 파괴적 CLI 명령은 도입되지 않았다.

### 6.5 제품 / 에이전트 사용성

- 사람은 요약과 매트릭스를 한 페이지 미만으로 읽고 무엇이 동작하는지 알 수 있다. 에이전트는 기준별 구체적 file/test 증거와 재실행 가능한 명령을 갖는다. 이전 미결정은 해결되어 `docs/DECISIONS.md`에 기록되었다. 향후 TODO 항목(가속, 비-Markdown 리더, 청킹 마이그레이션, 외부 메모리, `vg ask`, HTTP 서빙)은 인수 차단 항목에서 배제된다.

### 6.6 문서 일관성

- `SPEC.md`, `FEATURES.md`, `DESIGN.md`는 구현 증명이 아니라 소스 컨텍스트로 취급되었다. 모든 PASS는 디자인 문서만이 아니라 코드와 테스트로 뒷받침된다. `SPEC.md` §17은 이제 구현된 CLI 명령과 CLI TODO 명령을 분리하고, 기존 "Initial CLI" 표현을 대체한다. `docs/DECISIONS.md`는 리셋, 오프라인, CLI 문서화 결정을 기록하고, `docs/PATCH_LOG.md`는 acceptance-review 수정사항을 기록한다.

### 6.7 Phase 6 프로젝션 커버리지

- 결과 설명, 프로젝트/의사결정/이슈/타임라인 메모리, 헬스 탐색기, MCP 메모리 리소스/도구가 모두 보조 증거(섹션 5.9)로 포함되며 읽기 전용 작업 컨텍스트이지 영속 메모리 데이터베이스가 아니다. 본 검토는 어떤 Phase 6 출력도 답변 합성이나 Vault 게시의 대체로 취급하지 않는다.

## 7. 해결된 결정 사항 (Resolved Decisions)

### 해결 1: 인덱스 리셋 UX (기준 6)

승인: Vault Graph 내부 인덱스 상태 삭제 후 `vg index` / `vg index --vault-id`를 실행하는 방식을 문서화하고 테스트한다. 공개 전에는 `vg reset-index`를 추가하지 않으며, 실제 사용자 대면 격차가 나타날 때만 검토한다. `docs/DECISIONS.md`에 기록됨.

### 해결 2: 오프라인 인수 임계값 (기준 7)

승인: 네트워크/다운로드 경로를 비활성화하거나 페이크한 결정론적 오프라인 smoke 테스트를 요구한다. 실제 캐시된 모델 + OS 수준 네트워크 차단은 선택적 수동 릴리스 점검으로 둔다. `docs/DECISIONS.md`에 기록됨.

### 해결 3: CLI 문서 명료성 (§17)

승인: "Initial CLI"를 구현된 CLI 명령과 CLI TODO 블록으로 대체한다. `vg watch`, `vg ask`, `vg serve --http`는 현재 제품 기능이 아니다. `docs/DECISIONS.md`에 기록됨.

## 8. 완료된 Acceptance 조치

### 닫힌 차단 항목

1. **MCP 동일 상대 경로 충돌 테스트 (기준 3):** 추가 및 통과.
2. **삭제→재빌드 acceptance 테스트 (기준 6):** 추가 및 통과.
3. **결정론적 오프라인 smoke 테스트 (기준 7):** 추가 및 통과.
4. **CLI 문서 명료성:** `SPEC.md` §17이 구현 명령과 CLI TODO 명령을 구분한다.

### 남은 향후 작업, acceptance 차단 아님

5. MacBook 가속, 비-Markdown 리더, 청킹 마이그레이션, 외부 메모리 어댑터, `ask_vault`/답변 합성, Phase 7 UI/HTTP는 향후 범위로 유지한다.
6. 안내형 `vg reset-index` 명령은 수동 state 디렉터리 삭제가 실제 사용자에게 혼란을 만들 때 선택적으로 검토한다.
