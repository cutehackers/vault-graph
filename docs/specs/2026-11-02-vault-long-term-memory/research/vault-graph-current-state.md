# vault-graph가 지금 여러 Vault와 기억을 다루는 방식

조사 기준: `feat/jh/local-graph` 0a9057b + 커밋 안 된 `docs/SPEC.md` §0, `docs/DECISIONS.md` 2026-11-02 항목.

## 1. Vault 모델과 여러 Vault 검색

- Graph Home catalog는 `VaultCatalog`이고 항목과 `active_vault_id` 하나를 가진다 (`src/vault_graph/operation/scope/vault_catalog.py:72-131`). 항목에 종류 필드가 없다.
- `vg setup`(`--vault` 없음)은 `vault-map.json`의 모든 Vault를 catalog에 넣는다 (`src/vault_graph/interface/cli/main.py:378-458`).
- 범위를 주지 않으면 모든 검색 경로가 활성 Vault 하나만 검색한다 (`vault_catalog.py:142-144`, `src/vault_graph/interface/mcp/mcp_scope.py:24-40`, `main.py:205-213`, `src/vault_graph/interface/http/http_server.py:224-237`).
- `all_vaults`나 `vault_ids`를 주면 `fuse_candidates`가 (vault_id, chunk_id)로 합친 한 순위를 만든다 (`src/vault_graph/retrieval/search/candidate_ranking.py:26-51`).
- `resolve_project_vaults`(`src/vault_graph/interface/composition/query_scope_resolution.py:38-86`)는 세션 시작 회상만 쓴다. MCP `search_vault`는 `cwd`를 받지 않는다 (`src/vault_graph/interface/mcp/mcp_tools.py:676-692`).
- 결과에는 `vault_id`만 있다 (`src/vault_graph/retrieval/search/retrieval_result.py:58`). Vault 이름과 종류가 없다. `MappedVault.role`은 읽기만 하고 쓰지 않는다.

## 2. 세션 시작 회상

- `src/vault_graph/context/pack/recall.py`, `src/vault_graph/interface/cli/hook_commands.py`.
- 블록 A(pin): 비어 있다. `pin`을 읽는 코드가 없다.
- 블록 B: 프로젝트 `wiki/` 페이지를 최신순으로 정렬하고, usage 기록으로 순서를 바꾼다 (`recall.py:404-423`). 10번 넣었는데 한 번도 열지 않은 페이지를 내린다 (`recall.py:33, 410-417`). 이것은 §0 규칙5 위반이다.
- 여러 Vault 페이지가 한 목록으로 섞이고, 관련도가 아니라 최신순이다.
- 예산은 공백 단위 1,500토큰과 9,000자이다.

## 3. remember

- `src/vault_graph/operation/integration/remember_service.py:133-151`. 명시한 `vault`를 찾을 때 프로젝트에 연결된 Vault로 범위를 좁히지 않고 map의 모든 Vault에서 찾는다.
- Vault가 여럿이면 status `error`와 함께 "the project links several Vaults ... Pass vault."를 돌려준다. `vault_required` 코드와 기본 저장 Vault 단계가 없다.
- 새 페이지만 추가한다. 이미 있는 페이지면 거부한다.

## 4. usage 로그

- `src/vault_graph/storage/local/usage_log.py:16-59`: `usage/YYYY-MM.jsonl`에 `injected`, `fetched` 이벤트를 쓴다.
- 회상 순위에 영향을 준다(위 2). 검색은 읽지 않는다.

## 5. Vault에 쓰는 다른 경로

- remember 하위 프로세스 외에는 없다 (`src/vault_graph/interface/composition/adapters/vault_publish_cli.py:36`).
- 예외 하나: harness guidance 설치기는 사용자가 지정한 곳에 `AGENTS.md`/`CLAUDE.md`를 쓰는데, 그곳이 Vault 안인지 검사하지 않는다 (`src/vault_graph/operation/integration/harness/harness_guidance.py:46-50, 260-264`).

## 6. 갱신할 문서

- `docs/html/2026-10-29-vault-memory-design.html`: 여러 Vault 연결이 vault-builder 몫이라는 문장, "검색·회상 계층"이라는 정의, remember 단일 쓰기.
- `docs/SPEC.md`: §2 표, 87행의 "쓰기·검증·여러 Vault 연결은 vault-graph 일이 아님", §4·§5 remember, §6.1 vault-map 필드, §9.
- `docs/ARCHITECTURE.md` §4, VG-MOD INV-01·INV-02(`docs/design/specs/2026-10-15-vault-graph-modular-architecture-ko.md:127-128`), `README.md` 5-17행.

## 7. 이전 spec의 남은 일

- `docs/specs/2026-10-29-local-graph-memory-layer`: 작업13(한국어 `body_stem`), 작업14(재측정, 수동).
- 의존1~7(spec.md §4.4): SessionStart 훅, 세션 수집기, raw/sessions 예외(요청1·2로 구현됨, 미병합), 정리 스킬 확정 규칙, `vault-memory/v1`과 `pin`·`memory_kind`, publish-draft 버전 표시, vault-map version 2 유지.
