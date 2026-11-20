# 3. `vg review` 명령 그룹과 쓰기 경계

## id

3

## title

`vg review` 명령 그룹과 쓰기 경계

## goal

프로젝트 폴더에서 명령 하나로 연결된 모든 Vault의 제안을 읽고 수락·거절한다. 수락한 Vault는 배경에서 색인한다. 에이전트가 스스로 수락하는 길은 늘지 않는다. (Intent 전체, 특히 1·3·5번째 항목)

## units

D1, D2, D3, D5, D6, D8, I1, I2, I4, A1, A2, A4, A5, A7, A8, F1, F6, F7, F8, F9, F10, F11

## files

- src/vault_graph/interface/cli/review_commands.py
- src/vault_graph/interface/cli/main.py
- tests/test_cli_review.py
- tests/test_review_write_boundary.py

## blockers

1, 2

## checks

- tests/test_cli_review.py
- tests/test_review_write_boundary.py

## done-when

- [ ] `vg review`, `list`, `show`, `accept`, `reject`가 있고 `--cwd`, `--graph-home`, `--vault-map`을 받는다.
- [ ] `main.py`에 등록한다.
- [ ] 연결된 모든 Vault를 읽는다. Graph Home에 등록되지 않은 Vault도 포함하고, 같은 ID가 두 Vault에 있으면 `--vault`를 요구한다.
- [ ] 대화형은 stdin과 stdout이 둘 다 터미널일 때만 묻는다. 아니면 목록과 안내만 내고 종료 코드 0이다.
- [ ] `VAULT_GRAPH_FACTS_CHILD=1`이면 모든 하위 명령이 아무것도 안 하고 종료 코드 1이다.
- [ ] `vault_review_cli`를 가져오는 모듈이 `review_commands.py` 하나뿐이다. MCP 도구에 수락·거절이 없다.
- [ ] `list`, `show`, 건너뛰기, 종료 전후로 Vault와 Graph Home 파일의 sha256이 같다.
- [ ] `reject`는 이유가 필수이고, `accept` 기본 이유는 "Accepted in vg review."다.
- [ ] 미발행 수락과 초안을 읽을 수 없는 제안의 수락은 Vault를 실행하지 않고 종료 코드 1이다.
- [ ] 발행이 있었던 Vault마다 실행 끝에 `start_catch_up_index`를 한 번 부르고 기다리지 않는다.
- [ ] 색인을 시작하지 못하거나 Vault가 등록되지 않았으면 `vg index` 안내를 내고 종료 코드 0이다.
- [ ] Vault 쓰기 호출이 `vault_review_cli`에만 있다.

## notes

작업 1이 `vault_review_queue.py`를 쓰므로 이 작업은 그 파일을 읽기만 하고 고치지 않는다. F1의 목록·수치는 작업 1, 수락 거부는 이 작업이다. I5의 "수락·거절로 알림" 출력도 이 작업이 쓴다.
