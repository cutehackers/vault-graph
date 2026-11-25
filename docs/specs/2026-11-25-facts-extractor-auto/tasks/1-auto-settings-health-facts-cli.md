## id

1

## title

`auto` 값, `/health` 확인 함수, `vg facts on|off|status`를 만든다

## goal

설정 파일이 없을 때 `auto`가 되고, 끝점이 답하는지 가려서 llama-server 또는 claude로 바꿔 줄 수 있다. 사용자는 `vg facts status`로 지금 어느 추출기를 쓰는지 볼 수 있다(Intent의 "기본 로컬, 아니면 claude", "설정이나 명령어로 변경", "볼 수 있어야 한다").

## units

D4, D5, D7, D8, D9, I4, F9, A4, A7, A8, A9

## files

- src/vault_graph/operation/scope/facts_settings.py
- src/vault_graph/interface/composition/adapters/llama_health.py
- src/vault_graph/interface/composition/adapters/fact_extractor_selection.py
- src/vault_graph/interface/cli/facts_commands.py
- tests/test_facts_config.py
- tests/test_llama_health.py

## blockers

없음

## checks

- tests/test_facts_config.py
- tests/test_llama_health.py

## done-when

- [ ] 파일이 없으면 켜진 `auto`, 로컬 끝점, 로컬 모델이다. `auto` 파일의 `endpoint`가 null이거나 http(s)가 아니면 깨진 파일이다(A4).
- [ ] `resolve_facts_settings`가 답하면 llama-server 설정을, 아니면 claude와 `CLAUDE_FACTS_MODEL`을 돌려준다(A4).
- [ ] 끝점 확인은 200만 참이다. 503, 연결 거부, 시간 초과는 거짓이다(A7).
- [ ] 새 하위 프로세스에서 `hook_commands`, `facts_commands`, `llama_health`를 import해도 `sys.modules`에 두 추출기 모듈과 `fact_worker`가 없다(A8).
- [ ] `on`과 `off`는 파일이 없을 때 `auto`를 저장하고 `on --extractor auto|llama-server|claude`가 그 값을 저장한다(A9).
- [ ] `status`는 `extractor_now`와 `last_job` 줄을 낸다. 기록 파일이 없으면 `last_job: none`, 깨졌으면 `last_job: unreadable`이다(A9).
- [ ] `vg facts status`의 끝점 확인 시간 제한은 1초다(D5).
- [ ] 수동: llama-server를 켠 상태에서 `/health`가 200을 주는지(모델을 읽는 중에는 503인지) 한 번 확인하고 결과를 spec R2에 남긴다.
