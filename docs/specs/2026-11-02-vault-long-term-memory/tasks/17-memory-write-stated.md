## id

17

## title

[vault-graph] G4. V3 stated 경로. `remember`, `update_memory`, `retire_memory`, 저장 Vault 고르기, 계약1 `--json` 어댑터를 만든다

## goal

에이전트가 사용자가 말한 사실을 추가·수정·폐기하면 Vault 검사를 통과하는 순간 확정된다. 저장 Vault는 결정12대로 정해지거나 되물어진다. spec Intent 3·4, 결정12·A2·A3·S3·S5·S6·S8을 다룬다.

## files

저장소: vault-graph (이 worktree, 브랜치 `feat/jh/local-graph`)

- `src/vault_graph/operation/memory/memory_requests.py`, `memory_target.py` (새 파일), `memory_drafts.py`, `memory_ports.py`, `memory_write_service.py`
- `src/vault_graph/interface/composition/adapters/vault_publish_cli.py`
- `src/vault_graph/interface/composition/adapters/vault_page_reader.py` (새 파일)
- `src/vault_graph/interface/mcp/mcp_tools.py`, `mcp_tool_serialization.py`, `mcp_service_factory.py`
- `tests/test_memory_write_service.py`
- `tests/test_memory_target.py` (새 파일)
- `tests/test_memory_drafts.py` (새 파일)
- `tests/test_vault_publish_cli.py`
- `tests/test_mcp_tools.py`
- `tests/test_memory_write_boundary.py` (새 파일)

## blockers

3, 4, 5, 12, 14, 15

## acceptance

A-2 (가짜 포트로 단위 수준. 실제 Vault 증명은 작업 21), A-8, A-17 (3번째 항목), A-18, A-19, A-22

## checks

vault-graph worktree에서 실행한다.

- `uv run --python 3.12 --all-packages --all-extras pytest -q tests/test_memory_write_service.py tests/test_memory_target.py tests/test_memory_drafts.py tests/test_vault_publish_cli.py tests/test_mcp_tools.py tests/test_memory_write_boundary.py tests/test_feature_import_direction.py tests/test_module_import_cycles.py`
- `grep -rnE "write_text|write_bytes|open\(.*['\"][wa]" src/vault_graph/operation/memory` (임시 draft 하나뿐이어야 함)
- `uv run --python 3.12 --all-packages --all-extras pytest -q`

## done-when

- [ ] A-8 표의 네 경우가 통과하고, `memory_kind`를 바꿔도 고른 Vault가 같다
- [ ] 명시한 `vault`는 `cwd` 프로젝트의 연결 Vault 안에서만 찾고, 연결되지 않은 이름이면 `rejected`와 연결 Vault 목록을 돌려준다
- [ ] 수정·폐기 대상 Vault 찾기가 0개(`rejected`), 1개(그 Vault), 2개 이상(`vault_required`)에서 맞게 동작한다
- [ ] draft 네 가지(추가, 수정, 대체 없는 폐기, 대체 있는 폐기)가 입력과 날짜만으로 결정되는 순수 함수다
- [ ] 수정은 잠금 안에서 읽은 sha256을 publish 직전에 다시 확인하고, 다르면 `rejected`다
- [ ] 같은 경로가 있으면 추가는 publish 전에 `rejected`이고 `update_memory`를 쓰라고 안내한다
- [ ] 어댑터는 계약1 JSON만 읽는다. 종료 코드 2와 `unrecognized arguments`는 "계약 4로 마이그레이션하라" `error`, JSON이 아니면 마지막 20줄을 담은 `error`, 120초 초과는 지금과 같은 `error`다
- [ ] `reason: human-locked`가 Vault 메시지와 함께 `rejected`로 전달된다
- [ ] MCP 도구가 14개이고, 세 쓰기 도구의 `basis`는 필수이며 기본값이 없다. 기존 11개 도구의 입출력은 그대로다
- [ ] 가짜 `VaultWriter`로 세 도구를 실행해도 Vault 폴더의 파일 sha256이 바뀌지 않는다
- [ ] 이 작업에서 `basis="inferred"`는 Vault 명령을 부르지 않고 `rejected`를 돌려준다. 작업 19가 이 동작을 `proposed` 경로로 바꾼다. 이 중간 동작은 2026-11-02 분해 승인 때 허용되었고, 커밋 메시지에 적는다

멈춤: 작업 3의 `--json` 출력 형식이 spec 4.2 계약1과 다르면 텍스트 해석으로 돌아가지 않고 보고한다.
