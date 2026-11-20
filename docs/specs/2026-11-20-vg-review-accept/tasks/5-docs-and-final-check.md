# 5. 규칙 문서, 안내 문구, 최종 점검

## id

5

## title

규칙 문서, 안내 문구, 최종 점검

## goal

규칙 문서와 안내가 여섯째 길과 `vg review`를 같게 적고, 사용자가 준 한계를 지켰는지 확인한다. (Intent의 5번째 항목과 Non-goals)

## units

D10, I6, A10, A11, A12

## files

- AGENTS.md
- docs/SPEC.md
- docs/ARCHITECTURE.md
- docs/DECISIONS.md
- README.md
- README-kr.md
- docs/FEATURES.md
- CHANGELOG.md
- docs/TODO.md
- docs/PATCH_LOG.md
- src/vault_graph/interface/mcp/mcp_server.py
- src/vault_graph/operation/memory/memory_write_service.py

## blockers

3

## checks

- 수동: AGENTS.md, docs/SPEC.md 원칙4·§4·§5, docs/ARCHITECTURE.md §4, docs/DECISIONS.md, README.md, docs/FEATURES.md를 읽고 길 수와 조건, 한계, 명령 안내가 서로 맞는지 본다
- 수동: 대기 제안이 있는 프로젝트 폴더의 터미널에서 vg review를 실행해 하나를 수락하고 하나를 건너뛴 뒤 vg dream status를 본다
- 수동: ruff, mypy, 전체 테스트를 실행하고 git 브랜치와 vault-builder 저장소의 변경 여부를 본다

## done-when

- [ ] 세 규칙 문서가 같은 여섯 길을 같은 순서로 적고, SPEC §4에 사실 첨부를 넣는다.
- [ ] DECISIONS 새 항목에 조건(사람이 친 `vg review`에서만)과 한계(셸로 치는 에이전트는 막지 못함)가 있다.
- [ ] README와 FEATURES가 `vg review`를 가리킨다.
- [ ] MCP 서버 안내와 `proposed` 메시지에 "사람이 프로젝트 폴더에서 `vg review`를 실행한다"는 줄을 더한다. 기존 Vault 명령 줄은 남겨서 `tests/test_memory_write_service.py`, `tests/test_memory_write_boundary.py`, `tests/test_vault_publish_cli.py`가 그대로 통과한다.
- [ ] ruff, mypy, 전체 테스트가 통과한다.
- [ ] 커밋은 `feat/jh/agent-memory-dream`에만 있고 vault-builder 저장소는 변하지 않았으며 MCP 도구 수와 이름은 그대로다.

## notes

승인 때 CHANGELOG.md, README-kr.md, docs/TODO.md, docs/PATCH_LOG.md를 files에 더했다. 구현 중 다른 파일에서 같은 `review resolve` 안내가 나오면 그 파일도 files에 추가한다.
