# 작업 1: `vg setup`에 `--index/--no-index` 옵션 추가

## id

1

## title

`vg setup`에 `--index/--no-index` 옵션과 `SetupRequest.run_index`를 추가한다

## goal

사용자가 색인 없이 Vault 등록, Data Home 초기화, MCP 등록만 할 수 있게 된다. Intent 1(설치는 색인하지 않고 끝남)과 4(색인 전에도 설치 성공, MCP 등록)를 CLI 계층에서 받친다.

## files

- `src/vault_graph/operation/runtime/setup_service.py`
- `src/vault_graph/interface/cli/main.py`
- `tests/test_cli_setup_no_index.py` (새 파일)

## blockers

없음

## acceptance

A-4, A-5, A-6, A-8

## checks

- `uv run --python 3.12 pytest -q tests/test_cli_setup_no_index.py`
- `uv run --python 3.12 pytest -q tests/test_cli_setup.py tests/test_cli_vault_map_setup_status.py`
- `uv run --python 3.12 ruff check src/vault_graph/operation/runtime/setup_service.py src/vault_graph/interface/cli/main.py tests/test_cli_setup_no_index.py`

## done-when

- [ ] `SetupRequest.run_index`(기본 True)가 있고, False면 색인 블록을 건너뛰어 `index_report`가 None이다.
- [ ] `--no-index` 결과가 `indexed=False`, `ready=False`이고 `recovery_hint`에 `vg index --all-vaults`가 있다. dry run 안내가 먼저 나온다.
- [ ] `--no-index`에서도 MCP 설정 파일에 `vault-graph` 항목이 생긴다.
- [ ] `vg setup --help`에 `--no-index`와 `vg index --all-vaults`가 나온다.
- [ ] 새 테스트가 `vault-map.json`의 Vault 2개 임시 환경에서 통과한다. 검증 항목은 종료 코드 0, 카탈로그의 Vault 2개, 메타데이터 SQLite 파일 없음, Vault마다 `indexed: False` 줄, `create_mcp_server` 무예외, 검색 도구의 `metadata_unavailable` 또는 `keyword_index_unavailable` 코드다.
- [ ] `vg setup --no-index --dry-run`이 Data Home에 아무것도 만들지 않는다는 테스트가 있다.
- [ ] 기존 `tests/test_cli_setup.py`와 `tests/test_cli_vault_map_setup_status.py`가 수정 없이 통과한다.
