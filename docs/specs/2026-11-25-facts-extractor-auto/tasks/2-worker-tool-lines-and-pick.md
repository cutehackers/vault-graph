## id

2

## title

`fact_worker.py`에서 도구 호출 줄을 거르고 `auto`를 작업마다 풀어 실제 값을 캐시·첨부·마지막 작업 기록에 쓴다

## goal

같은 part의 프롬프트가 줄어도 사실 수는 그대로이고(3d), `auto`가 켜져 있으면 서버가 켜진 날은 로컬, 꺼진 날은 claude로 추출하며 첨부에 실제로 쓴 값이 남는다(3e).

## units

D1, D2, D3, D6, I1, I2, I3, F1, F2, F3, F7, F8, A1, A2, A3, A5, A6, A13

## files

- src/vault_graph/interface/composition/adapters/fact_worker.py
- tests/test_fact_worker.py

## blockers

1

## checks

- tests/test_fact_worker.py
- tests/test_facts_config.py
- 수동: 도구 호출 줄이 있는 실제 v2 part를 필터 없이 한 번, 필터와 함께 한 번 claude 추출기로 뽑아 프롬프트 바이트와 사실 수를 비교한다(A3)
- 수동: llama-server를 끈 채 세션 하나를 수집하고 `vg facts status`와 새 `.facts.md`를 본 뒤, 서버를 켜고 같은 일을 다시 한다(A13)

## done-when

- [ ] `_exchanges`가 메타 `tools=`에서 이름 집합을 모으고, `strip_tool_name_lines`가 assistant 구획에서 `- <이름>`, `- <이름> <인자…>` 줄(실패 표시 줄 포함) 중 메타에 있는 이름만 지운다. user 구획 줄, 메타에 없는 이름, 이름 뒤에 글자가 바로 이어지는 줄, 사용자 글머리표, 문장 중간 `Tools:`는 남는다(A1).
- [ ] 가짜 추출기가 받은 프롬프트 바이트가 필터 전보다 작고, 교환 id 목록, 첨부 사실 수, 캐시 키(원문 해시)는 그대로다. 도구 줄뿐인 교환은 추출기에 가지 않고 빈 목록으로 캐시된다. 캐시를 놓친 교환이 모두 비면 추출기를 부르지 않는다(A2).
- [ ] `auto` 작업마다 캐시를 보기 전에 끝점을 확인한다(작업자 시간 제한 2초). 답하면 캐시 키와 첨부 입력이 `llama-server`와 로컬 모델, 아니면 `claude`와 `CLAUDE_FACTS_MODEL`이다. 첨부에 `auto`는 적히지 않는다(A6).
- [ ] 고른 llama-server가 작업 중 실패하면 그 작업은 `extractor_unavailable`이고 같은 실행의 뒤 `auto` 작업은 확인 없이 claude다. 다음 실행은 다시 확인한다(A6).
- [ ] 고정 `llama-server`는 서버가 답하지 않아도 claude를 부르지 않고, 기존 `claude`, `llama-server` 설정 파일은 끝점 확인 없이 지금처럼 동작한다(A5, A6).
- [ ] 추출기를 고른 작업이 끝날 때마다 `<graph-home>/logs/facts-last-job.json`을 임시 파일과 `os.replace`로 쓴다. 값은 첨부에 적은 추출기·모델과 같다.
- [ ] 수동 A3, A13 확인을 했고 결과를 spec의 해당 evidence에 남긴다.
