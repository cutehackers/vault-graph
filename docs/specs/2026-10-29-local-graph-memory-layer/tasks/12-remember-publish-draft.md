## id

12

## title

1차-4 MCP `remember`와 publish-draft 어댑터를 만들고 README를 고친다 [선택 수동]

## goal

에이전트가 vault-graph MCP 하나로 기억을 남기고, 그 기록은 Vault 도구의 publish-draft 검증을 거친다. spec Intent 4, 결정8, S5·S6을 다룬다.

## files

- `src/vault_graph/operation/integration/remember_service.py` (새 파일)
- `src/vault_graph/interface/composition/adapters/vault_publish_cli.py` (새 파일)
- `src/vault_graph/interface/mcp/mcp_tools.py`
- `src/vault_graph/interface/mcp/mcp_tool_serialization.py`
- `src/vault_graph/interface/mcp/mcp_service_factory.py`
- `README.md` (5~13행)
- `tests/test_remember_service.py`
- `tests/test_vault_publish_cli.py` (A-14는 Vault 도구가 없으면 건너뜀)
- `tests/test_mcp_tools.py` (도구 목록 12개)
- `tests/test_remember_write_boundary.py` (호출되면 실패하는 publisher 대역으로 A-15 검사)

Vault `tools/wiki/lib/draft.py`와 `tools/wiki/cli.py`는 읽기만 한다.

## blockers

7, 11

결정 (2026-10-30 승인): 보완4(작업 11)를 이 작업의 blocker로 둔다.

## acceptance

A-13, A-14 (선택), A-15, A-16, A-20, A-21, A-22

## checks

- `uv run --python 3.12 --all-packages --all-extras pytest -q tests/test_remember_service.py tests/test_vault_publish_cli.py tests/test_mcp_tools.py tests/test_mcp_tool_read_only_boundary.py tests/test_remember_write_boundary.py tests/test_readme_onboarding_contract.py tests/test_feature_import_direction.py`
- `grep -rnE "^\s*(import|from) (openai|anthropic)" src` (0건)
- CI 검증 세 명령 (작업 1의 checks와 같음)

## done-when

- [ ] 구현 전에 Vault `tools/wiki/lib/draft.py`를 읽고 draft 형식과 성공 출력 해석을 정했다
- [ ] 입력 확인 실패는 `rejected`이고 publisher가 불리지 않는다
- [ ] 대상 Vault는 `vault` 인자, 연결 Vault 하나, 그 밖에는 `error` 순서로 정해진다
- [ ] 임시 draft가 성공, 실패, 시간 초과에서 모두 지워진다
- [ ] 같은 Vault에 대한 호출은 순서대로 실행되고, 120초가 지나면 `error`다
- [ ] publisher 결과가 `published`, `rejected`, `error`로 그대로 옮겨지고, vault-graph 자신은 Vault 루트 아래에 파일을 만들지 않는다
- [ ] MCP 도구가 기존 11개와 `remember`이고, 기존 11개의 이름과 입력·출력 스키마가 `28f1c96`과 같다
- [ ] 기존 read-only 테스트, `vg index`, `vg watch`에서 publisher가 불리지 않는다
- [ ] README 정의와 경계 문단이 remember를 반영하고, onboarding 계약 테스트는 바꾸지 않은 채 통과한다
- [ ] `project-bindings.json` 관련 코드와 `vg vault add`가 남아 있다
- [ ] (선택 수동) 임시 디렉터리에 복사한 Vault에서 A-14가 통과했다. 실제 사용자 Vault로는 실행하지 않는다
