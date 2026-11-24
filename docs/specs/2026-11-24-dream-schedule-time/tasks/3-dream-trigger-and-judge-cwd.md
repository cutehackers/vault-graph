# 3. dream-trigger-and-judge-cwd

## id
3

## title
`run_dream`의 `manual`을 `trigger`로 바꾸고 `run` 줄에 적고 판단 명령에 cwd를 넘긴다

## goal
실행 경로(hook, manual, schedule)를 구분하고, schedule은 간격 검사만 건너뛴다. 판단 명령이 프로젝트 루트에서 돌 수 있게 한다.

## units
D2, D7, D12, I2, I3, I4, A7, A8, A10

## files
- src/vault_graph/interface/composition/adapters/dream_worker.py
- src/vault_graph/interface/composition/adapters/claude_dream_judge.py
- src/vault_graph/interface/cli/dream_commands.py
- tests/test_dream_worker.py
- tests/test_dream_judge.py

## blockers
none

## checks
- tests/test_dream_worker.py
- tests/test_dream_judge.py
- tests/test_hook_dream.py

## done-when
- [ ] `run_dream`과 `run_dream_locked`가 `trigger: Literal["hook","manual","schedule"]`을 받고, `manual: bool`은 없어진다
- [ ] `schedule`은 간격 검사만 건너뛰고 켜짐, 대기 한도, 실행 조건은 지킨다. `manual`의 기존 동작은 그대로다
- [ ] `run` 줄에 `trigger`를 적는다. `trigger`가 없는 옛 줄은 지금처럼 읽고, 시각 실행이 아닌 것으로 본다
- [ ] `reason="locked"`, `trigger="schedule"` 줄을 `_ran_recently`의 간격 계산에서 `pending_cap`처럼 뺀다
- [ ] 잠금 때문에 건너뛴 프로젝트의 `locked` `run` 줄을 남기는 공개 함수가 있다. 지금 `_log_run`은 `DreamRun`과 vault를 받으므로, 쓰기 Vault를 찾지 못하는 경우도 task 4가 부를 수 있게 서명을 정한다
- [ ] `_WORKER_SCRIPT`를 공개 이름으로도 내보낸다(지금은 `dream_worker.py:134`의 비공개 상수). task 5가 쓴다
- [ ] `ClaudeDreamJudge`가 선택 인자 `cwd`를 받고(지금 `__init__`은 `model`, `timeout_seconds`뿐), 지정하면 `subprocess.run(cwd=...)`로 넘긴다. 지정하지 않으면 지금처럼 cwd를 정하지 않는다
- [ ] `open_dream_ports`는 이미 `cwd`를 받지만 후보 수집에만 쓴다. 판단 명령의 cwd는 훅 실행이 바뀌지 않도록 별도 선택 인자(예: `judge_cwd`)로 받고, 기본은 지정 안 함이다
- [ ] `dream_commands.py`는 `manual=` 호출(105행, 116행 부근)을 `trigger="manual"`과 `trigger="hook"`으로 바꾸는 것과 `_run`의 `manual` 분기 정리만 한다. `hook_commands.py`는 쓰지 않는다
- [ ] 기존 `tests/test_hook_dream.py`가 고치지 않고 통과한다. `trigger="hook"`은 시각 실행이 남긴 한 시간 전 `run` 줄 때문에 `interval`로 건너뛴다
