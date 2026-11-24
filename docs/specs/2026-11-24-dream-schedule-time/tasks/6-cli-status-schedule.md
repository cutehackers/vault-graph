# 6. cli-status-schedule

## id
6

## title
`vg dream status`에 실행 시각, 스케줄 상태, 마지막 시각 실행을 더하고 실제 Mac에서 확인한다

## goal
사용자가 시각 실행이 설치됐는지, 낡았는지, 실제로 돌았는지를 `status`로 알 수 있다. 업그레이드한 사용자는 재설치가 필요하다는 것을 알게 된다.

## units
D5, D9, F10, F13, F14, A11, A12

## files
- src/vault_graph/interface/cli/dream_commands.py
- tests/test_cli_dream_schedule.py

## blockers
5

## checks
- tests/test_cli_dream_schedule.py
- 수동: macOS에서 `vg dream on` 뒤 `vg dream at`을 2분 뒤 시각으로 바꾸고 기다린 다음, 같은 확인을 Mac을 그 시각 전후로 재워서 한 번 더 한다. 결과는 `logs/dream-runs.jsonl`의 `trigger="schedule"` 줄(각 줄의 `cwd`가 vault-map 루트)과 `vg dream off` 뒤 `launchctl list`에서 본다

## done-when
- [ ] `status`가 `run_at: HH:MM (local)`을 보인다
- [ ] `status`가 `schedule: installed|not_installed|stale|unsupported`와 plist 경로나 이유를 보인다
- [ ] 켜져 있는데 `not_installed`나 `stale`이면 "run `vg dream on` to install it" 안내가 붙는다
- [ ] `last_scheduled_run`이 `trigger="schedule"`인 마지막 `run` 줄의 시각을 보인다. 없거나 `trigger` 없는 옛 줄뿐이면 `-`다
- [ ] 기존 `status` 줄은 바뀌지 않는다
- [ ] 실제 Mac에서 정해진 시각에 등록 프로젝트마다 `trigger="schedule"` 줄이 생긴다
- [ ] 재운 경우 깨어난 뒤 한 번 돌고, `vg dream off` 뒤 `launchctl list`에 Label이 없다
