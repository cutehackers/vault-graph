# 4. scheduled-run-all-projects

## id
4

## title
시각 실행 `run_scheduled_dreams`와 `VaultMap.projects`를 만든다

## goal
정해진 시각에 등록 프로젝트 전체를 한 번에 하나씩, 각 프로젝트 루트를 cwd로 돈다. 잠금은 30분까지 기다린다.

## units
D3, D8, D10, I1, F1, F2, F3, F4, F11, F12, A6, A7, A9, A10

## files
- src/vault_graph/operation/integration/vault_map.py
- src/vault_graph/interface/composition/adapters/dream_scheduled_run.py
- tests/test_dream_schedule_run.py

## blockers
3

## checks
- tests/test_dream_schedule_run.py

## done-when
- [ ] `VaultMap.projects`가 id 순서의 `MappedProject` 튜플을 낸다. 다른 속성은 바뀌지 않는다
- [ ] `run_scheduled_dreams`는 설정이 꺼짐이거나 `broken`이면 "dream: skipped off" 한 줄만 쓰고 0으로 끝난다
- [ ] 프로젝트를 id 순서로, 한 번에 하나씩 돈다. 프로젝트마다 `logs/dream-worker.lock`을 non-blocking flock으로 폴링하며 잡고(`run_dream_locked`는 잠금이 잡혀 있으면 바로 None을 내므로, 잡은 descriptor를 `lock_fd`로 넘긴다), `trigger="schedule"`로 `run_dream_locked`를 부른다
- [ ] 판단 명령의 cwd(task 3의 `judge_cwd`)와 `run_dream`의 cwd로 vault-map `root`를 넘긴다
- [ ] 루트가 비었거나 폴더가 없으면 "skipped <project>: root missing <path>" 한 줄만 쓰고 `run` 줄은 없다
- [ ] git 아닌 루트와 쓰기 Vault 없음은 `run_dream`의 건너뜀 결과를 로그에 적고 다음으로 간다
- [ ] 잠금 대기 한도는 30분이고 테스트에서 짧게 줄 수 있다. 한도 안에 풀리면 돌고, 넘으면 task 3의 공개 함수로 `locked` `run` 줄을 남기고 다음 프로젝트로 간다
- [ ] `locked` 줄 뒤에도 훅 실행이 간격에 막히지 않는다
- [ ] `claude`가 없는 `OSError`는 그 프로젝트가 `failed`가 되고 다음으로 간다
- [ ] `VaultGraphError`와 `OSError`는 프로젝트 이름과 함께 로그에 적고 다음으로 간다. 한 프로젝트라도 오류가 났으면 전체는 1로 끝난다
- [ ] 설정이 꺼진 경우에 어떤 프로젝트도 판단하지 않는다(A7)
