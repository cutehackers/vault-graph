## id
10

## title
S8b 프로젝트 범위 규칙: `page_in_project`, `VaultProjectScope`, `sharable` 읽기와 미설정 안내

## goal
회상, 요약, L3 목록, 정리 꾸러미가 같은 규칙으로 "이 프로젝트의 기억"을 고르고, 다른 프로젝트 기억이 섞이지 않는다. (Intent 7)

## spec
§4.4.2, §6 `sharable` 행, 위험D4, 위험D13

## acceptance
A-20(vg 쪽, 가짜 `VaultProjectScope`)

## files
- src/vault_graph/context/memory/project_scope.py (신규)
- src/vault_graph/operation/integration/vault_map.py
- src/vault_graph/context/pack/recall.py
- src/vault_graph/context/memory/project_memory.py
- src/vault_graph/operation/diagnostics/index_status_reader.py
- src/vault_graph/interface/cli/hook_commands.py
- tests/test_page_in_project.py (신규)
- tests/test_vault_map_sharable.py (신규)
- tests/test_sharable_notice.py (신규)

## blockers
1, 6, 요청S4(외부, vault-builder `sharable` 필드와 설정 명령)

## checks
pytest tests/test_page_in_project.py tests/test_vault_map_sharable.py tests/test_sharable_notice.py tests/test_vault_map.py tests/test_recall_pins.py tests/test_session_recall.py tests/test_project_memory_service.py -q

## wave
3

## done-when
- [ ] 18경우 표 테스트가 규칙1~3대로다. 연결 프로젝트 하나뿐인 Vault는 `sharable`과 무관하게 참이다
- [ ] `sharable` 필드 없음과 false가 같은 결과이고, 불리언이 아니면 경고와 false다
- [ ] 연결 프로젝트가 둘 이상인 Vault만 `vg status`와 session-start 표준 오류에 설정 안내 한 줄이 나온다
- [ ] false Vault의 `project` 없는 페이지는 회상에는 없고 `vg search`에는 있다
- [ ] `recall.py:_in_project`가 사라지고 `page_in_project` 정의가 M10 한 곳이다
- [ ] vault-graph pytest 전체 통과, 독립 커밋

## notes
요청S4 없이도 vg 쪽은 가짜 `vault-map.json`으로 만들고 단위 테스트할 수 있다. 요청S4가 필요한 부분은 안내 문구 속 설정 명령 이름과 이 컴퓨터 실측(#16)이다. 설정 명령 이름이 미정이면 상수 한 곳에 두고 #16에서 확정한다. `main.py`는 건드리지 않는다.
