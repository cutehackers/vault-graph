# 조사: 드리밍 실행 경로의 지금 코드

2026-11-24, branch `bake/dream-schedule-time`(커밋 `bb07019`)에서 코드를 읽고 grep으로 확인했다.

### X1. 설정 파일의 키 집합이 닫혀 있다
- source: src/vault_graph/operation/scope/dream_settings.py:36-37, 137-158

`_KEYS`는 `version`, `enabled`, `model`과 한도 다섯 개다. `_settings_from_payload`는 모르는 키도, 빠진 키도 `CatalogError`로 거부하고, `read_dream_settings`는 그 파일을 `broken`(꺼짐)으로 읽는다. 그래서 `run_at` 키를 그냥 더하면 그 키가 없는 기존 파일은 꺼짐으로 읽힌다. 파일 크기 상한은 4096 bytes다(35행).

### X2. 실행 조건과 24시간 간격 검사
- source: src/vault_graph/interface/composition/adapters/dream_worker.py:294-310, 374-384

`run_dream`은 `manual=False`일 때 켜짐 여부와 `_ran_recently`를 본다. `_ran_recently`는 그 프로젝트의 `run` 줄 가운데 `pending_cap`이 아닌 마지막 줄의 시각을 `interval_hours`(실패면 1시간)와 비교한다. 대기 한도는 언제나 보고, 실행 조건(`_is_due`)은 `manual`이면 건너뛴다. 어느 경로가 남긴 `run` 줄이든 같은 간격 계산에 들어간다.

### X3. 작업자와 판단 명령은 cwd를 지정하지 않는다
- source: src/vault_graph/interface/composition/adapters/dream_worker.py:824-832, src/vault_graph/interface/composition/adapters/claude_dream_judge.py:240-250

`start_dream_worker`의 `subprocess.Popen`에도, `ClaudeDreamJudge.judge`의 `subprocess.run`에도 `cwd=` 인자가 없다. 그래서 `claude -p`는 훅을 부른 프로세스의 작업 폴더를 물려받는다.

### X4. 판단 명령은 PATH에서 `claude`를 찾는다
- source: src/vault_graph/interface/composition/adapters/claude_dream_judge.py:37, 221-234, 205-209

명령 첫 단어는 `CLAUDE_COMMAND = "claude"`이고 절대 경로가 아니다. 자식 환경은 지금 환경에서 `ANTHROPIC_API_KEY`만 빼고 `VAULT_GRAPH_FACTS_CHILD=1`을 더한다.

### X5. vault-map은 프로젝트 목록을 밖으로 내주지 않는다
- source: src/vault_graph/operation/integration/vault_map.py:45-50, 86, 112-125, 316-325

`MappedProject`는 `project_id`, `root`, `vault_names`, `remote`, `default_write_vault`를 가진다. `VaultMap`은 프로젝트를 `_projects`에 두고, 밖에서는 `default_write_vaults`로 id만 보인다. `find_project(cwd)`는 먼저 git 주 worktree 루트를 구하고, git 저장소가 아니면 프로젝트 없음으로 답한다.

### X6. 수집 훅이 작업자를 띄우는 길
- source: src/vault_graph/interface/cli/hook_commands.py:454-456, 501-527

written 수집 뒤 `_start_dream`이 Graph Home 초기화와 켜짐을 확인하고, 훅 JSON의 `cwd`로 `start_dream_worker`를 부른다. 잠금이 잡혀 있으면 띄우지 않는다.

### X7. vg에는 OS 스케줄러 코드가 없다
- source: 저장소 전체 grep `launchd|launchctl|LaunchAgents|StartCalendarInterval|crontab|systemd`

맞는 파일은 `tests/fixtures/eval_layer2/vault/wiki/workflows/restore-homelab-data-from-restic.md` 하나뿐이고, 이것은 평가용 Vault 페이지다. `src/`에는 없다.

### X8. 지워진 worktree를 cwd로 쓴 실행이 실패했다
- source: brief (2026-11-24, 사용자 관찰)

981park-flutter-app 프로젝트의 마지막 드리밍 실행은 지워진 worktree를 cwd로 썼고, `claude -p`가 "current directory no longer exists"로 실패했다. 이 spec 작업에서 `logs/dream-runs.jsonl`을 직접 열어 보지는 않았다.

### X9. 지금 `vg dream` 명령과 `status` 출력
- source: src/vault_graph/interface/cli/dream_commands.py:57-116, 174-249

명령은 `on`, `off`, `status`, `run`, 숨은 `worker`다. `on`/`off`는 `_set_enabled`로 저장된 모델과 한도를 지키고 `enabled`만 바꾼다. `status`는 켜짐, 모델, 한도, 설정 파일 출처, 프로젝트별 마지막 실행, 제안 상태, 대기 한도 멈춤을 보인다. 실행 시각이나 스케줄 줄은 없다.

### X10. `run` 줄에는 실행 경로가 적히지 않는다
- source: src/vault_graph/interface/composition/adapters/dream_worker.py:740-763

`_log_run`은 `at`, `project`, `cwd`, `vault`, `status`, `reason`, `judged`, `cost_usd` 등을 적지만, 훅 실행인지 `vg dream run`인지는 적지 않는다.
