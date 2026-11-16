# 18. hook-facts

## id
18

## title
수집 훅이 작업 파일을 두고 작업자를 띄우며 자식 세션은 건너뛴다. 새 파일 위치를 ARCHITECTURE에 적는다

## goal
훅은 기다리지 않고 수집 결과가 B 전과 같다. 추출용 `claude -p` 세션이 기억에 닿지 않는다. 이 spec이 더한 파일의 위치와 다섯째 쓰기 경로를 `docs/ARCHITECTURE.md`에 적는다. Intent 3을 맡는다.

## units
D16, I8, I9, F10, F11, F13, A12, A13, A17

## files
- src/vault_graph/interface/cli/hook_commands.py
- docs/ARCHITECTURE.md
- tests/test_hook_facts.py

## blockers
13, 17

## checks
- tests/test_hook_facts.py

## done-when
- [ ] 켜져 있고 수집이 `written`이면 작업 파일 하나와 분리 프로세스가 생긴다. `written`이 아니면 작업 파일이 없다
- [ ] 잠금이 잡혀 있으면 띄우지 않는다
- [ ] 종료 코드와 출력이 꺼짐과 같고, 느린 가짜 추출기에서도 훅이 1초 안에 끝난다
- [ ] `VAULT_GRAPH_FACTS_CHILD=1`이면 `vg hook capture`와 `vg hook session-start`가 실행기와 회상을 부르지 않고 0으로 끝난다
- [ ] 설정 파일이 없는 기존 설치도 켜짐이고, 첫 작업에서만 stderr 안내 한 줄과 안내 기록이 있다. 지난 세션은 대기열에 들지 않는다
- [ ] 꺼짐이면 작업 파일이 없다
- [ ] `docs/ARCHITECTURE.md` §1에 `date_expression.py`, `session_facts_chunker.py`, `facts_settings.py`, 추출기·작업자 어댑터 위치를 적고 §4에 다섯째 쓰기 경로(`sessions attach-facts`)를 더했다
- [ ] `tests/test_grouped_module_layout.py`, `tests/test_feature_import_direction.py`, `tests/test_module_import_cycles.py`가 통과한다
