# 5. cli-schedule-commands

## id
5

## title
`vg dream scheduled`와 `at`을 더하고 `on`/`off`가 스케줄을 설치하고 제거한다

## goal
사용자가 `vg dream on`, `vg dream at HH:MM`, `vg dream off`로 정해진 시각 실행을 켜고 끄고 바꿀 수 있다. 설치 실패는 놓치지 않게 알린다.

## units
D6, D13, F5, F6, F9, A2, A4, A5

## files
- src/vault_graph/interface/cli/dream_commands.py
- tests/test_cli_dream_schedule.py

## blockers
1, 2, 3, 4

## checks
- tests/test_cli_dream_schedule.py

## done-when
- [ ] 숨은 명령 `vg dream scheduled --graph-home PATH`가 `run_scheduled_dreams`를 부르고 그 종료 코드로 끝난다
- [ ] 스케줄 구현을 갈아 끼울 수 있다(테스트용 가짜). 기본은 `LaunchdDreamSchedule`이고 작업자 스크립트는 task 3이 내보낸 것을 쓴다
- [ ] `on`은 설정 저장 뒤 설치한다. `off`는 제거한다. 올라가 있지 않음 실패는 0이다
- [ ] `at HH:MM`은 형식을 검사한다. 잘못된 값은 이유를 내고 1로 끝나며 파일 바이트가 그대로다
- [ ] 켜져 있으면 `at`이 저장 뒤 새 시각으로 설치를 한 번 부른다. 꺼져 있으면 저장만 하고 설치를 부르지 않는다
- [ ] 설치 실패 시 설정은 저장된 채로 "schedule: not installed: <이유>"와 "hook runs still work"를 내고 1로 끝난다
- [ ] macOS가 아니면 `on`이 설정을 저장하고 "schedule: unsupported on <플랫폼>"을 내고 0으로 끝난다. plist도 `launchctl` 호출도 없다
