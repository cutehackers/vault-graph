## id

19

## title

[vault-graph] G6. V3 inferred 경로. 계약4 `review propose`로 제안을 보내고 승인 명령을 안내한다

## goal

에이전트가 추론한 사실이 바로 확정되지 않고 Vault 검토 대기열로 가며, 승인 전에는 회상과 검색에 나오지 않는다. spec Intent 3, 결정6·S5를 다룬다.

## files

저장소: vault-graph (이 worktree, 브랜치 `feat/jh/local-graph`)

- `src/vault_graph/operation/memory/memory_write_service.py`
- `src/vault_graph/interface/composition/adapters/vault_publish_cli.py` (`propose`)
- `src/vault_graph/interface/mcp/mcp_tool_serialization.py` (`review_path`)
- `tests/test_memory_write_service.py`
- `tests/test_vault_publish_cli.py`

## blockers

6, 17

## acceptance

A-3 (단위 수준. 실제 Vault 증명은 작업 21), A-18

## checks

vault-graph worktree에서 실행한다.

- `uv run --python 3.12 --all-packages --all-extras pytest -q tests/test_memory_write_service.py tests/test_vault_publish_cli.py tests/test_mcp_tools.py tests/test_memory_write_boundary.py tests/test_feature_import_direction.py`
- `uv run --python 3.12 --all-packages --all-extras pytest -q`

## done-when

- [x] 작업 17의 중간 동작(`inferred` → `rejected`)이 없어졌다
- [x] `remember`, `update_memory`, `retire_memory` 모두 `basis="inferred"`면 `VaultWriter.propose`를 부르고 `proposed`와 `review_path`를 돌려준다
- [x] `messages`에 `review resolve <review_path> --status accepted --resolution "<사유>"` 한 줄이 있다
- [x] 어댑터는 `vault-review-result/v1` JSON만 읽고, 종료 코드 1은 `rejected`, 2는 마이그레이션 안내 `error`다
- [x] `scratch/review/`를 색인하지 않는다는 기존 범위 테스트가 통과한다

멈춤: 작업 6의 `review propose --json` 출력이 spec 계약4와 다르면 보고한다.

기록 (2026-11-02): 전체 pytest 1863 passed, 1 skipped. 실제 vault-builder를 복사한 Vault에서 `review propose --json` 테스트 통과(건너뜀 0). 범위 조정: `memory_ports.py`에 `propose`·`proposed`·`review_path`, `tests/test_memory_write_boundary.py`에 제안 경로를 더했다. `scratch/review/`는 `DEFAULT_CONTENT_SCOPES`(`raw`, `wiki`, `docs`, `scratch/reports`) 밖이라 색인되지 않는다. 승인 안내의 자리표시는 다른 메시지와 맞춰 영어 `<reason>`이다.
