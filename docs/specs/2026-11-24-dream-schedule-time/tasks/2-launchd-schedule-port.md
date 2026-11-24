# 2. launchd-schedule-port

## id
2

## title
`DreamSchedule` 프로토콜과 launchd 구현 `LaunchdDreamSchedule`을 만든다

## goal
vg가 OS에 정해진 시각 실행을 설치, 제거, 조회할 수 있다(D4). 테스트는 실제 LaunchAgents와 launchctl을 건드리지 않는다(I6).

## units
D4, D11, I6, A3

## files
- src/vault_graph/interface/composition/adapters/dream_schedule.py
- tests/test_dream_schedule.py

## blockers
none

## checks
- tests/test_dream_schedule.py

## done-when
- [ ] `DreamSchedule`(`install`, `remove`, `state`)와 `ScheduleResult`, `ScheduleState`(installed, not_installed, stale, unsupported)가 있다
- [ ] 생성자가 LaunchAgents 폴더, `launchctl` 실행 함수, 플랫폼 이름, 작업자 스크립트 문자열을 받는다. 스크립트는 호출한 쪽이 넘기며, 이 task는 `dream_worker.py`를 쓰지 않는다
- [ ] plist 글은 순수 함수가 만들고, `Hour`/`Minute`가 `run_at`과 같다
- [ ] `ProgramArguments`는 `sys.executable`, `-c`, 작업자 스크립트, `dream scheduled --graph-home <경로>`다
- [ ] `EnvironmentVariables`에 `PATH`, `HOME`이 있고, 있으면 `VAULT_GRAPH_VAULT_MAP`과 `CLAUDE_CONFIG_DIR`도 있다
- [ ] Label에 Graph Home 해시가 붙고, 출력 경로가 `logs/dream-schedule.log`다
- [ ] 설치는 plist를 쓴 뒤 `bootstrap`을 부르고, 다시 설치하면 먼저 `bootout`한다
- [ ] 제거는 `bootout` 뒤 파일을 지운다. 올라가 있지 않음 실패는 성공으로 본다
- [ ] `state()`는 plist가 있지만 Python 경로가 없거나 시각이 다르면 `stale`을 낸다
- [ ] 플랫폼이 macOS가 아니면 `unsupported`이고 파일도 `launchctl` 호출도 없다
- [ ] 테스트가 `$HOME/Library/LaunchAgents`를 건드리지 않는다
