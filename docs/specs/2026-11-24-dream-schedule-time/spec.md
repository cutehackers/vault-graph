# 드리밍을 정해진 현지 시각에 등록된 프로젝트 전체에 대해 실행하기

<!-- bake: index -->
| ID | title | status | relations | covered by | area | hash | tasks |
|---|---|---|---|---|---|---|---|
| I1 | 시각 실행은 한 번에 프로젝트 하나만 돈다 |  | basis D3, D8 | A6, A9 | global | 4ba3b0e1 | 4-scheduled-run-all-projects.md |
| I2 | 시각 실행의 판단 명령은 프로젝트 루트에서 돈다 |  | basis D10, X3, X8 | A10 | schedule-run | 8ad84b66 | 3-dream-trigger-and-judge-cwd.md |
| I3 | 훅 실행은 지금과 같게 동작한다 |  | basis D2, X2, X6 | A8 | hook | a4e7d186 | 3-dream-trigger-and-judge-cwd.md |
| I4 | 시각 실행은 간격 검사만 건너뛴다 |  | basis D7, X2 | A7 | schedule-run | a8c2bce4 | 3-dream-trigger-and-judge-cwd.md |
| I5 | `run_at`이 없는 기존 설정 파일도 그대로 읽힌다 |  | basis D6, X1 | A1 | settings | 690df258 | 1-dream-settings-run-at.md |
| I6 | 테스트는 실제 LaunchAgents와 launchctl을 건드리지 않는다 |  | basis D4, D11 | A3 | schedule-port | a9f22217 | 2-launchd-schedule-port.md |
| D1 | 기본 실행 시각은 현지 01:00이고 사용자가 바꿀 수 있다 | decided |  | A1 | global | edc380c8 | 1-dream-settings-run-at.md |
| D2 | 훅 실행을 남기고 시각 실행을 더한다 | decided | basis X6 | A8 | global | a8e93df6 | 3-dream-trigger-and-judge-cwd.md |
| D3 | 시각 실행의 대상은 루트 폴더가 있는 등록 프로젝트 전체다 | decided | basis X5 | A6 | schedule-run | 6da2ebce | 4-scheduled-run-all-projects.md |
| D4 | 스케줄러는 macOS launchd LaunchAgent다 | decided | basis X7; depends D5 | A3, A4, A12 | schedule-port | 8a0250e7 | 2-launchd-schedule-port.md |
| D5 | Mac이 잠든 동안 지난 시각은 깨어난 뒤 한 번 돈다 | decided | basis D4 | A12 | schedule-port | 51612d29 | 6-cli-status-schedule.md |
| D6 | 시각은 `configs/dream.json`의 `run_at`이고 `vg dream at HH:MM`으로 바꾼다 | decided | basis D1, X1; depends I5 | A1, A2 | settings, cli | 85c1b6d5 | 5-cli-schedule-commands.md |
| D7 | 시각 실행은 24시간 간격 검사를 건너뛴다 | decided | basis X2 | A7 | schedule-run | ebfb1ceb | 3-dream-trigger-and-judge-cwd.md |
| D8 | 잠금이 잡혀 있으면 30분까지 기다리고, 넘으면 그 프로젝트를 건너뛴다 | decided | basis X6 | A9 | schedule-run | 6a51208a | 4-scheduled-run-all-projects.md |
| D9 | `vg dream status`가 실행 시각, 스케줄 상태, 마지막 시각 실행을 보인다 | decided | basis X9, D12 | A11 | cli | 5379db85 | 6-cli-status-schedule.md |
| D10 | 시각 실행은 프로젝트 루트를 cwd로 쓴다 | decided | basis X3, X8 | A10 | schedule-run | fe277942 | 4-scheduled-run-all-projects.md |
| D11 | plist는 설치한 순간의 Python과 환경을 적는다 | decided | basis X4 | A3 | schedule-port | a4711d02 | 2-launchd-schedule-port.md |
| D12 | `run` 줄에 `trigger`를 적는다 | decided | basis X10; depends D7, D8 | A7, A11 | worker | 992565e7 | 3-dream-trigger-and-judge-cwd.md |
| D13 | 스케줄 설치에 실패하면 설정은 저장하고 종료 코드 1로 알린다 | decided | basis D4 | A5 | cli | 51034c38 | 5-cli-schedule-commands.md |
| F1 | 등록된 루트 폴더가 없다 |  | basis D3 | A6 |  | 31dbf460 | 4-scheduled-run-all-projects.md |
| F2 | 루트는 있지만 프로젝트로 찾아지지 않거나 쓰기 Vault가 없다 |  | basis D3, X5 | A6 |  | 798c7eb1 | 4-scheduled-run-all-projects.md |
| F3 | 잠금이 30분 넘게 잡혀 있다 |  | basis D8 | A9 |  | 98c9e2ae | 4-scheduled-run-all-projects.md |
| F4 | 드리밍이 꺼졌는데 launchd가 시각 실행을 부른다 |  | basis D4, I4 | A7 |  | fe53624b | 4-scheduled-run-all-projects.md |
| F5 | macOS가 아니다 |  | basis D4, D13 | A4 |  | ab2cb4fb | 5-cli-schedule-commands.md |
| F6 | plist 쓰기나 launchctl이 실패한다 |  | basis D13 | A5 |  | 7970e9b5 | 5-cli-schedule-commands.md |
| F7 | 기존 설정 파일에 `run_at`이 없다 |  | basis D6, I5 | A1 |  | 6bbc0cc4 | 1-dream-settings-run-at.md |
| F8 | `run_at` 값이 잘못됐다 |  | basis D6 | A1, A2 |  | bbda4eba | 1-dream-settings-run-at.md |
| F9 | 드리밍이 꺼진 상태에서 시각을 바꾼다 |  | basis D6 | A2 |  | 737184e3 | 5-cli-schedule-commands.md |
| F10 | plist의 Python 경로가 사라졌다 |  | basis D9, D11 | A11 |  | d3937505 | 6-cli-status-schedule.md |
| F11 | 시각 실행에서 `claude`를 찾지 못하거나 판단이 실패한다 |  | basis D10, D11 | A10 |  | cf67b198 | 4-scheduled-run-all-projects.md |
| F12 | 한 프로젝트에서 예상하지 못한 오류가 난다 |  | basis D3 | A6 |  | 87f818f0 | 4-scheduled-run-all-projects.md |
| F13 | 이미 드리밍을 켜 둔 사용자가 업그레이드한다 |  | basis D4, D9 | A11 |  | 084e9dd7 | 6-cli-status-schedule.md |
| F14 | 그 시각에 Mac이 잠들어 있거나 꺼져 있다 |  | basis D5 | A12 |  | f2669f01 | 6-cli-status-schedule.md |
| R1 | launchd가 잠든 동안 놓친 시각을 깨어난 뒤 돌린다는 전제 |  | basis D5 |  |  | 6923b08e |  |
| R2 | `launchctl bootstrap`/`bootout`이 이 macOS 버전에서 그대로 동작한다는 전제 |  | basis D4 |  |  | 1bbd23cb |  |
| R3 | `StartCalendarInterval`이 시간대 변경과 일광 절약 시간을 따라간다는 전제 |  | basis D4, D6 |  |  | ea9b8649 |  |
| R4 | launchd에서 띄운 `claude -p`가 사용자 로그인으로 인증된다는 전제 |  | basis D11, X4 |  |  | 4935bd9a |  |
| R5 | 로그인 셸의 PATH가 아닌 설치 프로세스의 PATH로 충분하다는 전제 |  | basis D11 |  |  | ff8cf646 |  |
| R6 | 등록 프로젝트 수와 그 비용 |  | basis D3 |  |  | 4fe81a4f |  |
| A1 | 설정 파일이 `run_at`을 읽고 쓴다 |  | covers D1, D6, I5, F7, F8 |  |  | 230bf774 | 1-dream-settings-run-at.md |
| A2 | `vg dream at`이 시각을 검사하고 저장한다 |  | covers D6, F8, F9 |  |  | c4032916 | 5-cli-schedule-commands.md |
| A3 | launchd 구현이 plist를 쓰고 올리고 내린다 |  | covers D4, D11, I6 |  |  | 6cd9b0e7 | 2-launchd-schedule-port.md |
| A4 | macOS가 아니면 설치하지 않는다 |  | covers D4, F5 |  |  | 6785c3f5 | 5-cli-schedule-commands.md |
| A5 | 설치 실패는 설정을 남기고 1로 끝난다 |  | covers D13, F6 |  |  | 8bc72b0a | 5-cli-schedule-commands.md |
| A6 | 시각 실행이 루트가 있는 프로젝트를 차례로 돈다 |  | covers D3, I1, F1, F2, F12 |  |  | fd965072 | 4-scheduled-run-all-projects.md |
| A7 | 시각 실행은 간격만 건너뛰고 나머지 조건은 지킨다 |  | covers D7, D12, I4, F4 |  |  | f8e97d63 | 3-dream-trigger-and-judge-cwd.md, 4-scheduled-run-all-projects.md |
| A8 | 훅 실행은 바뀌지 않는다 |  | covers D2, I3 |  |  | 7bf01054 | 3-dream-trigger-and-judge-cwd.md |
| A9 | 잠금을 기다리고 시간이 넘으면 건너뛴다 |  | covers D8, I1, F3 |  |  | e312964d | 4-scheduled-run-all-projects.md |
| A10 | 시각 실행의 판단 명령은 프로젝트 루트에서 돈다 |  | covers D10, I2, F11 |  |  | e1b8b1e5 | 3-dream-trigger-and-judge-cwd.md, 4-scheduled-run-all-projects.md |
| A11 | `status`가 실행 시각과 스케줄 상태를 보인다 |  | covers D9, D12, F10, F13 |  |  | 2d481720 | 6-cli-status-schedule.md |
| A12 | 실제 Mac에서 정해진 시각에 돈다 |  | covers D4, D5, F14 |  |  | 5800112c | 6-cli-status-schedule.md |
| O1 | 정해진 시각 실행을 macOS launchd로 설치할까? |  | decides D4, D11 |  |  | d35a501f |  |
| O2 | Mac이 그 시각에 잠들어 있었으면 어떻게 할까? |  | decides D5 |  |  | 0e83ec4d |  |
| O3 | 실행 시각을 어디에 두고 어떤 명령으로 바꿀까? |  | decides D6 |  |  | 0c42888f |  |
| O4 | 시각 실행이 24시간 간격 검사를 건너뛸까? |  | decides D7 |  |  | baf8f868 |  |
| O5 | 01:00에 다른 드리밍 실행이 잠금을 잡고 있으면 어떻게 할까? |  | decides D8 |  |  | ff8531e4 |  |
| O6 | `vg dream status`에 무엇을 더할까? |  | decides D9, D12 |  |  | df4773ca |  |
| O7 | 스케줄 설치가 실패하면 `vg dream on`을 실패로 끝낼까? |  | decides D13 |  |  | 9aca311f |  |
| X1 | 설정 파일의 키 집합이 닫혀 있다 |  |  |  |  | 48538785 |  |
| X2 | 실행 조건과 24시간 간격 검사 |  |  |  |  | 04a6b254 |  |
| X3 | 작업자와 판단 명령은 cwd를 지정하지 않는다 |  |  |  |  | 4f3080d7 |  |
| X4 | 판단 명령은 PATH에서 `claude`를 찾는다 |  |  |  |  | 0084ce23 |  |
| X5 | vault-map은 프로젝트 목록을 밖으로 내주지 않는다 |  |  |  |  | 2bacecc5 |  |
| X6 | 수집 훅이 작업자를 띄우는 길 |  |  |  |  | ce04e4ce |  |
| X7 | vg에는 OS 스케줄러 코드가 없다 |  |  |  |  | ae7c3733 |  |
| X8 | 지워진 worktree를 cwd로 쓴 실행이 실패했다 |  |  |  |  | bac00cf3 |  |
| X9 | 지금 `vg dream` 명령과 `status` 출력 |  |  |  |  | a5748111 |  |
| X10 | `run` 줄에는 실행 경로가 적히지 않는다 |  |  |  |  | c30cccc2 |  |
<!-- bake: index end -->

## 1. Problem

지금 드리밍은 수집 훅이 세션을 쓴 직후에만 돈다(`research/current-code.md` X6). 그래서 드리밍이 언제 도는지는 사람이 일하는 시간에 달려 있다. 개발 중에 `claude -p`가 뒤에서 돌고, 쉬는 시간에는 아무것도 돌지 않는다.

확인한 것:

- vg에는 launchd, cron, systemd를 다루는 코드가 없다. 저장소 grep으로 확인했다(X7).
- 실행은 훅의 `cwd`를 그대로 쓰고, 판단 명령도 cwd를 따로 정하지 않는다(X3). 사용자가 본 실패가 이 때문이다. 981park-flutter-app의 마지막 실행은 지워진 worktree를 cwd로 써서 `claude -p`가 "current directory no longer exists"로 실패했다(X8).
- 설정 파일 `configs/dream.json`은 키 집합이 닫혀 있다. 키를 그냥 더하면 기존 파일이 꺼짐으로 읽힌다(X1).
- 24시간 간격 검사는 어느 경로가 남긴 `run` 줄이든 함께 센다(X2). `run` 줄에는 어느 경로로 돈 실행인지 적히지 않는다(X10).
- vault-map을 읽는 `VaultMap`은 프로젝트 목록과 루트 폴더를 밖으로 내주지 않는다(X5).

확인 방법: 위 파일을 branch `bake/dream-schedule-time`에서 읽고 grep했다. 근거는 `research/current-code.md`에 있다. 기존 드리밍 설계는 `2026-11-19-memory-dreaming:D2`(실행 조건과 한도)와 그 spec의 소유자 결정 2~4다.


## 2. Intent

사용자는 드리밍을 정해진 시각에 돌리고 싶어 한다. 예로 든 시각은 "현지시간 새벽1시", 사람들이 개발을 쉬는 시간이다. 사용자가 시각을 정하지 않으면 기본 시각을 써야 하고, 기본은 01:00 현지 시각으로 승인했다. 사용자가 이 시각을 바꿀 수도 있어야 한다.

정해진 시각 실행은 기존 훅 실행을 대신하지 않고 더해진다. 시각 실행은 vault-map에 루트 폴더가 등록되어 있고 그 폴더가 실제로 있는 프로젝트를 모두, 한 번에 하나씩 돈다.

[가정] 시각 실행은 개발 중에 뒤에서 `claude -p`가 도는 일을 줄이고, 훅 실행이 걸리지 않은 프로젝트도 하루 한 번은 판단받게 하려는 것이다. 사용자는 이 이유를 직접 말하지 않았다.

## 3. Non-goals

- 훅 실행의 동작을 바꾸지 않는다. 훅 실행이 지워진 worktree를 cwd로 쓰는 문제(X8)는 이 spec에서 고치지 않는다. [가정] 사용자는 시각 실행이 프로젝트 루트를 써야 한다고만 정했다.
- macOS 밖(Linux cron, systemd, Windows 작업 스케줄러)에 시각 실행을 설치하지 않는다. [가정]
- 요일, 하루 여러 번, 프로젝트마다 다른 시각을 두지 않는다. 시각은 Graph Home 하나에 하나다. [가정]
- 드리밍의 판단, 제안, 한도 값, 프롬프트를 바꾸지 않는다.
- vault-map에 프로젝트를 등록하거나 고치지 않는다. vault-map은 vault-builder가 쓴다.


## 4. Design

경계는 다섯 곳이다.

1. 설정. `DreamSettings`에 `run_at: str = "01:00"`(현지 시각 "HH:MM")을 더한다. `dream_settings.py`의 키 검사는 `run_at`을 선택 키로 받는다. 읽을 때 없으면 "01:00"이고, 저장할 때는 언제나 쓴다. 형식 버전은 1 그대로다.
2. 스케줄 포트. 새 파일 `src/vault_graph/interface/composition/adapters/dream_schedule.py`에 `DreamSchedule` 프로토콜(`install(run_at) -> ScheduleResult`, `remove() -> ScheduleResult`, `state() -> ScheduleState`)과 launchd 구현 `LaunchdDreamSchedule`을 둔다. 구현은 LaunchAgents 폴더, `launchctl` 실행 함수, 플랫폼 이름을 생성자로 받는다. plist 글은 순수 함수가 만든다.
3. 시각 실행. 숨은 명령 `vg dream scheduled --graph-home PATH`가 launchd가 부르는 입구다. 같은 파일 또는 `dream_worker.py`의 `run_scheduled_dreams`가 vault-map의 프로젝트를 id 순서로 돌며, 프로젝트마다 루트 폴더를 cwd로 `run_dream_locked`를 부른다. `VaultMap`에는 `projects` 속성(id 순서의 `MappedProject` 튜플)을 더한다.
4. 실행 경로 표시. `run_dream`의 `manual: bool`을 `trigger: Literal["hook", "manual", "schedule"]`로 바꾼다. `schedule`은 간격 검사만 건너뛴다. `run` 줄에 `trigger`를 적는다. `open_dream_ports`와 `ClaudeDreamJudge`는 판단 명령의 cwd를 받는다.
5. CLI. `src/vault_graph/interface/cli/dream_commands.py`: `on`은 설정 저장 뒤 스케줄을 설치하고, `off`는 제거하고, 새 명령 `at HH:MM`은 시각을 저장하고 켜져 있으면 다시 설치한다. `status`는 실행 시각, 스케줄 상태, 마지막 시각 실행을 보인다.

훅 경로(`hook_commands.py`의 `_start_dream`, `start_dream_worker`, `vg dream worker`)는 `trigger="hook"`을 넘기는 것 말고는 바뀌지 않는다.

### I1. 시각 실행은 한 번에 프로젝트 하나만 돈다
- by: 사람 (interview gate 답 3)
- area: global
- basis: D3, D8

시각 실행은 프로젝트마다 `logs/dream-worker.lock`을 잡고 한 프로젝트를 끝낸 뒤 다음으로 간다. 훅 실행과 시각 실행도 같은 잠금을 쓰므로 두 실행이 동시에 돌지 않는다.

### I2. 시각 실행의 판단 명령은 프로젝트 루트에서 돈다
- by: 가정 (brief의 관찰에서 정함)
- area: schedule-run
- basis: D10, X3, X8

시각 실행이 넘기는 `cwd`와 `claude -p`의 작업 폴더는 vault-map에 적힌 그 프로젝트의 루트다. 훅이 남긴 cwd나 worktree 경로를 쓰지 않는다.

### I3. 훅 실행은 지금과 같게 동작한다
- by: 사람 (interview gate 답 2)
- area: hook
- basis: D2, X2, X6

훅 실행은 켜짐, 24시간 간격, 대기 한도, 실행 조건을 지금처럼 모두 본다. 시각 실행을 설치했는지와 상관없다.

### I4. 시각 실행은 간격 검사만 건너뛴다
- by: 가정 (brief 가정 4)
- area: schedule-run
- basis: D7, X2

`trigger="schedule"`인 실행은 켜짐, 대기 한도, 실행 조건을 지킨다. 꺼져 있으면 아무 프로젝트도 판단하지 않는다.

### I5. `run_at`이 없는 기존 설정 파일도 그대로 읽힌다
- by: 가정 (기존 사용자의 드리밍이 업그레이드로 꺼지지 않게)
- area: settings
- basis: D6, X1

`run_at` 키가 없는 버전 1 파일은 `source="file"`, `run_at="01:00"`으로 읽힌다. 나머지 키 검사는 바뀌지 않는다.

### I6. 테스트는 실제 LaunchAgents와 launchctl을 건드리지 않는다
- by: 가정 (테스트가 사용자 Mac의 스케줄을 바꾸지 않게)
- area: schedule-port
- basis: D4, D11

`LaunchdDreamSchedule`은 LaunchAgents 폴더와 `launchctl` 실행 함수를 주입받는다. CLI 테스트는 가짜 구현을 쓴다. `$HOME/Library/LaunchAgents`는 실제 실행에서만 기본값이다.


## 5. Decisions

D1~D3은 사용자가 interview gate에서 정했다. D4~D13은 brief의 가정과 이 spec의 가정이고, spec gate에서 확인받는다.

### D1. 기본 실행 시각은 현지 01:00이고 사용자가 바꿀 수 있다
- by: 사람 (interview gate 답 1)
- status: decided
- area: global

사용자가 시각을 정하지 않으면 01:00 현지 시각에 돈다. 사용자는 이 시각을 바꿀 수 있어야 한다. 사용자가 든 이유는 "사람들이 개발을 쉬는 시간"이다.

### D2. 훅 실행을 남기고 시각 실행을 더한다
- by: 사람 (interview gate 답 2)
- status: decided
- area: global
- basis: X6

수집 훅이 dream worker를 띄우는 길은 그대로 둔다. 시각 실행은 그 옆에 더하는 둘째 입구다.

### D3. 시각 실행의 대상은 루트 폴더가 있는 등록 프로젝트 전체다
- by: 사람 (interview gate 답 3)
- status: decided
- area: schedule-run
- basis: X5

vault-map.json의 `projects` 가운데 `root`가 적혀 있고 그 폴더가 실제로 있는 프로젝트를 모두 돈다. 한 번에 하나씩, 프로젝트 id 순서로 돈다. 한 프로젝트가 실패하거나 건너뛰어져도 다음 프로젝트로 넘어간다. 루트가 git 저장소가 아니거나 쓰기 Vault가 없으면 `run_dream`이 지금처럼 건너뛴다.

### D4. 스케줄러는 macOS launchd LaunchAgent다
- by: 사람 (2026-11-24 spec gate: launchd (Recommended). cron은 잠든 동안 실행을 건너뛴다는 비교 뒤 고름)
- status: decided
- area: schedule-port
- basis: X7
- depends: D5

vg가 `$HOME/Library/LaunchAgents/`에 plist를 쓰고 `launchctl bootstrap gui/<uid>`로 올린다. `StartCalendarInterval`의 `Hour`, `Minute`에 `run_at`을 넣는다. `vg dream on`이 설치하고, `vg dream off`가 `launchctl bootout` 뒤 plist를 지운다. macOS가 아니면 설치하지 않고 "schedule: unsupported on <플랫폼>"을 알린다. 이때도 설정은 저장되고 훅 실행은 그대로다. launchd를 고른 이유는 사용자 기기가 macOS이고, cron과 달리 잠든 동안 놓친 시각을 깨어난 뒤 돌리기 때문이다(D5).

### D5. Mac이 잠든 동안 지난 시각은 깨어난 뒤 한 번 돈다
- by: 사람 (2026-11-24 spec gate: 깨어나면 돈다 (Recommended))
- status: decided
- area: schedule-port
- basis: D4

launchd의 기본 동작을 따른다. vg가 따로 놓친 실행을 찾거나 메우지 않는다. 전원이 꺼져 있던 날은 돌지 않고, 그날 프로젝트는 훅 실행이 맡는다.

### D6. 시각은 `configs/dream.json`의 `run_at`이고 `vg dream at HH:MM`으로 바꾼다
- by: 사람 (2026-11-24 spec gate: vg dream at (Recommended))
- status: decided
- area: settings, cli
- basis: D1, X1
- depends: I5

`run_at`은 두 자리 시(00~23), 콜론, 두 자리 분(00~59)이다. 파일에 이 형식이 아닌 값이 있으면 다른 키처럼 파일 전체가 `broken`(꺼짐)이다. `vg dream at`에 잘못된 값을 주면 거부하고 파일을 바꾸지 않는다. 켜져 있으면 저장 뒤 스케줄을 다시 설치하고, 꺼져 있으면 저장만 한다. 키가 없는 기존 파일은 01:00으로 읽는다(I5). 현지 시각의 뜻은 launchd가 쓰는 시스템 시간대다.

### D7. 시각 실행은 24시간 간격 검사를 건너뛴다
- by: 사람 (2026-11-24 spec gate: 건너뛴다 (Recommended))
- status: decided
- area: schedule-run
- basis: X2

시각 실행은 그날의 정기 실행이므로, 전날 밤 훅 실행이 있었어도 돈다. 켜짐, 대기 한도, 실행 조건은 지킨다. 결과: 시각 실행이 `run` 줄을 남기므로 그 프로젝트의 훅 실행은 그 뒤 24시간 동안 간격에 막힌다(X2). 그래서 시각 실행을 설치하면 훅 실행은 사실상 시각 실행이 건너뛴 프로젝트나 실패한 프로젝트에서만 돈다.

### D8. 잠금이 잡혀 있으면 30분까지 기다리고, 넘으면 그 프로젝트를 건너뛴다
- by: 사람 (2026-11-24 spec gate: 30분까지 기다린다 (Recommended))
- status: decided
- area: schedule-run
- basis: X6

01:00에 잠금을 잡고 있는 것은 대개 늦게 끝난 세션의 훅 실행이다. 판단 한 번의 시간 제한이 600초이고 실행 한 번의 묶음 수에도 한도가 있어 그 실행은 끝난다. 바로 건너뛰면 그 프로젝트는 그날 시각 실행을 놓친다. 30분을 넘기면 `run` 줄에 `status="skipped"`, `reason="locked"`, `trigger="schedule"`로 적고 다음 프로젝트로 간다. 이 줄은 간격 계산에서 `pending_cap`처럼 빼서 훅 실행을 막지 않는다.


### D9. `vg dream status`가 실행 시각, 스케줄 상태, 마지막 시각 실행을 보인다
- by: 사람 (2026-11-24 spec gate: 더한다 (Recommended))
- status: decided
- area: cli
- basis: X9, D12

`status`에 세 줄을 더한다. `run_at: HH:MM (local)`. `schedule: installed|not_installed|stale|unsupported` 뒤에 plist 경로나 이유. `last_scheduled_run: <at>`(`trigger="schedule"`인 마지막 `run` 줄의 시각, 없으면 `-`). 켜져 있는데 `not_installed`나 `stale`이면 "run `vg dream on` to install it" 안내를 붙인다. `stale`은 plist는 있지만 그 안의 Python 경로가 없거나 시각이 `run_at`과 다를 때다.

### D10. 시각 실행은 프로젝트 루트를 cwd로 쓴다
- by: 사람 (2026-11-24 spec gate: Approve, 가정을 적힌 대로 승인)
- status: decided
- area: schedule-run
- basis: X3, X8

`run_scheduled_dreams`는 vault-map `root`를 `run_dream`의 `cwd`로 넘기고, `ClaudeDreamJudge`가 `subprocess.run(cwd=root)`로 `claude -p`를 띄우게 한다. 판단 명령의 작업 폴더가 사라졌다는 이유로 실패하지 않게 하려는 것이다. 훅 실행의 cwd는 바꾸지 않는다(Non-goals).

### D11. plist는 설치한 순간의 Python과 환경을 적는다
- by: 사람 (2026-11-24 spec gate: Approve, 가정을 적힌 대로 승인)
- status: decided
- area: schedule-port
- basis: X4

`ProgramArguments`는 `sys.executable -c <작업자 스크립트> dream scheduled --graph-home <Graph Home>`이다. 작업자 스크립트는 `start_dream_worker`가 쓰는 것과 같다. `EnvironmentVariables`에는 설치한 프로세스의 `PATH`, `HOME`, 그리고 있으면 `VAULT_GRAPH_VAULT_MAP`, `CLAUDE_CONFIG_DIR`을 적는다. `claude`를 PATH에서 찾기 때문이다(X4). 출력은 Graph Home `logs/dream-schedule.log`로 보낸다. Label은 `io.vault-graph.dream.<Graph Home 절대 경로 sha256 앞 8자>`이고, 그래서 Graph Home마다 plist가 하나다.

### D12. `run` 줄에 `trigger`를 적는다
- by: 사람 (2026-11-24 spec gate: 더한다 (Recommended), status 질문에서 실행 길 기록과 함께 승인)
- status: decided
- area: worker
- basis: X10
- depends: D7, D8

`run` 줄에 `trigger`(`hook`, `manual`, `schedule`)를 더한다. `trigger`가 없는 옛 줄은 지금처럼 읽고, 시각 실행이 아닌 것으로 본다. 간격 계산은 `trigger`를 보지 않는다(D7, D8의 `locked`만 뺀다).

### D13. 스케줄 설치에 실패하면 설정은 저장하고 종료 코드 1로 알린다
- by: 사람 (2026-11-24 spec gate: 실패로 끝낸다 (Recommended))
- status: decided
- area: cli
- basis: D4

`vg dream on`이나 `vg dream at`에서 plist 쓰기나 `launchctl`이 실패하면 설정 파일은 이미 저장된 채로 두고, "schedule: not installed: <이유>"와 "hook runs still work"를 출력하고 1로 끝난다. `vg dream off`에서 `bootout`이 "올라가 있지 않음"으로 실패하면 성공으로 본다. macOS가 아닌 플랫폼은 실패가 아니므로 0으로 끝난다.

## 6. Failure and boundary behavior

시각 실행 하나의 출력은 `logs/dream-schedule.log`에 남고, 프로젝트 판단 결과는 지금처럼 `logs/dream-runs.jsonl`의 `run` 줄에 남는다.

### F1. 등록된 루트 폴더가 없다
- basis: D3

`root`가 비었거나 그 폴더가 없는 프로젝트는 `run_dream`을 부르지 않는다. 시각 실행 로그에 "skipped <project>: root missing <path>" 한 줄을 쓰고 다음 프로젝트로 간다. `run` 줄은 쓰지 않는다.

### F2. 루트는 있지만 프로젝트로 찾아지지 않거나 쓰기 Vault가 없다
- basis: D3, X5

루트가 git 저장소가 아니거나, 다른 프로젝트와 겹쳐 `find_project`가 정하지 못하거나, 쓰기 Vault가 없으면 `run_dream`이 지금처럼 `no_project` 또는 `no_write_vault`로 건너뛴다. 시각 실행은 그 결과를 로그에 적고 다음 프로젝트로 간다.

### F3. 잠금이 30분 넘게 잡혀 있다
- basis: D8

그 프로젝트는 `reason="locked"` `run` 줄을 남기고 건너뛴다. 다음 프로젝트는 다시 30분까지 기다린다. 이 줄은 훅 실행의 간격 계산에 들어가지 않는다.

### F4. 드리밍이 꺼졌는데 launchd가 시각 실행을 부른다
- basis: D4, I4

`vg dream off`가 plist 제거에 실패했거나 사용자가 파일을 손으로 고친 경우다. `vg dream scheduled`는 설정이 꺼짐이나 `broken`이면 "dream: skipped off" 한 줄만 쓰고 0으로 끝난다. 아무 프로젝트도 판단하지 않는다.

### F5. macOS가 아니다
- basis: D4, D13

`vg dream on`은 설정을 저장하고 "schedule: unsupported on <플랫폼>"을 출력하고 0으로 끝난다. `vg dream at`은 시각만 저장한다. `status`는 `schedule: unsupported`를 보인다.

### F6. plist 쓰기나 launchctl이 실패한다
- basis: D13

설정은 저장된 채로 두고, 실패 이유를 출력하고 1로 끝난다. 다음 `vg dream on`이 다시 설치를 시도한다.

### F7. 기존 설정 파일에 `run_at`이 없다
- basis: D6, I5

01:00으로 읽고 켜짐과 한도는 파일 값대로 쓴다. 다음 저장 때 `run_at`이 파일에 들어간다.

### F8. `run_at` 값이 잘못됐다
- basis: D6

파일 안의 값이 "HH:MM" 형식이 아니거나 범위를 넘으면(예: "1:00", "24:00", "01:60", 숫자 1) 파일 전체가 `broken`이고 드리밍은 꺼짐으로 읽힌다. 시각 실행도 꺼져 있을 때처럼 아무것도 판단하지 않고 끝난다. `vg dream at`에 같은 값을 주면 이유를 출력하고 1로 끝나며 파일은 그대로다.

### F9. 드리밍이 꺼진 상태에서 시각을 바꾼다
- basis: D6

`vg dream at`은 `run_at`만 저장하고 스케줄은 설치하지 않는다. 다음 `vg dream on`이 그 시각으로 설치한다.

### F10. plist의 Python 경로가 사라졌다
- basis: D9, D11

uv tool 재설치나 가상 환경 삭제로 plist에 적힌 Python이 없어지면 launchd 실행이 시작부터 실패하고 vg는 그 사실을 알 수 없다. `status`가 `schedule: stale`과 재설치 안내를 보인다.

### F11. 시각 실행에서 `claude`를 찾지 못하거나 판단이 실패한다
- basis: D10, D11

`run_dream`이 지금처럼 `failed` `run` 줄을 남기고, 시각 실행은 다음 프로젝트로 간다. 실패한 프로젝트는 지금 규칙대로 1시간 뒤 훅 실행이 다시 시도할 수 있다.

### F12. 한 프로젝트에서 예상하지 못한 오류가 난다
- basis: D3

한 프로젝트에서 난 오류는 종류와 상관없이(`VaultGraphError`, `OSError`, 그 밖의 예외) 그 프로젝트 이름과 함께 로그에 적고 다음 프로젝트로 간다. 그래서 id 순서상 뒤에 있는 프로젝트가 한 프로젝트의 오류 때문에 그날 빠지지 않는다. 시각 실행 전체는 한 프로젝트라도 오류가 났으면 1로 끝난다. (2026-11-24 PR 리뷰 뒤 사람이 넓힘)

### F13. 이미 드리밍을 켜 둔 사용자가 업그레이드한다
- basis: D4, D9

업그레이드만으로는 plist가 생기지 않는다. `status`가 `schedule: not_installed`와 "run `vg dream on` to install it"을 보인다. 그 전까지는 훅 실행만 돈다.

### F14. 그 시각에 Mac이 잠들어 있거나 꺼져 있다
- basis: D5

잠들어 있었으면 깨어난 뒤 한 번 돈다. 꺼져 있었으면 그날은 돌지 않는다. vg는 놓친 실행을 메우지 않는다.


## 7. What could be wrong

아래는 이 spec 작업에서 실행해 보지 않은 것이다. launchd 동작은 `man launchd.plist`와 실제 Mac에서 확인해야 한다.

### R1. launchd가 잠든 동안 놓친 시각을 깨어난 뒤 돌린다는 전제
- basis: D5

launchd 문서에 그렇게 적혀 있다고 알고 있지만 이 작업에서 man 페이지를 열거나 실제로 재워 보지 않았다. 틀리면 노트북을 덮어 두는 사용자는 시각 실행이 거의 돌지 않는다.

### R2. `launchctl bootstrap`/`bootout`이 이 macOS 버전에서 그대로 동작한다는 전제
- basis: D4

Darwin 27에서 두 하위 명령과 `gui/<uid>` 도메인을 확인하지 않았다. 틀리면 설치 명령을 `load -w`/`unload`로 바꿔야 한다.

### R3. `StartCalendarInterval`이 시간대 변경과 일광 절약 시간을 따라간다는 전제
- basis: D4, D6

여행으로 시간대를 바꾸면 새 현지 시각 01:00에 돈다고 가정했다. 확인하지 않았다.

### R4. launchd에서 띄운 `claude -p`가 사용자 로그인으로 인증된다는 전제
- basis: D11, X4

`claude`가 로그인 정보를 Keychain에서 읽는다면, LaunchAgent 작업에서 Keychain을 열 수 있는지 확인하지 않았다. 틀리면 모든 시각 실행이 `judge_unavailable`로 실패하고, 이것은 실제 실행으로만 알 수 있다.

### R5. 로그인 셸의 PATH가 아닌 설치 프로세스의 PATH로 충분하다는 전제
- basis: D11

`vg dream on`을 Claude Code 훅이나 IDE 터미널에서 부르면 PATH가 셸과 다를 수 있다. 그 PATH에 `claude`가 없으면 시각 실행마다 판단 명령을 찾지 못해 실패한다.

### R6. 등록 프로젝트 수와 그 비용
- basis: D3

vault-map.json을 이 작업에서 열지 않아 등록 프로젝트 수를 모른다. 실행 조건과 대기 한도가 대부분의 프로젝트를 건너뛰게 하겠지만, 프로젝트 수 × 실행당 비용(수동 실행 기준 $0.40~$0.57)이 하루에 쓰일 수 있다.


## 8. Acceptance criteria

모든 테스트는 CI 명령(`.github/workflows/ci.yml`의 ruff, mypy, pytest)과 함께 통과해야 한다.

### A1. 설정 파일이 `run_at`을 읽고 쓴다
- covers: D1, D6, I5, F7, F8
- check: tests/test_dream_settings.py
- evidence: tests/test_dream_settings.py: test_missing_file_runs_at_one_in_the_morning, test_a_version_1_file_without_run_at_still_reads_from_the_file, test_a_valid_run_at_is_read_from_the_file, test_a_bad_run_at_breaks_the_whole_file, test_saving_always_writes_run_at_with_version_1 (bake-verify.log: 4036 passed, 22 skipped)

없는 파일은 `run_at="01:00"`이다. `run_at`이 없는 버전 1 파일은 `source="file"`, 01:00이고 `enabled`와 한도는 파일 값이다. "00:00", "23:59"는 받는다. "1:00", "24:00", "01:60", 숫자 1, 빈 문자열은 `broken`이다. 저장한 파일에는 언제나 `run_at`이 있다.

### A2. `vg dream at`이 시각을 검사하고 저장한다
- covers: D6, F8, F9
- check: tests/test_cli_dream_schedule.py
- evidence: tests/test_cli_dream_schedule.py: test_at_saves_the_time_and_reinstalls_when_dreaming_is_on, test_at_only_saves_while_dreaming_is_off, test_at_refuses_a_bad_time_and_leaves_the_file

가짜 스케줄로: 켜져 있으면 저장 뒤 새 시각으로 설치를 한 번 부른다. 꺼져 있으면 저장만 하고 설치를 부르지 않는다. 잘못된 값은 1로 끝나고 파일 바이트가 그대로다.

### A3. launchd 구현이 plist를 쓰고 올리고 내린다
- covers: D4, D11, I6
- check: tests/test_dream_schedule.py
- evidence: tests/test_dream_schedule.py: test_install_writes_the_plist_then_bootstraps, test_install_again_boots_out_first, test_remove_boots_out_then_deletes_the_plist, test_label_carries_the_graph_home_hash, test_default_folder_is_the_user_launch_agents_and_tests_never_touch_it

임시 LaunchAgents 폴더와 기록만 하는 `launchctl` 함수로: 설치하면 plist의 `Hour`/`Minute`가 `run_at`과 같고, `ProgramArguments`는 `sys.executable`과 `dream scheduled --graph-home <경로>`를 담고, `EnvironmentVariables`에 `PATH`와 `HOME`이 있고, Label에 Graph Home 해시가 붙고, 출력 경로가 `logs/dream-schedule.log`다. 이어서 `bootstrap`을 부른다. 다시 설치하면 먼저 `bootout`한다. 제거하면 `bootout` 뒤 파일이 없다. 테스트는 `$HOME/Library/LaunchAgents`를 건드리지 않는다.

### A4. macOS가 아니면 설치하지 않는다
- covers: D4, F5
- check: tests/test_cli_dream_schedule.py
- evidence: tests/test_cli_dream_schedule.py: test_off_macos_on_saves_and_reports_unsupported_with_0, tests/test_dream_schedule.py: test_other_platforms_are_unsupported_and_touch_nothing

플랫폼을 "linux"로 주면 `vg dream on`은 설정을 저장하고 "schedule: unsupported on linux"를 출력하고 0으로 끝난다. plist 파일도 `launchctl` 호출도 없다.

### A5. 설치 실패는 설정을 남기고 1로 끝난다
- covers: D13, F6
- check: tests/test_cli_dream_schedule.py
- evidence: tests/test_cli_dream_schedule.py: test_a_failed_install_keeps_the_settings_and_ends_with_1, tests/test_dream_schedule.py: test_remove_counts_not_loaded_as_success, test_a_plist_that_cannot_be_written_is_reported_not_raised, test_a_plist_that_cannot_be_deleted_after_a_failed_bootstrap_is_reported_not_raised

`launchctl`이 실패하는 가짜로 `vg dream on`을 부르면 `enabled=true`가 저장되고, "schedule: not installed"가 출력되고, 1로 끝난다. `off`에서 "올라가 있지 않음" 실패는 0이다.

### A6. 시각 실행이 루트가 있는 프로젝트를 차례로 돈다
- covers: D3, I1, F1, F2, F12
- check: tests/test_dream_schedule_run.py
- evidence: tests/test_dream_schedule_run.py: test_every_project_runs_once_in_turn_from_its_root_as_a_scheduled_run, test_a_missing_or_empty_root_is_skipped_without_a_run_line, test_skipped_and_failed_runs_go_on_to_the_next_project, test_an_error_in_one_project_is_logged_and_the_run_ends_with_1, test_any_other_error_in_one_project_is_logged_and_the_rest_still_run

프로젝트 셋(루트 있음, 루트 없음, git 아닌 루트)과 가짜 `run_dream`으로: id 순서로, 루트가 있는 둘에 대해서만 한 번씩 불리고, 동시에 둘이 불리지 않는다. 루트 없는 프로젝트는 로그 한 줄로 끝난다. 첫 프로젝트에서 `OSError`가 나도 다음 프로젝트가 불리고 전체는 1로 끝난다.

### A7. 시각 실행은 간격만 건너뛰고 나머지 조건은 지킨다
- covers: D7, D12, I4, F4
- check: tests/test_dream_worker.py, tests/test_dream_schedule_run.py
- evidence: tests/test_dream_worker.py: test_the_scheduled_run_skips_only_the_interval, test_the_scheduled_run_keeps_off_the_pending_cap_and_the_due_check, tests/test_dream_schedule_run.py: test_off_or_broken_settings_judge_nothing

한 시간 전에 `run` 줄이 있어도 `trigger="schedule"`은 판단한다. 꺼짐, 대기 한도, 실행 조건 미달에서는 판단하지 않는다. `run` 줄에 `trigger="schedule"`이 적힌다. 설정이 꺼짐이거나 `broken`이면 `vg dream scheduled`는 아무 프로젝트도 판단하지 않고 0으로 끝난다.

### A8. 훅 실행은 바뀌지 않는다
- covers: D2, I3
- check: tests/test_hook_dream.py, tests/test_dream_worker.py
- evidence: tests/test_hook_dream.py (기존 테스트 통과, bake-verify.log: 4036 passed), tests/test_dream_worker.py: test_a_hook_run_waits_out_the_interval_after_a_scheduled_run

기존 훅 테스트가 그대로 통과한다. `trigger="hook"` 실행은 시각 실행이 남긴 한 시간 전 `run` 줄 때문에 `interval`로 건너뛴다. 훅 실행의 `run` 줄에 `trigger="hook"`이 적힌다.

### A9. 잠금을 기다리고 시간이 넘으면 건너뛴다
- covers: D8, I1, F3
- check: tests/test_dream_schedule_run.py
- evidence: tests/test_dream_schedule_run.py: test_a_lock_freed_within_the_wait_lets_the_project_run, test_a_lock_held_past_the_wait_leaves_a_locked_line_and_moves_on, tests/test_dream_worker.py: test_a_locked_line_does_not_start_the_interval

기다림 한도를 짧게 주고 잠금을 다른 프로세스가 잡은 상태에서: 한도 안에 풀리면 그 프로젝트가 돈다. 넘으면 `reason="locked"` `run` 줄이 남고 다음 프로젝트로 간다. 그 줄 뒤에도 훅 실행은 간격에 막히지 않는다.

### A10. 시각 실행의 판단 명령은 프로젝트 루트에서 돈다
- covers: D10, I2, F11
- check: tests/test_dream_judge.py, tests/test_dream_schedule_run.py
- evidence: tests/test_dream_judge.py: test_claude_runs_in_the_given_folder_and_otherwise_inherits_it, tests/test_dream_schedule_run.py: test_every_project_runs_once_in_turn_from_its_root_as_a_scheduled_run, test_skipped_and_failed_runs_go_on_to_the_next_project

`ClaudeDreamJudge(cwd=root)`는 `subprocess.run`에 `cwd=root`를 넘긴다. 시각 실행이 각 프로젝트에 넘기는 cwd는 vault-map의 `root`다. 판단 명령이 없으면(`OSError`) 그 프로젝트는 `failed`가 되고 다음 프로젝트가 돈다.

### A11. `status`가 실행 시각과 스케줄 상태를 보인다
- covers: D9, D12, F10, F13
- check: tests/test_cli_dream_schedule.py
- evidence: tests/test_cli_dream_schedule.py: test_status_shows_run_at_and_an_installed_schedule, test_status_tells_an_upgraded_user_to_install_the_schedule, test_status_shows_a_stale_schedule_when_the_time_differs, test_status_shows_unsupported_off_macos, test_status_shows_the_last_scheduled_run_only

`run_at: 01:00 (local)`이 나온다. 가짜 스케줄 상태마다 `schedule: installed`, `not_installed`, `stale`, `unsupported`가 나오고, 켜져 있는데 `not_installed`나 `stale`이면 재설치 안내가 붙는다. `trigger="schedule"` 줄이 있으면 `last_scheduled_run`에 그 시각이, 없거나 `trigger` 없는 옛 줄뿐이면 `-`가 나온다.

### A12. 실제 Mac에서 정해진 시각에 돈다
- covers: D4, D5, F14
- check: 수동: macOS에서 `vg dream on` 뒤 `vg dream at`을 2분 뒤 시각으로 바꾸고 기다린 다음, 같은 확인을 Mac을 그 시각 전후로 재워서 한 번 더 한다
- evidence: 수동: macOS에서 `vg dream on`을 실행하고 `vg dream at`을 2분 뒤 시각으로 바꾼 다음 기다린다. `logs/dream-runs.jsonl`에 `trigger="schedule"` 줄이 프로젝트마다 생기고 각 줄의 cwd가 vault-map의 루트인지 본다. 그 시각 전후로 Mac을 재워서 한 번 더 확인한다. 마지막으로 `vg dream off`를 실행하고 `launchctl list`에 그 Label이 없는지 본다.

`logs/dream-runs.jsonl`에 `trigger="schedule"` `run` 줄이 등록 프로젝트마다 생기고, 각 줄의 `cwd`가 vault-map의 루트다. 재운 경우 깨어난 뒤 한 번 돈다. `vg dream off` 뒤 `launchctl list`에 그 Label이 없다.


## 9. Open decisions

### O1. 정해진 시각 실행을 macOS launchd로 설치할까?
- decides: D4, D11

답 (2026-11-24 spec gate): launchd.

배경: vg에는 지금 OS 스케줄러 코드가 없다. 시각 실행을 하려면 OS가 vg를 그 시각에 불러 줘야 한다.

권고: launchd LaunchAgent를 쓴다. `vg dream on`이 `$HOME/Library/LaunchAgents/`에 파일 하나를 쓰고 올리며, `off`가 지운다. 사용자 기기가 macOS이고, cron과 달리 잠든 동안 놓친 시각을 깨어난 뒤 돌린다. 설치할 때의 Python 경로와 PATH를 파일에 적어 두므로, vg를 다른 곳에 다시 설치하면 `vg dream on`을 한 번 더 해야 한다.

바뀌는 것: 다른 답(cron, 사용자가 직접 등록)이면 설치 코드와 수용 기준 셋(설치, 비 macOS, 설치 실패)이 바뀐다. Linux에서는 어느 쪽이든 시각 실행이 없다.

### O2. Mac이 그 시각에 잠들어 있었으면 어떻게 할까?
- decides: D5

답 (2026-11-24 spec gate): 깨어나면 돈다.

배경: 노트북은 01:00에 덮여 있는 일이 많다.

권고: launchd 기본 동작대로 깨어난 뒤 한 번 돈다. vg가 놓친 실행을 따로 기억하거나 메우지 않는다. 코드가 없고, 꺼져 있던 날은 훅 실행이 대신한다.

바뀌는 것: "깨어난 직후에는 돌지 않고 다음 날을 기다린다"를 고르면 마지막 실행 날짜를 보고 건너뛰는 코드가 더해진다. 그 경우 아침에 노트북을 열자마자 `claude -p`가 도는 일은 없다.

### O3. 실행 시각을 어디에 두고 어떤 명령으로 바꿀까?
- decides: D6

답 (2026-11-24 spec gate): vg dream at.

배경: 기본 01:00은 승인됐고, 사용자가 바꿀 수 있어야 한다.

권고: `configs/dream.json`에 `run_at: "HH:MM"`을 두고 `vg dream at 02:30`처럼 바꾼다. 다른 드리밍 설정과 같은 파일이고, 키가 없는 기존 파일은 01:00으로 읽어 업그레이드로 드리밍이 꺼지지 않는다.

바뀌는 것: `vg dream on --at 02:30` 같은 옵션을 고르면 명령 모양과 CLI 테스트만 바뀐다.

### O4. 시각 실행이 24시간 간격 검사를 건너뛸까?
- decides: D7

답 (2026-11-24 spec gate): 건너뛴다.

배경: 드리밍은 프로젝트마다 24시간에 한 번만 돈다. 어느 경로가 돌았든 같은 기록으로 센다.

권고: 시각 실행은 간격을 건너뛴다. 그러지 않으면 전날 밤 훅 실행이 돈 프로젝트는 01:00에 건너뛰어 "정해진 시각에 돈다"가 지켜지지 않는다. 켜짐, 대기 한도, 실행 조건은 지킨다.

바뀌는 것: 결과로 01:00에 돈 프로젝트는 그날 낮 훅 실행이 간격에 막힌다. 낮에는 거의 시각 실행만 남는다. 훅 실행도 낮에 계속 돌기를 원하면 간격을 경로마다 따로 세야 하고 판단 비용이 하루 두 배까지 늘 수 있다.

### O5. 01:00에 다른 드리밍 실행이 잠금을 잡고 있으면 어떻게 할까?
- decides: D8

답 (2026-11-24 spec gate): 30분까지 기다린다.

배경: 드리밍은 한 번에 하나만 돈다. 늦게 끝난 세션의 훅 실행이 01:00에 돌고 있을 수 있다.

권고: 30분까지 기다리고, 넘으면 그 프로젝트만 건너뛰고 기록한다. 훅 실행은 길어도 그 안에 끝나므로 대개 그날 실행을 놓치지 않는다.

바뀌는 것: "바로 건너뛴다"를 고르면 기다림 코드가 없어지지만 그 프로젝트는 그날 시각 실행을 놓친다. "끝없이 기다린다"를 고르면 멈춘 실행 하나가 나머지 프로젝트를 모두 막는다.

### O6. `vg dream status`에 무엇을 더할까?
- decides: D9, D12

답 (2026-11-24 spec gate): 더한다.

배경: 지금 `status`에는 실행 시각도, 스케줄이 설치됐는지도 없다. 실행 기록에는 어느 경로로 돈 실행인지 적히지 않는다.

권고: 실행 시각, 스케줄 상태(설치됨, 없음, 낡음, 지원 안 함), 마지막 시각 실행 시각을 보인다. 이를 위해 실행 기록 줄마다 경로(훅, 수동, 시각)를 적는다. 이미 드리밍을 켠 사용자가 업그레이드 뒤 `vg dream on`을 다시 해야 한다는 것을 여기서 알게 된다.

바뀌는 것: 줄을 빼면 사용자는 시각 실행이 실제로 도는지 `logs/dream-runs.jsonl`을 직접 열어 봐야 한다.

### O7. 스케줄 설치가 실패하면 `vg dream on`을 실패로 끝낼까?
- decides: D13

답 (2026-11-24 spec gate): 실패로 끝낸다.

배경: 설정 저장은 성공했지만 launchd 설치가 실패할 수 있다. 그래도 훅 실행은 돈다.

권고: 설정은 저장된 채로 두고, 실패 이유와 "훅 실행은 계속 돈다"를 출력하고 종료 코드 1로 끝낸다. 시각 실행이 없다는 것을 사용자가 놓치지 않게 하려는 것이다.

바뀌는 것: 0으로 끝내면 스크립트에서 `vg dream on`이 늘 성공으로 보이고, 설치 실패는 `status`로만 알 수 있다.

