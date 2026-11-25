## id

3

## title

세션 시작 회상 구획D에 추출기 줄을 넣고 수집 알림에 `auto` 문구를 더한다

## goal

서버가 꺼진 것을 모르고 지나가는 날이 없도록, 전체 회상(startup, clear, compact)을 열 때마다 지금 고를 추출기가 한 줄로 보인다(Intent의 "매 세션 보임").

## units

D10, D11, F4, F5, F6, A10, A11, A12

## files

- src/vault_graph/interface/cli/hook_commands.py
- src/vault_graph/context/pack/recall.py
- tests/test_cli_hook_session_start.py
- tests/test_session_recall.py
- tests/test_hook_facts.py
- tests/test_llama_health.py

## blockers

1

## checks

- tests/test_cli_hook_session_start.py
- tests/test_session_recall.py
- tests/test_hook_facts.py
- tests/test_llama_health.py

## done-when

- [ ] `recall(..., facts_line: str | None = None)`가 전체 회상의 구획D에서 열기 안내 다음 줄에 그 줄을 낸다. resume, fork, handoff에는 없다(A10).
- [ ] `session-start` 훅이 설정을 읽고 끝점을 0.3초 시간 제한으로 확인해 D10의 일곱 문구 중 하나를 만들어 넘긴다. 확인이 시간을 넘으면 `- facts: auto → claude`다(A10).
- [ ] 설정 파일이 깨졌으면 `- facts: off (settings broken)`이고, 고정 llama-server가 답하지 않으면 `- facts: llama-server (not answering)`이다(A10).
- [ ] D10의 일곱 문구 모두 `estimate_recall_tokens`로 15토큰 이하이고, 답하지 않는 서버에 대한 훅 확인은 0.3초 안에 끝난다(A11). 후자 테스트는 task 1이 만든 tests/test_llama_health.py에 더한다.
- [ ] 수집 알림 표에 D11의 `auto` 문구가 있다(A12).
- [ ] 훅 경로가 `llama_health`만 쓰고 추출기 모듈과 `fact_worker`를 import하지 않는다. task 1의 A8 테스트가 계속 통과한다.
