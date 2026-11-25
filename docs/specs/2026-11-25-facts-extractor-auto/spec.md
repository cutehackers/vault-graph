# 사실 추출기 `auto`와 도구 이름 줄 빼기(3d, 3e)

<!-- bake: index -->
| ID | title | status | relations | covered by | area | hash | tasks |
|---|---|---|---|---|---|---|---|
| X1 | `Tools:` 줄은 v1 part에만 있다 |  |  |  |  | 6179897f |  |
| X2 | 사실 작업자는 v2 part만 읽는다 |  | basis 2026-11-25-memory-intent-layers:X10 |  |  | d63cdd28 |  |
| X3 | v2 part는 도구 호출을 `- <이름>` 줄로 적고, 교환 메타가 이름 목록을 가진다 |  | basis X1 |  |  | cd619ad2 |  |
| X4 | 두 추출기는 프롬프트 함수 하나를 같이 쓴다 |  |  |  |  | 0f0e08fa |  |
| X5 | 추출기 값은 둘이고 설정 파일이 없으면 claude다 |  |  |  |  | ec410d94 |  |
| X6 | 작업자는 실행마다 추출기 하나를 만들고, 캐시 키와 첨부에 설정 값을 쓴다 |  |  |  |  | 063f6aef |  |
| X7 | llama-server가 답하지 않으면 작업은 30분 뒤 다시 시도된다 |  |  |  |  | 91436f49 |  |
| X8 | 훅과 다른 명령은 추출기 포트를 불러오지 않는다 |  |  |  |  | 513f0136 |  |
| X9 | `vg facts` 명령의 지금 동작 |  |  |  |  | 490c021b |  |
| X10 | 회상 구획D는 전체 회상에만 있고 줄 목록을 밖에서 받는다 |  |  |  |  | 168e7467 |  |
| X11 | 테스트는 진짜 추출기를 만들지 못한다 |  |  |  |  | 84b22d18 |  |
| X12 | 도구 호출 줄을 모두 빼도 실제 part의 사실은 줄지 않았다 |  |  |  |  | 6c560c94 |  |
| I1 | 사실 캐시 키는 교환 원문 해시와 실제로 고른 추출기·모델로 만든다 |  | basis X6 | A2 | 사실 추출 | 8e80e3a7 | 2-worker-tool-lines-and-pick.md |
| I2 | `.facts.md`의 `extractor`, `model`은 그 작업이 실제로 고른 값이다 |  |  | A6, A13 | 사실 추출 | b84b73eb | 2-worker-tool-lines-and-pick.md |
| I3 | `llama-server`로 고정한 설정은 claude를 부르지 않는다 |  | basis X7 | A5, A6 | 사실 추출 | 7d9dcd4f | 2-worker-tool-lines-and-pick.md |
| I4 | 훅, `vg facts status`, 회상은 추출기 포트를 불러오지 않는다 |  | basis X8 | A8 | 사실 추출, 회상 | e521368c | 1-auto-settings-health-facts-cli.md |
| D1 | 3d는 v2 part에서 도구 호출 줄을 인자까지 모두 뺀다 | decided | basis X1, X2, X3, X12 | A1, A3 |  | 58403465 | 2-worker-tool-lines-and-pick.md |
| D2 | 필터는 작업자가 추출기 입력을 만들 때 하고 캐시 키는 그대로 둔다 | decided | basis X4, X6, I1; depends D1 | A2, A3 |  | 73b0f95d | 2-worker-tool-lines-and-pick.md |
| D3 | 거른 뒤 빈 교환은 추출기에 넘기지 않는다 | decided | depends D2 | A2 |  | 3fe3aacb | 2-worker-tool-lines-and-pick.md |
| D4 | 추출기 값 `auto`를 더하고 설정 파일이 없을 때의 기본값으로 한다 | decided | basis X5, 2026-11-25-memory-intent-layers:D6 | A4 | 사실 추출 | 0a4b5bab | 1-auto-settings-health-facts-cli.md |
| D5 | "답한다"는 `GET <endpoint>/health`가 시간 안에 HTTP 200을 돌려준 것이다 | decided | basis I4; depends D4 | A7, A11 | 사실 추출 | ee1eedf0 | 1-auto-settings-health-facts-cli.md |
| D6 | `auto`는 작업마다 고르고, 중간에 실패한 작업은 실패로 남긴다 | decided | basis X6, X7, I1, I3; depends D5 | A6, A13 | 사실 추출 | e9afecfe | 2-worker-tool-lines-and-pick.md |
| D7 | `auto` 설정 파일은 로컬 끝점과 모델을 담고 형식 version은 1 그대로다 | decided | basis X5; depends D4 | A4, A5 | 사실 추출 | b2e658b6 | 1-auto-settings-health-facts-cli.md |
| D8 | `vg facts on --extractor auto\|llama-server\|claude`로 바꾸고, 값을 주지 않으면 `auto`를 저장한다 | decided | basis X9; depends D4, D7 | A9 | 사실 추출 | 0a607492 | 1-auto-settings-health-facts-cli.md |
| D9 | `vg facts status`가 지금 고를 추출기와 마지막 작업의 추출기를 보인다 | decided | basis X9, I2, I4; depends D5, D6 | A9, A13 | 사실 추출 | 04b945b4 | 1-auto-settings-health-facts-cli.md |
| D10 | 세션 시작 회상의 구획D에 추출기 줄 하나를 매 세션 둔다 | decided | basis X10, I4, 2026-11-25-memory-intent-layers:D19; depends D5, D9 | A10, A11 | 사실 추출, 회상 | 4aad5e91 | 3-recall-facts-line-and-notice.md |
| D11 | 수집 알림에 `auto` 문구를 더한다 | decided | basis X8; depends D4 | A12 | 사실 추출 | 1f3b9498 | 3-recall-facts-line-and-notice.md |
| F1 | `auto`인데 llama-server가 답하지 않는다 |  | basis D4, D5, 2026-11-25-memory-intent-layers:F6 | A6 |  | b5949502 | 2-worker-tool-lines-and-pick.md |
| F2 | 고른 llama-server가 작업 중에 멈춘다 |  | basis D6, X7 | A6 |  | de6ddd73 | 2-worker-tool-lines-and-pick.md |
| F3 | `llama-server`로 고정했는데 서버가 답하지 않는다 |  | basis D9, D10, I3 | A6 |  | c1c0938d | 2-worker-tool-lines-and-pick.md |
| F4 | 설정 파일이 깨졌다 |  | basis D10, X5 | A10 |  | e1167a0d | 3-recall-facts-line-and-notice.md |
| F5 | 회상이 handoff하거나 resume, fork다 |  | basis D10, X10 | A10 |  | b29f1047 | 3-recall-facts-line-and-notice.md |
| F6 | 세션 시작 훅의 끝점 확인이 시간을 넘는다 |  | basis D5, D10 | A10 |  | decb925f | 3-recall-facts-line-and-notice.md |
| F7 | 사용자 글머리표가 그 교환에서 쓴 도구 이름과 같다 |  | basis D1 | A1 |  | e4e75157 | 2-worker-tool-lines-and-pick.md |
| F8 | 거른 뒤 교환 본문이 빈다 |  | basis D3 | A2 |  | 95efb59b | 2-worker-tool-lines-and-pick.md |
| F9 | 마지막 작업 기록이 없거나 읽을 수 없다 |  | basis D9 | A9 |  | 69c1c7ba | 1-auto-settings-health-facts-cli.md |
| R1 | 설명 없이 명령만 돌린 교환은 그 명령의 사실을 잃는다 |  | basis X3, X12 |  |  | 56c4e71d |  |
| R2 | llama-server의 `/health` 응답을 이 Mac에서 확인하지 않았다 |  | basis 2026-11-25-memory-intent-layers:X19 |  |  | 44f5716e |  |
| R3 | 옛 vg 설치본이 `auto` 파일을 깨진 것으로 읽는다 |  | basis X5 |  |  | 4ad6d53f |  |
| R4 | 첨부의 `model`은 서버가 실제로 띄운 모델이 아닐 수 있다 |  | basis X6 |  |  | 256fb7be |  |
| R5 | 로컬 추출기가 긴 part에서 느리거나 사실을 덜 뽑을 수 있다 |  | basis 2026-11-25-memory-intent-layers:X18 |  |  | 34856d6f |  |
| A1 | 메타에 있는 이름의 도구 호출 줄만 빠진다 |  | covers D1, F7 |  |  | f55f02bd | 2-worker-tool-lines-and-pick.md |
| A2 | 같은 part의 추출기 입력이 줄고 교환과 캐시 키는 그대로다 |  | covers D2, D3, I1, F8 |  |  | 0167361b | 2-worker-tool-lines-and-pick.md |
| A3 | 실제 part에서 뽑힌 사실 수가 줄지 않는다 |  | covers D1, D2 |  |  | 312a44d8 | 2-worker-tool-lines-and-pick.md |
| A4 | 설정 파일이 없으면 `auto`이고 `auto` 파일 검사가 맞다 |  | covers D4, D7 |  |  | 515dddb0 | 1-auto-settings-health-facts-cli.md |
| A5 | 기존 `claude`, `llama-server` 설정 파일은 그대로 동작한다 |  | covers D7, I3 |  |  | d57abc6b | 2-worker-tool-lines-and-pick.md |
| A6 | 작업자가 작업마다 고르고 실제 값을 캐시와 첨부에 적는다 |  | covers D6, I2, I3, F1, F2, F3 |  |  | cc719b3d | 2-worker-tool-lines-and-pick.md |
| A7 | 끝점 확인은 200만 답으로 친다 |  | covers D5 |  |  | 165e391f | 1-auto-settings-health-facts-cli.md |
| A8 | 훅과 status는 추출기 모듈을 불러오지 않는다 |  | covers I4 |  |  | fd525a33 | 1-auto-settings-health-facts-cli.md |
| A9 | `vg facts on\|off\|status`가 `auto`를 다루고 두 줄을 더 보인다 |  | covers D8, D9, F9 |  |  | 50110afe | 1-auto-settings-health-facts-cli.md |
| A10 | 세션 시작 회상에 추출기 줄이 하나 나온다 |  | covers D10, F4, F5, F6 |  |  | 81a2990f | 3-recall-facts-line-and-notice.md |
| A11 | 추출기 줄은 약 15토큰이고 훅 확인은 0.3초를 넘지 않는다 |  | covers D10, D5 |  |  | 8744925b | 3-recall-facts-line-and-notice.md |
| A12 | 수집 알림에 `auto` 문구가 있다 |  | covers D11 |  |  | a76547e7 | 3-recall-facts-line-and-notice.md |
| A13 | 서버를 끄고 켜면 status와 첨부가 따라 바뀐다 |  | covers D6, D9, I2 |  |  | dd6fb8e7 | 2-worker-tool-lines-and-pick.md |
| O1 | 3d에서 어떤 줄을 뺄까? |  | decides D1, D2 |  |  | 78b31ed1 |  |
<!-- bake: index end -->

## 1. Problem

부모 spec `docs/specs/2026-11-25-memory-intent-layers/spec.md` §4.3의 3d, 3e를 구현하기 전 상태다. 2026-11-25에 commit `fd21e3f`의 코드와 vault-graph Vault(`~/vaults/vault-graph/raw/sessions/claude-code/`)를 직접 읽고 grep해 확인했다. 연구 폴더에 파일을 쓸 수 없어서 사실 블록을 이 절에 둔다.

- 3d: brief는 `Tools: Bash` 같은 줄을 빼라고 했다. 그런데 이 줄은 v1 part에만 있고(X1), 사실 작업자는 v2 part만 읽는다(X2). 그래서 brief의 패턴대로 빼면 지금 프롬프트는 1바이트도 줄지 않는다. v2 part의 도구 줄은 `- REPL`, `- Bash \`git …\`` 모양이고, 교환 메타가 그 교환의 도구 이름을 가진다(X3). 두 추출기는 프롬프트 함수 하나를 같이 쓴다(X4).
- 3e: 추출기 값은 `claude`, `llama-server` 둘이고 설정 파일이 없으면 `claude`다(X5). 작업자는 실행마다 추출기 하나를 만들고, 캐시 키와 `.facts.md` 첨부에 설정 값을 그대로 적는다(X6). 로컬 서버가 꺼져 있으면 작업은 30분 뒤 다시 시도될 뿐 claude로 가지 않는다(X7). `vg facts status`와 세션 시작 회상 어디에도 지금 어떤 추출기가 쓰이는지 나오지 않는다(X9, X10).

### X1. `Tools:` 줄은 v1 part에만 있다
- source: Vault grep `^Tools: [A-Za-z0-9_.:-]+(, [A-Za-z0-9_.:-]+)*$` 33개 파일 18,344줄, `^schema: vault-session/v2` 파일 43개와 대조(2026-11-25)

두 파일 목록은 겹치지 않는다. v2 part에는 `Tools:` 줄이 없다. `Tools:`가 들어간 줄은 모두 18,373줄이고, 패턴에 맞지 않는 29줄은 문장 중간에 `Tools:`가 있는 산문이다.
### X2. 사실 작업자는 v2 part만 읽는다
- source: `src/vault_graph/interface/composition/adapters/fact_worker.py:335-338@fd21e3f`
- basis: 2026-11-25-memory-intent-layers:X10

`schema`가 `vault-session/v2`가 아니면 `part_unreadable`로 작업을 닫는다. v1 part의 `Tools:` 줄은 지금 프롬프트에 들어가지 않는다.

### X3. v2 part는 도구 호출을 `- <이름>` 줄로 적고, 교환 메타가 이름 목록을 가진다
- source: `2026-11-06-2428954a-…-part1.md:25-36`, `2026-11-19-70c57bbc-…-part1.md:25,45-60`, 2026-11-1x·2x 파일 grep(2026-11-25)
- basis: X1

메타 줄에 `tools=Agent:10,Bash:3,Poll:10,REPL:6,…`처럼 이름과 횟수가 있다. 본문 도구 줄은 `- REPL`처럼 이름만 있거나 `- Bash \`git …\``처럼 인자가 붙는다. 2026-11-10 이후 v2 part에서 이름만 있는 줄(`^- [A-Za-z0-9_.:-]+$`)은 1,457줄, 인자가 붙은 줄은 8,382줄이다. 사용자가 쓴 글머리표(`- create 2 subagents …`)도 같은 `- ` 모양이다.

### X4. 두 추출기는 프롬프트 함수 하나를 같이 쓴다
- source: `claude_fact_extractor.py:83-86@fd21e3f`, `llama_fact_extractor.py:16-20,53@fd21e3f`, `fact_worker.py:363-381@fd21e3f`

`build_facts_prompt`는 교환의 id, 날짜, 본문을 JSON 목록으로 붙인다. 본문은 작업자가 메타 줄 아래 줄을 그대로 이은 것이다.

### X5. 추출기 값은 둘이고 설정 파일이 없으면 claude다
- source: `src/vault_graph/operation/scope/facts_settings.py:24,77-101,173-185@fd21e3f`

`claude`면 `endpoint`가 null, `llama-server`면 http(s) 주소여야 한다. 파일 형식 version은 1이고, 모르는 값이 있으면 파일을 깨진 것으로 보고 추출을 끈다.

### X6. 작업자는 실행마다 추출기 하나를 만들고, 캐시 키와 첨부에 설정 값을 쓴다
- source: `fact_worker.py:141-159,388-404,455-461@fd21e3f`

`_Extraction`은 처음 캐시를 놓칠 때 추출기를 만든다. `FactExtractorUnavailable`이 나면 이유를 `down`에 적고 그 실행의 뒤 작업에서는 부르지 않는다. 캐시 키는 `settings.extractor`, `settings.model`, 교환 원문 해시다. 첨부 입력의 `extractor`, `model`도 설정 값이다.

### X7. llama-server가 답하지 않으면 작업은 30분 뒤 다시 시도된다
- source: `llama_fact_extractor.py:71-77@fd21e3f`, `fact_worker.py:18-19,418-423@fd21e3f`

HTTP 오류와 연결 실패는 `FactExtractorUnavailable`이 되고, 작업자는 `extractor_unavailable`로 적고 작업을 대기열에 남긴다. llama 요청 시간 제한은 900초다.

### X8. 훅과 다른 명령은 추출기 포트를 불러오지 않는다
- source: `hook_commands.py:93,111-120,493-496,540-547@fd21e3f`, `facts_commands.py:134-135@fd21e3f`

작업자 모듈은 함수 안에서만 import한다(spec 2026-11-16의 import 경계). 수집 알림 문구는 추출기 이름별 표이고 처음 한 번만 낸다.

### X9. `vg facts` 명령의 지금 동작
- source: `src/vault_graph/interface/cli/facts_commands.py:36-40,52-112@fd21e3f`

`on`은 파일이 없으면 `--extractor` 값이나 claude로 저장하고, `off`는 파일이 없으면 claude를 꺼진 상태로 저장한다. `status`는 `facts`, `extractor`, `model`, `endpoint`, `settings`, `problem`, `queue`, `failures` 줄을 낸다. 마지막 작업 기록은 없다.

### X10. 회상 구획D는 전체 회상에만 있고 줄 목록을 밖에서 받는다
- source: `src/vault_graph/context/pack/recall.py:201-280,726-756@fd21e3f`, `hook_commands.py:195-204@fd21e3f`

`source`가 resume, fork면 알림만 내고 구획D가 없다. 회상할 것이 없으면 handoff해 `recall.sh`로 넘어간다. 훅은 색인 실패 줄을 `index_failures`로 넘기고 구획D가 그 줄을 보인다.

### X11. 테스트는 진짜 추출기를 만들지 못한다
- source: `tests/conftest.py:41-54@fd21e3f`

autouse fixture가 `_construct`를 가짜로 바꾸고, `_load_adapter_class`를 부르면 테스트를 실패시킨다.

### X12. 도구 호출 줄을 모두 빼도 실제 part의 사실은 줄지 않았다
- source: 2026-11-25 이 change의 측정. vault-graph Vault v2 part 3개를 claude 추출기로 두 번씩 추출

등록 Vault의 v2 part 214개에서 이름만 있는 도구 줄은 본문 바이트의 0.5%, 인자가 붙은 도구 줄은 33.2%다. part 3개(`2026-11-11-11b39614…-part1`, `2026-11-18-74521120…-part1`, `2026-11-23-bcc39f4f…-part1`)에서 메타 `tools=`에 있는 이름의 도구 줄을 모두 빼니 프롬프트 바이트가 17%, 13%, 28% 줄었다. 사실 수는 10→12, 17→16, 13→11(합 40→39)이었다. 빠진 사실은 다른 사실과 합쳐진 것이었고 결정, commit, 파일 이름은 assistant 설명에서 그대로 나왔다.

## 2. Intent

사용자는 사실 추출에 "로컬 ai가 존재하면 기본으로 이것을 사용하고 아니라면 claude"를 쓰기를 원한다. 이 선택은 "설정이나 명령어로도 변경가능"해야 하고, 지금 "로컬 ai인지 아니면 claude 인지"를 사용자가 볼 수 있어야 한다. 로컬은 llama-server 끝점이 답할 때만 있는 것으로 친다(부모 spec 옵션1). 세션 시작 회상의 추출기 줄은 매 세션 보인다(부모 spec의 회상 줄 결정, "매 세션 보임"). 이유는 서버가 꺼진 것을 모르고 지나가는 날이 없게 하려는 것이다.

3d에서 사용자는 사실 추출에 "가장 궁극적인 방법"을 원했고, 추출 모델에는 대화만 주고 도구 호출 줄은 인자까지 모두 빼는 방식을 골랐다(O1). 같은 part의 프롬프트가 작아지고 뽑히는 사실은 줄지 않아야 한다. 기계가 아는 것은 코드가 붙인다(부모 spec 3c).

기존 `claude` 설정 파일은 그대로 동작해야 한다.

## 3. Non-goals

- 3a(v1 part 다시 수집), 3b(`vg facts backfill`), 3c(사실 계약 v2의 종류와 개념 태그)는 하지 않는다.
- 인자가 붙은 도구 줄(`- Bash \`git …\``)은 빼지 않는다. 명령과 파일 경로에서 사실이 나올 수 있다.
- v1 part의 `Tools:` 줄은 작업자가 v1을 읽지 않으므로(X2) 따로 다루지 않는다.
- 작업 하나 안에서 llama-server가 실패했을 때 그 자리에서 claude로 다시 추출하지 않는다.
- 사실 캐시 형식, 실패 기록 형식, 재시도 간격 30분은 바꾸지 않는다.
- vault-builder `sessions attach-facts` 계약은 바꾸지 않는다. 지금도 `extractor`, `model`을 받는다.

## 4. Design

**4.1 도구 이름 줄 빼기(3d)**

- `fact_worker.py`: `_exchanges`가 메타 줄의 `tools=` 값에서 이름만 모아 `_Exchange.tools`(이름 집합)에 넣는다. 새 순수 함수 `strip_tool_name_lines(text: str, tools: frozenset[str]) -> str`가 줄 전체가 `- <이름>`이고 그 이름이 `tools`에 있는 줄만 지운다(D1).
- `_facts_for_part`는 캐시 키를 지금처럼 원문으로 만들고, `_extract`에 넘기는 `FactExchange.text`만 지운 본문으로 바꾼다(D2, I1). 지운 뒤 빈 교환은 넘기지 않는다(D3).
- `build_facts_prompt`와 두 추출기 모듈은 바꾸지 않는다.

**4.2 추출기 `auto`(3e)**

- `facts_settings.py`: `FACT_EXTRACTORS`에 `auto`를 더한다. 파일이 없으면 `default_facts_settings("auto")`를 쓴다(D4). `auto`의 `endpoint`는 http(s) 주소, `model`은 로컬 모델이다(D7). 새 순수 함수 `resolve_facts_settings(settings: FactsSettings, local_answers: bool) -> FactsSettings`가 `auto`를 `llama-server`(같은 끝점과 모델) 또는 `claude`(`CLAUDE_FACTS_MODEL`)로 바꾼다. 마지막 작업 기록 경로 `facts_last_job_path(graph_home)`도 여기서 정한다(D9).
- 새 모듈 `interface/composition/adapters/llama_health.py`: `llama_server_answers(endpoint: str, *, timeout_s: float) -> bool`. 표준 라이브러리 HTTP만 쓰고 추출기 모듈을 import하지 않는다(D5, I4).
- `fact_worker.py`: 작업마다 캐시를 보기 전에 추출기를 고른다(D6). `_Extraction`은 고른 이름과 모델마다 추출기를 하나씩 만들고 `down`도 이름마다 따로 적는다. 캐시 키와 첨부 입력에는 고른 값을 쓴다(I1, I2). 추출기를 고른 작업이 끝날 때마다 마지막 작업 기록을 쓴다(D9).
- `fact_extractor_selection.py`: `select_fact_extractor`는 `auto`를 받으면 `CatalogError`를 낸다. `auto`는 늘 작업자가 먼저 푼다.
- `facts_commands.py`: `--extractor`가 `auto`를 받고, `status`에 `extractor_now`, `last_job` 줄을 더한다(D8, D9).
- `hook_commands.py`: `session-start`가 추출기 줄을 계산해 `recall`에 넘긴다(D10). 수집 알림 표에 `auto` 문구를 더한다(D11).
- `context/pack/recall.py`: `recall(..., facts_line: str | None = None)`. 전체 회상의 구획D에서 열기 안내 다음 줄에 둔다(D10).

### I1. 사실 캐시 키는 교환 원문 해시와 실제로 고른 추출기·모델로 만든다
- by: 가정 (brief 가정1, 가정4)
- area: 사실 추출
- basis: X6

3d 필터를 넣어도 원문 해시는 바뀌지 않으므로 이미 쌓인 캐시를 다시 쓴다. `auto`일 때 키의 추출기와 모델은 설정 값 `auto`가 아니라 그 작업에서 고른 값이다.

### I2. `.facts.md`의 `extractor`, `model`은 그 작업이 실제로 고른 값이다
- by: 사람 (brief 목표 3e, ".facts.md keeps recording the real extractor and model")
- area: 사실 추출

첨부에 `auto`가 적히는 일은 없다. 사용자는 첨부만 보고도 로컬과 claude 중 어느 쪽이 뽑았는지 안다.

### I3. `llama-server`로 고정한 설정은 claude를 부르지 않는다
- by: 사람 (brief 목표 3e, "A fixed llama-server never falls back to claude")
- area: 사실 추출
- basis: X7

claude로 넘어가는 일은 `auto`일 때만 있다. 고정 설정에서 서버가 답하지 않으면 작업은 지금처럼 실패로 남는다(X7).

### I4. 훅, `vg facts status`, 회상은 추출기 포트를 불러오지 않는다
- by: 가정 (spec 2026-11-16의 import 경계를 이어받음)
- area: 사실 추출, 회상
- basis: X8

끝점 확인은 `llama_health.py`만 쓴다. 이 모듈은 추출기 모듈과 작업자 모듈을 import하지 않는다.

## 5. Decisions

D1~D3은 3d, D4~D11은 3e다. 사용자가 brief와 부모 spec에서 정한 것만 `decided`다.

### D1. 3d는 v2 part에서 도구 호출 줄을 인자까지 모두 뺀다
- by: 사람 (2026-11-25 spec gate, "사실추출에 가장 궁극적인 방법을 제안하라" 뒤 "도구 줄 전부 빼기" 선택)
- status: decided
- basis: X1, X2, X3, X12

brief 예시 `Tools: Bash` 줄은 v1 part에만 있어(X1) 작업자가 읽는 v2 part에서는 아무것도 줄지 않는다(X2). v2는 도구 호출을 `- REPL`, ``- Bash `git status` ``, 실패면 `✗: <오류 첫 줄>`이 붙은 한 줄로 적는다(X3). 원칙: 추출 모델에는 대화(사용자 말과 assistant 설명)만 주고, 기계가 이미 아는 것(쓴 도구, 고친 파일, commit, 오류 수)은 교환 메타에 있으니 코드가 붙인다(부모 spec 3c). 그래서 `### user` 구획이 아닌 구획(도구 줄이 붙는 assistant 구획)에서 `- <이름>` 또는 `- <이름> <인자…>` 줄 가운데 이름이 그 교환 메타 `tools=`에 있는 줄을 모두 뺀다. 사용자 구획의 글머리표는 이름이 같아도 남는다. 도구 줄을 빼고 나서 빈 assistant 구획은 제목 줄까지 뺀다. 실제 part에서 프롬프트는 13~28% 줄고 사실 수는 줄지 않았다(X12).

### D2. 필터는 작업자가 추출기 입력을 만들 때 하고 캐시 키는 그대로 둔다
- by: 가정 (brief 가정1을 메타가 필요한 D1에 맞춤)
- status: decided
- basis: X4, X6, I1
- depends: D1

brief는 `build_facts_prompt` 안에서 거르자고 했지만, D1은 교환 메타의 도구 이름이 필요하고 그 메타는 작업자만 읽는다(X4). 작업자가 `FactExchange.text`를 거른 본문으로 만들면 두 추출기가 똑같이 받는다. 캐시 키는 원문 해시라서 이미 쌓인 캐시가 그대로 맞는다(I1).

### D3. 거른 뒤 빈 교환은 추출기에 넘기지 않는다
- by: 가정 (brief 가정1)
- status: decided
- depends: D2

빈 교환은 사실 없음(빈 목록)으로 캐시에 넣는다. 캐시를 놓친 교환이 모두 비면 그 작업은 추출기를 부르지 않는다.

### D4. 추출기 값 `auto`를 더하고 설정 파일이 없을 때의 기본값으로 한다
- by: 사람 (2026-11-25 대화, "로컬 ai가 존재하면 기본으로 이것을 사용하고 아니라면 claude")
- status: decided
- area: 사실 추출
- basis: X5, 2026-11-25-memory-intent-layers:D6

추출기 값은 `auto`, `llama-server`, `claude` 셋이다. `auto`는 llama-server 끝점이 답하면 llama-server를, 아니면 claude를 쓴다. 파일이 없을 때 지금은 claude지만(X5) 이제 `auto`다.

### D5. "답한다"는 `GET <endpoint>/health`가 시간 안에 HTTP 200을 돌려준 것이다
- by: 사람 (부모 spec 옵션1, 끝점이 답할 때만 로컬), 가정 (`/health`, 200만 인정, 시간 제한 값)
- status: decided
- area: 사실 추출
- basis: I4
- depends: D4

llama-server는 모델을 읽는 동안 503을 돌려주므로 200만 답으로 친다. 시간 제한은 작업자 2초, `vg facts status` 1초, 세션 시작 훅 0.3초로 한다. 훅은 세션 시작을 늦추면 안 되기 때문에 가장 짧다. 확인 함수는 `llama_health.py`에 두어 훅도 쓸 수 있게 한다(I4).

### D6. `auto`는 작업마다 고르고, 중간에 실패한 작업은 실패로 남긴다
- by: 사람 (brief 목표 3e, "A job whose server stops midway fails and the next job picks again"), 가정 (같은 실행 안의 기억)
- status: decided
- area: 사실 추출
- basis: X6, X7, I1, I3
- depends: D5

작업자는 `auto` 작업마다 캐시를 보기 전에 끝점을 확인하고 추출기를 고른다(I1). 고른 llama-server가 작업 중에 답하지 않으면 그 작업은 지금처럼 `extractor_unavailable`로 남고 30분 뒤 다시 시도된다(X7). 같은 실행의 뒤 `auto` 작업은 확인 없이 claude를 고른다. `/health`는 답하는데 추출 요청만 실패하는 서버에서 작업마다 실패하지 않게 하려는 것이다. 다음 실행은 다시 확인한다. 고정 설정은 바꾸지 않는다(I3).

### D7. `auto` 설정 파일은 로컬 끝점과 모델을 담고 형식 version은 1 그대로다
- by: 사람 (brief 목표 3e, "Existing settings files with claude keep working"), 가정 (`auto`의 필드 값)
- status: decided
- area: 사실 추출
- basis: X5
- depends: D4

`auto` 파일의 `endpoint`는 http(s) 주소(기본 `http://127.0.0.1:8080`), `model`은 로컬 모델 파일(기본 `local_facts_model()`)이다. claude를 고르면 `CLAUDE_FACTS_MODEL`을 쓴다. 키가 같아서 version 1을 그대로 쓰고, `claude`, `llama-server` 파일은 지금처럼 읽힌다.

### D8. `vg facts on --extractor auto|llama-server|claude`로 바꾸고, 값을 주지 않으면 `auto`를 저장한다
- by: 사람 (2026-11-25 대화, "설정이나 명령어로도 변경가능"), 가정 (파일이 없을 때 저장하는 값)
- status: decided
- area: 사실 추출
- basis: X9
- depends: D4, D7

`on`은 파일이 있고 값이 같거나 없으면 저장된 설정을 켠다. 파일이 없거나 깨졌으면 `--extractor` 값, 없으면 `auto`를 저장한다. `off`는 파일이 없으면 `auto`를 꺼진 상태로 저장한다. 지금은 두 곳 모두 claude다(X9). 도움말은 "Default: keep the saved one, else auto"로 바꾼다.

### D9. `vg facts status`가 지금 고를 추출기와 마지막 작업의 추출기를 보인다
- by: 사람 (brief 목표 3e, "로컬 ai인지 아니면 claude 인지"), 가정 (줄 이름, 기록 파일)
- status: decided
- area: 사실 추출
- basis: X9, I2, I4
- depends: D5, D6

지금 줄(X9)은 그대로 두고 두 줄을 더한다.

1. `extractor_now: <이름> <모델>`. `auto`가 claude를 고르면 `(llama-server not answering at <endpoint>)`를, 고정 llama-server가 답하지 않으면 `(not answering)`을 붙인다. 꺼져 있으면 `extractor_now: none`이다. 확인은 D5 방식이다(I4).
2. `last_job: <작업> <상태> <추출기> <모델> <끝난 시각>` 또는 `last_job: none`.

작업자는 추출기를 고른 작업이 끝날 때마다 `<graph-home>/logs/facts-last-job.json`에 작업 이름, 상태, 추출기, 모델, 끝난 시각을 임시 파일과 `os.replace`로 쓴다. 추출기와 모델은 첨부에 적은 값과 같다(I2).

### D10. 세션 시작 회상의 구획D에 추출기 줄 하나를 매 세션 둔다
- by: 사람 (2026-11-25 spec gate, "매 세션 보임"), 가정 (문구와 자리)
- status: decided
- area: 사실 추출, 회상
- basis: X10, I4, 2026-11-25-memory-intent-layers:D19
- depends: D5, D9

훅이 설정을 읽고 D5 방식으로 확인해 아래 중 한 줄을 만들고 `recall`에 넘긴다. 구획D의 열기 안내 다음에 둔다.

- `- facts: auto → llama-server`, `- facts: auto → claude`
- `- facts: llama-server`, `- facts: llama-server (not answering)`, `- facts: claude`
- `- facts: off`, `- facts: off (settings broken)`

한 줄은 약 15토큰이다. 전체 회상(startup, clear, compact)에만 나오고, resume, fork의 알림 전용 출력과 handoff에는 없다(X10).

### D11. 수집 알림에 `auto` 문구를 더한다
- by: 가정 (brief 가정8)
- status: decided
- area: 사실 추출
- basis: X8
- depends: D4

처음 한 번 나오는 알림(X8)에 `auto` 문구를 둔다. "session fact extraction is on. After each captured session it runs the local llama-server when it answers, otherwise the logged-in Claude Code (`claude -p`), in the background. Run `vg facts off` to turn it off."

## 6. Failure and boundary behavior

### F1. `auto`인데 llama-server가 답하지 않는다
- basis: D4, D5, 2026-11-25-memory-intent-layers:F6

꺼져 있거나, 연결이 거부되거나, 모델을 읽는 중이라 503을 주거나, 시간 제한을 넘으면 모두 답하지 않은 것이다. 그 작업은 claude로 추출하고 첨부와 마지막 작업 기록에 `claude`와 `CLAUDE_FACTS_MODEL`을 적는다.

### F2. 고른 llama-server가 작업 중에 멈춘다
- basis: D6, X7

그 작업은 `extractor_unavailable`로 실패 기록에 남고 30분 뒤 다시 시도된다. 같은 실행의 뒤 `auto` 작업은 claude를 고른다. 다시 시도할 때는 그때 끝점을 확인해 고른다.

### F3. `llama-server`로 고정했는데 서버가 답하지 않는다
- basis: D9, D10, I3

작업은 지금처럼 `extractor_unavailable`로 실패한다. claude는 부르지 않는다. `vg facts status`는 `extractor_now: llama-server <모델> (not answering)`을, 회상은 `- facts: llama-server (not answering)`을 보인다.

### F4. 설정 파일이 깨졌다
- basis: D10, X5

추출은 지금처럼 꺼진다(X5). `vg facts status`는 `problem` 줄과 `extractor_now: none`을, 회상은 `- facts: off (settings broken)`을 보인다.

### F5. 회상이 handoff하거나 resume, fork다
- basis: D10, X10

추출기 줄은 나오지 않는다. handoff 뒤의 `recall.sh` 출력과 알림 전용 출력은 바꾸지 않는다.

### F6. 세션 시작 훅의 끝점 확인이 시간을 넘는다
- basis: D5, D10

0.3초를 넘으면 답하지 않은 것으로 보고 `- facts: auto → claude`를 낸다. 작업자는 2초로 따로 확인하므로, 느린 서버에서는 회상 줄과 실제 추출기가 다를 수 있다. 실제 값은 `vg facts status`의 `last_job`과 첨부에 남는다.

### F7. 사용자 글머리표가 그 교환에서 쓴 도구 이름과 같다
- basis: D1

`### user` 구획의 줄은 거르지 않으므로 사용자가 쓴 `- Read the spec`은 남는다. assistant 설명의 글머리표가 `- Read …`처럼 도구 이름으로 시작하면 빠진다. 원문과 캐시 키는 그대로다.

### F8. 거른 뒤 교환 본문이 빈다
- basis: D3

그 교환은 사실 없음으로 캐시에 들어간다. 캐시를 놓친 교환이 모두 비면 추출기를 부르지 않고, 다른 교환의 사실만으로 첨부하거나 `no_facts`로 끝낸다.

### F9. 마지막 작업 기록이 없거나 읽을 수 없다
- basis: D9

파일이 없으면 `last_job: none`, JSON이 깨졌거나 읽을 수 없으면 `last_job: unreadable`을 보인다. 작업자는 다음 작업에서 새로 쓴다.

## 7. What could be wrong

### R1. 설명 없이 명령만 돌린 교환은 그 명령의 사실을 잃는다
- basis: X3, X12

assistant가 설명 없이 도구만 쓴 교환에서는 명령, 실패한 오류 첫 줄에서 나오던 사실이 나오지 않는다. 세션 원문은 그대로 색인되므로 검색에서는 남는다. 파일과 commit은 3c에서 코드가 메타로 붙인다.

### R2. llama-server의 `/health` 응답을 이 Mac에서 확인하지 않았다
- basis: 2026-11-25-memory-intent-layers:X19

spec을 쓸 때는 서버가 꺼져 있어 200과 503 응답을 직접 보지 못했다. 버전에 따라 경로나 응답이 다르면 `auto`가 늘 claude를 고른다. 구현 때 확인했다(2026-11-25, llama-server 0.9.0 build 12110, Qwen3-8B를 포트 8091로 잠깐 띄움): 시작 직후 연결 거부, 모델을 읽는 동안 `/health`가 503 `{"error":{"message":"Loading model",…}}`, 약 4초 뒤 200 `{"status":"ok"}`. `check_llama_health`는 200일 때 참, 서버를 끈 뒤 거짓이었다.

### R3. 옛 vg 설치본이 `auto` 파일을 깨진 것으로 읽는다
- basis: X5

같은 Graph Home을 옛 버전 vg가 읽으면 모르는 값이라 추출을 끈다(X5). 버전을 내리거나 두 설치본을 같이 쓸 때만 생긴다.

### R4. 첨부의 `model`은 서버가 실제로 띄운 모델이 아닐 수 있다
- basis: X6

llama-server 쪽 `model`은 설정 값이다(X6). 서버가 다른 모델 파일로 떠 있으면 첨부에는 설정 값이 적힌다. 서버에 띄운 모델을 묻는 일은 이번에 하지 않는다.

### R5. 로컬 추출기가 긴 part에서 느리거나 사실을 덜 뽑을 수 있다
- basis: 2026-11-25-memory-intent-layers:X18

로컬 14초는 짧은 세션 기준이다. `auto`가 기본이 되면 서버를 켠 사용자의 긴 part도 로컬로 간다.

## 8. Acceptance criteria

테스트는 가짜 추출기로 돈다(X11). 진짜 추출기와 진짜 서버가 필요한 확인은 `수동`이다.

### A1. 메타에 있는 이름의 도구 호출 줄만 빠진다
- covers: D1, F7
- check: tests/test_fact_worker.py
- evidence:

assistant 구획에서 메타 `tools=`에 있는 이름의 `- <이름>` 줄과 `- <이름> <인자…>` 줄(실패 표시 줄 포함)은 빠진다. `### user` 구획의 같은 모양 줄, 메타에 없는 이름의 줄, 이름 뒤에 공백 없이 글자가 이어지는 줄, 사용자 글머리표 문장, 문장 중간에 `Tools:`가 있는 줄은 남는다.

### A2. 같은 part의 추출기 입력이 줄고 교환과 캐시 키는 그대로다
- covers: D2, D3, I1, F8
- check: tests/test_fact_worker.py
- evidence:

도구 호출 줄이 섞인 v2 fixture part에서 가짜 추출기가 받은 `build_facts_prompt` 바이트가 필터 전보다 작다. 받은 교환 id 목록과 첨부 사실 수는 같고, 캐시 키는 원문 해시와 같다. 도구 줄뿐인 교환은 추출기에 가지 않고 빈 목록으로 캐시된다.

### A3. 실제 part에서 뽑힌 사실 수가 줄지 않는다
- covers: D1, D2
- check: 수동: 도구 호출 줄이 있는 실제 v2 part를 claude 추출기로 필터 없이 한 번, 필터와 함께 한 번 추출해 프롬프트 바이트와 사실 수를 비교한다
- evidence: 2026-11-25 spec 단계 측정(X12): part 3개에서 프롬프트 바이트 17%, 13%, 28% 감소, 사실 수 합 40→39, 빠진 사실은 합쳐진 것.

### A4. 설정 파일이 없으면 `auto`이고 `auto` 파일 검사가 맞다
- covers: D4, D7
- check: tests/test_facts_config.py
- evidence:

파일이 없으면 켜진 `auto`, 로컬 끝점, 로컬 모델이다. `auto` 파일의 `endpoint`가 null이거나 http(s)가 아니면 깨진 파일이다. `resolve_facts_settings`는 답하면 llama-server 설정을, 아니면 claude와 `CLAUDE_FACTS_MODEL`을 돌려준다.

### A5. 기존 `claude`, `llama-server` 설정 파일은 그대로 동작한다
- covers: D7, I3
- check: tests/test_facts_config.py, tests/test_fact_worker.py
- evidence:

이번 change 전에 저장한 두 형식의 파일을 그대로 읽어 같은 설정이 나오고, 작업자는 끝점을 확인하지 않고 그 추출기를 쓴다.

### A6. 작업자가 작업마다 고르고 실제 값을 캐시와 첨부에 적는다
- covers: D6, I2, I3, F1, F2, F3
- check: tests/test_fact_worker.py
- evidence:

확인 함수를 가짜로 바꿔 본다. 답하면 캐시 키와 첨부 입력이 `llama-server`와 로컬 모델, 답하지 않으면 `claude`와 `CLAUDE_FACTS_MODEL`이다. llama-server가 작업 중 실패하면 그 작업은 `extractor_unavailable`이고 같은 실행의 뒤 작업은 확인 없이 claude다. 고정 `llama-server`는 서버가 답하지 않아도 claude를 부르지 않는다.

### A7. 끝점 확인은 200만 답으로 친다
- covers: D5
- check: tests/test_llama_health.py
- evidence:

테스트 안의 로컬 HTTP 서버로 200은 참, 503·연결 거부·시간 초과는 거짓이다.

### A8. 훅과 status는 추출기 모듈을 불러오지 않는다
- covers: I4
- check: tests/test_llama_health.py
- evidence:

새 하위 프로세스에서 `hook_commands`, `facts_commands`, `llama_health`를 import한 뒤 `sys.modules`에 두 추출기 모듈과 `fact_worker`가 없다.

### A9. `vg facts on|off|status`가 `auto`를 다루고 두 줄을 더 보인다
- covers: D8, D9, F9
- check: tests/test_facts_config.py
- evidence:

파일이 없을 때 `on`과 `off`는 `auto`를 저장한다. `on --extractor auto|llama-server|claude`가 그 값을 저장한다. `status`는 `extractor_now`와 `last_job` 줄을 내고, 기록 파일이 없으면 `last_job: none`, 깨졌으면 `last_job: unreadable`이다.

### A10. 세션 시작 회상에 추출기 줄이 하나 나온다
- covers: D10, F4, F5, F6
- check: tests/test_cli_hook_session_start.py, tests/test_session_recall.py
- evidence:

전체 회상의 구획D에 D10 문구 중 상태에 맞는 한 줄이 열기 안내 다음에 있다. resume, fork, handoff에는 없다. 확인이 시간을 넘으면 `- facts: auto → claude`다.

### A11. 추출기 줄은 약 15토큰이고 훅 확인은 0.3초를 넘지 않는다
- covers: D10, D5
- check: tests/test_session_recall.py, tests/test_llama_health.py
- evidence:

D10의 일곱 문구 모두 `estimate_recall_tokens`로 15토큰 이하이고, 답하지 않는 서버에 대한 훅 확인은 0.3초 안에 끝난다.

### A12. 수집 알림에 `auto` 문구가 있다
- covers: D11
- check: tests/test_hook_facts.py
- evidence:

### A13. 서버를 끄고 켜면 status와 첨부가 따라 바뀐다
- covers: D6, D9, I2
- check: 수동: llama-server를 끈 채 세션 하나를 수집하고 `vg facts status`와 새 `.facts.md`를 본 뒤, 서버를 켜고 같은 일을 다시 한다
- evidence:

끈 때는 `extractor_now: claude …`와 첨부 `extractor: claude`, 켠 때는 `extractor_now: llama-server …`와 첨부 `extractor: llama-server`다. `last_job` 줄도 첨부와 같다.

## 9. Open decisions

### O1. 3d에서 어떤 줄을 뺄까?
- decides: D1, D2

답(2026-11-25 spec gate): 사용자는 "사실추출에 가장 궁극적인 방법을 제안하라"고 했고, 대화만 모델에 주고 도구 호출 줄을 인자까지 모두 빼는 제안(측정은 §1의 도구 줄 측정 블록)에 "도구 줄 전부 빼기"를 골랐다. D1에 적었다.
