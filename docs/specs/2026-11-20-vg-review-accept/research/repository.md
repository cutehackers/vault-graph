# 조사: 저장소와 Vault 도구의 현재 동작

2026-11-20에 이 worktree와 vault-builder 체크아웃(`$HOME/workspace/vault-builder`, 읽기만)을 읽어 확인했다. 명령은 실행하지 않았다.

### X1. Vault의 수락은 pending 항목만 받고, 발행한 뒤 resolution에 "Published:"를 적는다
- source: vault-builder `tools/wiki/lib/memory_proposal.py`의 `accept`

status가 `pending`이 아니면 "Review item is already <status>."로 거부한다. 대상 페이지의 sha256이 항목의 `target_hash`와 다르면 reason `target-changed`로 거부하고 항목은 pending으로 남는다. 통과하면 `publish_draft`로 발행하고 resolution을 `<이유> Published: <경로들>.`로 적는다. 발행은 됐는데 항목 갱신이 실패하면 reason `io-error`로 돌려준다.

### X2. `review resolve`의 인자와 두 갈래
- source: vault-builder `tools/wiki/cli.py` 169-173행, `_resolve_review`, `_resolve_review_with_gate`

인자는 `path`, `--status`(필수), `--resolution`(필수), `--json`이다. `accepted`이고 memory-proposal이면 수락 갈래로 가고 `--json` 결과는 `vault-review-result/v1` 객체(`status` resolved 또는 rejected, `review_status`, `reason`, `written_paths`, `messages`)다. 그 밖(거절 포함)은 lint 갈래다. 실행 전 lint가 깨져 있으면 lint 보고서를 Vault에 쓰고 중단한다. 처리 뒤 lint가 깨지면 되돌린다. 이 갈래의 `--json` 실패 reason은 `review-invalid`다.

### X3. 정상 처리는 항목 파일과 `wiki/log.md`를 함께 바꾼다
- source: vault-builder `tools/wiki/lib/review.py`의 `resolve_review_item`

frontmatter의 `status`, `updated`, `resolution`을 바꾸고 본문 "## Resolution" 구획을 고쳐 쓰며 `wiki/log.md`에 "Review <status>: <summary>" 항목을 더한다. 파일의 `status`만 손으로 고치면 이 가운데 어느 것도 일어나지 않고 발행도 없다.

### X4. 검토 항목과 초안 사본의 모양
- source: vault-builder `tools/wiki/lib/review.py`의 `create_review_item`, `memory_proposal.py`의 `propose`

항목은 `scratch/review/<review_id>.md`다. frontmatter에 `review_id`, `type`, `status`, `created`, `updated`, `summary`, `related_pages`, `evidence`, `resolution`이 있고 memory-proposal에는 `draft`, `target_path`, `target_hash`가 더 있다. 초안 사본은 `scratch/review/<review_id>.draft.json`이다. 검토 종류는 다섯 가지이고 memory-proposal은 그중 하나다.

### X5. vault-graph가 만드는 초안은 세 가지 모양이다
- source: `src/vault_graph/operation/memory/memory_drafts.py`, vault-builder `tools/wiki/lib/draft_patch.py`

추가와 수정은 `upsert-page`(`frontmatter`, `body` 전체)이고 본문 끝에 "## Evidence", "Status: <basis>", "- Evidence: <줄>"이 온다. 폐기와 복원은 frontmatter만 있는 `patch-page`다. 주장 교체는 `patch-page`의 `supersede-claim` edit(`claim`, `by`, `status`, `evidence`)이다. `patch-page`를 결과 페이지로 바꾸는 일은 Vault의 `materialize_patch`가 하고, 결과 페이지를 출력하는 Vault 명령은 없다(`apply-draft --dry-run`은 검증만 한다).

### X6. vault-graph는 지금 status 글자만 읽어 수락을 센다
- source: `src/vault_graph/interface/composition/adapters/vault_review_queue.py`, `src/vault_graph/interface/cli/dream_commands.py`의 `_echo_runs`

`review_item_status`는 frontmatter `status`만 돌려준다. `_echo_runs`는 그 값이 `accepted`인 수로 `accepted`와 `acceptance_rate`를 낸다. 대기 한도 안내 문구는 Vault의 `review resolve`를 가리킨다. `pending_proposals`는 type과 status가 맞는 항목 수만 센다.

### X7. Vault 명령 실행 어댑터에는 publish와 propose만 있다
- source: `src/vault_graph/interface/composition/adapters/vault_publish_cli.py`, `src/vault_graph/operation/memory/memory_write_service.py` 87행

`VaultPublishCli`는 vault-graph의 Python을 `-I -B`로, Vault 폴더를 작업 폴더로, 시간 한도를 두고 `tools/wiki/cli.py`를 실행한다. 표준 출력의 계약 JSON만 읽는다. 종료 코드 2는 Vault 도구가 그 명령을 모른다는 뜻으로 다룬다. 한도 기본값은 `PUBLISH_TIMEOUT_SECONDS` 120초다. `review resolve`를 실행하는 코드는 없다.

### X8. 발행 뒤 색인을 시작하는 기존 방법 두 가지
- source: `src/vault_graph/interface/mcp/mcp_service_factory.py`의 `start_background_index`, `src/vault_graph/interface/cli/hook_commands.py`의 `start_catch_up_index`

MCP 서버는 서버 프로세스 안의 daemon 스레드로 색인한다. 곧 끝나는 CLI에서는 쓸 수 없다. `start_catch_up_index`는 분리된 프로세스를 띄워 Vault마다 `vg index --vault-id`를 실행하고 Graph Home `logs/session-start-index.lock`을 쥔다. 잠금이 잡혀 있으면 None을 돌려주고 띄우지 않는다.

### X9. 자식 세션 표시 환경 변수
- source: `src/vault_graph/interface/cli/hook_commands.py` 109행과 `_facts_child`, `claude_dream_judge.py`, `claude_fact_extractor.py`

드리밍 판단과 사실 추출이 띄우는 Claude 세션의 환경에는 `VAULT_GRAPH_FACTS_CHILD=1`이 들어간다. 지금은 훅 두 개만 이 값을 본다.

### X10. 쓰기 길의 수를 적은 문서와 수락 방법을 안내하는 곳
- source: `AGENTS.md` 9행, `docs/SPEC.md` 61행과 §4, `docs/ARCHITECTURE.md` §4, `README.md` 89-95행, `docs/FEATURES.md` 169·199행, `src/vault_graph/interface/mcp/mcp_server.py` 92-93행

`AGENTS.md`, SPEC 원칙4, ARCHITECTURE §4는 "다섯"이라고 적는다. SPEC §4의 목록은 "네 경로"라고 적고 사실 첨부가 빠져 있어 이미 원칙4와 어긋난다. README, FEATURES, MCP 서버 안내, MCP 쓰기 도구의 `proposed` 메시지(SPEC §5)는 Vault 폴더에서 치는 `review resolve` 명령을 안내한다.

### X11. cwd에서 연결 Vault를 찾는 기존 코드와 드리밍 기록
- source: `src/vault_graph/interface/composition/query_scope_resolution.py`의 `resolve_project_vaults`·`registered_vault_ids`, `src/vault_graph/interface/composition/adapters/dream_worker.py` 658-672행

`vault-map.json`의 프로젝트에 연결된 Vault를 Graph Home에 등록된 것과 아닌 것으로 나눠 준다. 드리밍은 보낸 제안마다 `logs/dream-runs.jsonl`에 `vault`, `vault_root`, `target`, `review_path`를 적는다.

### X12. 실제 Vault 도구로 수락과 거절을 도는 e2e가 이미 있다
- source: `tests/e2e/test_long_term_memory_scenarios.py`의 `test_a3_inferred_memory_waits_for_review_then_is_published_on_accept`

이 테스트는 Vault의 `review resolve`를 테스트 도우미로 직접 실행한다. `vg` 명령을 거치는 수락 테스트는 없다.

### X13. 2026-11-19 첫 실제 드리밍 실행에서 본 것
- source: brief의 발견8~발견11 (사용자 관찰, 이 조사에서 다시 실행하지 않음)
- basis: X1, X6

제안 2개가 검토 대기열에 들어갔다. 사용자가 파일의 `status`를 손으로 `accepted`로 고치자 발행은 되지 않았고, 그 뒤 정상 명령은 "Review item is already accepted"로 거부됐으며, `vg dream status`는 수락률 1.00을 보였다. 거부 문구와 수락률 계산은 코드와 맞는다.
