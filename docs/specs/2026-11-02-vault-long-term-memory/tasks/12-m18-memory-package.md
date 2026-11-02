## id

12

## title

[vault-graph] G1. M18 `operation/memory/`를 만들고 `remember_service.py`를 옮긴다 (동작 변경 없음)

## goal

Vault 기억 쓰기가 설정 기록 영역 M17에서 나와 자기 영역을 갖고, 가져오기 방향 예외 0건과 순환 0건이 유지된다. spec Intent 7, 결정S1을 다룬다.

## files

저장소: vault-graph (이 worktree, 브랜치 `feat/jh/local-graph`)

- `src/vault_graph/operation/memory/__init__.py`, `memory_requests.py`, `memory_ports.py`, `memory_drafts.py`, `memory_write_service.py` (새 파일, 기존 코드를 책임별로 나눠 옮김)
- `src/vault_graph/operation/integration/remember_service.py` (삭제)
- `src/vault_graph/interface/mcp/mcp_tools.py`, `mcp_tool_serialization.py`, `mcp_service_factory.py` (가져오기 경로만)
- `src/vault_graph/interface/composition/adapters/vault_publish_cli.py` (가져오기 경로만)
- `tests/test_feature_import_direction.py`
- `tests/test_remember_service.py` → `tests/test_memory_write_service.py` (`git mv`)

## blockers

1

## acceptance

A-19, A-20, A-22 (MCP 입출력 무변경)

## checks

vault-graph worktree에서 실행한다.

- `uv run --python 3.12 --all-packages --all-extras pytest -q tests/test_feature_import_direction.py tests/test_module_import_cycles.py tests/test_functional_module_boundaries.py tests/test_memory_write_service.py tests/test_mcp_tools.py tests/test_vault_publish_cli.py`
- `grep -rn "operation.integration.remember_service" src tests` (0건)
- `uv run --python 3.12 --all-packages --all-extras pytest -q`

## done-when

- [ ] `_AREAS`에 `"operation/memory/": "M18"`이 있다
- [ ] `_ALLOWED`의 M18은 `{M01, M12}`이고, 어떤 영역도 M18을 가리키지 않는다
- [ ] `_PLANNED_MODULES`에 spec V1의 새 파일(`memory_target.py`, `recall_pins.py`, `vault_labels.py`, `vault_page_reader.py`, `vault_capture_cli.py` 포함)이 모두 있어, 뒤 작업이 이 테스트를 고치지 않는다
- [ ] `_KNOWN_VIOLATIONS == frozenset()`, `_KNOWN_VIOLATION_CEILING == 0`이다
- [ ] 이름만 바뀐 테스트 파일 외에는 기존 테스트가 고침 없이 통과한다
- [ ] MCP 도구가 12개 그대로이고 입출력이 같다

멈춤: M18이 M01·M12 밖의 영역을 가져와야 하면 예외를 추가하지 않고 보고한다.
