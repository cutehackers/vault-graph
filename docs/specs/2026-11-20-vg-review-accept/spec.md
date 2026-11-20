# vg review: 프로젝트 폴더에서 기억 제안을 읽고 수락·거절하기, dream status의 발행 확인
<!-- bake: index -->
| ID | title | status | relations | covered by | area | hash | tasks |
|---|---|---|---|---|---|---|---|
| I1 | vault-graph 프로세스는 검토 흐름에서도 Vault 파일을 직접 쓰지 않는다 |  | basis X3 | A5, A9 | global | aa79049f | 3-vg-review-command.md |
| I2 | `review resolve`는 `vg review` 명령에서만 실행된다 |  | basis X7, X9 | A5 | global | 1c22eae0 | 3-vg-review-command.md |
| I3 | 수락 수와 수락률에는 발행된 수락만 들어간다 |  | basis X1, X6 | A6 |  | 22dba123 | 1-dream-status-published.md |
| I4 | 보기와 건너뛰기는 아무것도 바꾸지 않는다 |  |  | A1 |  | 6350243f | 3-vg-review-command.md |
| I5 | Vault가 처리했다고 답한 것만 수락·거절로 알린다 |  | basis X2 | A3, A9 |  | 16e1b525 | 2-proposal-change-and-resolve-adapter.md |
| I6 | 이 변경은 vault-builder 저장소와 기존 MCP 도구를 바꾸지 않는다 |  |  | A12 | global | ee4f37f5 | 5-docs-and-final-check.md |
| D1 | `review resolve`를 여섯째 Vault 쓰기 길로 더한다 | decided | basis X2, X7, X10, I2 | A5, A9, A10 | global | 584fd138 | 3-vg-review-command.md |
| D2 | 명령은 대화형 하나와 비대화형 넷이다 | decided | basis X4; depends D1 | A1, A9, A11 |  | 07baaddb | 3-vg-review-command.md |
| D3 | cwd 프로젝트에 연결된 모든 Vault를 본다 | decided | basis X11 | A1 |  | a4269689 | 3-vg-review-command.md |
| D4 | 제안마다 대상, 요약, 바뀌는 글, 근거를 보여준다 | decided | basis X4, X5, I4 | A2, A11 |  | 1417f9e6 | 2-proposal-change-and-resolve-adapter.md |
| D5 | 에이전트가 스스로 수락하는 길을 세 가지로 줄인다 | decided | basis X9, I2; depends D1, D2 | A4, A10, A11 |  | 7e1d9ff8 | 3-vg-review-command.md |
| D6 | 거절 이유는 필수이고 수락 이유에는 기본 문구가 있다 | decided | basis X2 | A8 |  | 601c54e7 | 3-vg-review-command.md |
| D7 | 수락은 "Published:" 표시가 있을 때만 수락으로 센다 | decided | basis X1, X3, X6, I1, I3 | A6, A9 |  | 64b3a6a7 | 1-dream-status-published.md |
| D8 | 수락으로 발행되면 그 Vault의 색인을 분리된 프로세스로 시작한다 | decided | basis X8, X11, I5 | A7, A9 |  | 12d78d8c | 3-vg-review-command.md |
| D9 | Vault의 답을 그대로 전하고 다음 할 일을 한 줄 붙인다 | decided | basis X1, X2, X7, I5 | A3 |  | c5238d00 | 2-proposal-change-and-resolve-adapter.md |
| D10 | 수락 방법을 안내하는 글을 `vg review`로 바꾼다 | decided | basis X10; depends D1, D7 | A10 |  | e603a00c | 5-docs-and-final-check.md |
| F1 | 파일의 status만 손으로 accepted로 고친 제안 |  | basis D7, X1, X3 | A6 |  | a42f7fe3 | 1-dream-status-published.md, 3-vg-review-command.md |
| F2 | 제안 뒤에 대상 페이지가 바뀌었다 |  | basis D9, X1 | A3 |  | 00d3e690 | 2-proposal-change-and-resolve-adapter.md |
| F3 | Vault 검증이 수락이나 거절을 막는다 |  | basis D9, X2 | A3 |  | 099c544d | 2-proposal-change-and-resolve-adapter.md |
| F4 | Vault 도구가 없거나 `review resolve --json`을 모른다 |  | basis D9, X7 | A3 |  | 70169a1f | 2-proposal-change-and-resolve-adapter.md |
| F5 | Vault 명령이 시간 한도를 넘겼다 |  | basis D9, X7 | A3 |  | bcab645b | 2-proposal-change-and-resolve-adapter.md |
| F6 | 터미널이 아닌 곳에서 인자 없이 `vg review`를 실행했다 |  | basis D5 | A4 |  | f28d95ec | 3-vg-review-command.md |
| F7 | 드리밍·facts 자식 세션 안에서 실행됐다 |  | basis D5, X9 | A4 |  | bfb14984 | 3-vg-review-command.md |
| F8 | 연결된 Vault가 없거나, 제안이 없거나, ID가 맞지 않는다 |  | basis D3, D2 | A1 |  | 8d96f354 | 3-vg-review-command.md |
| F9 | 초안을 읽을 수 없는 제안 |  | basis D4, X4 | A2 |  | 3c4fb472 | 3-vg-review-command.md |
| F10 | 수락은 됐지만 색인을 시작하지 못했다 |  | basis D8, X8 | A7 |  | 5762bf71 | 3-vg-review-command.md |
| F11 | 이유 없이 거절하려 한다 |  | basis D6, X2 | A8 |  | dad6a4a5 | 3-vg-review-command.md |
| R1 | 연결된 Vault에 설치된 도구가 vault-builder 체크아웃과 다를 수 있다 |  | basis X2, D9 |  |  | 5b74726b |  |
| R2 | vault-graph의 frontmatter 읽기가 `resolution` 값을 온전히 돌려주는지 확인하지 못했다 |  | basis X6, D7 |  |  | 869d75ef |  |
| R3 | "Published:" 표시도 손으로 적을 수 있다 |  | basis D7 |  |  | f363dd59 |  |
| R4 | 에이전트가 셸로 수락할 수 있다 |  | basis D5, I2 |  |  | da58c7af |  |
| R5 | 배경 색인 잠금을 함께 쓰면 색인이 시작되지 않는 때가 있다 |  | basis D8, X8 |  |  | 54ffe82b |  |
| R6 | 첫 실제 실행의 관찰은 다시 재현하지 않았다 |  | basis X13 |  |  | 24f95456 |  |
| A1 | 프로젝트 폴더에서 연결된 모든 Vault의 제안을 본다 |  | covers D2, D3, I4, F8 |  |  | afbea71b | 3-vg-review-command.md |
| A2 | 바뀌는 글과 근거가 초안 모양별로 나온다 |  | covers D4, F9 |  |  | 07dfc34e | 2-proposal-change-and-resolve-adapter.md, 3-vg-review-command.md |
| A3 | 어댑터는 Vault의 계약 JSON만 읽고 실패를 수락으로 알리지 않는다 |  | covers D9, I5, F2, F3, F4, F5 |  |  | e7684c3f | 2-proposal-change-and-resolve-adapter.md |
| A4 | 대화형은 터미널에서만 묻고 자식 세션에서는 거부한다 |  | covers D5, F6, F7 |  |  | 39286bdb | 3-vg-review-command.md |
| A5 | `review resolve` 실행 코드는 `vg review`에서만 닿는다 |  | covers D1, I1, I2 |  |  | 35db6643 | 3-vg-review-command.md |
| A6 | 미발행 수락은 수락 수와 수락률에서 빠지고 따로 보인다 |  | covers D7, I3, F1 |  |  | b6f5e3e3 | 1-dream-status-published.md |
| A7 | 수락으로 발행된 Vault의 색인이 한 번 시작되고 명령은 기다리지 않는다 |  | covers D8, F10 |  |  | 9a5093c1 | 3-vg-review-command.md |
| A8 | 거절에는 이유가 있어야 하고 수락에는 기본 이유가 들어간다 |  | covers D6, F11 |  |  | 2147f834 | 3-vg-review-command.md |
| A9 | 실제 vault-builder 도구로 수락과 거절이 끝까지 돈다 |  | covers D1, D2, D7, D8, I1, I5 |  |  | f048b215 | 4-review-accept-e2e.md |
| A10 | 규칙 문서와 안내가 여섯째 길과 `vg review`를 적는다 |  | covers D1, D5, D10 |  |  | 0eb97c0d | 5-docs-and-final-check.md |
| A11 | 사람이 터미널에서 명령 하나로 읽고 고른다 |  | covers D2, D4, D5 |  |  | 867e778f | 5-docs-and-final-check.md |
| A12 | 사용자가 준 한계를 지킨다 |  | covers I6 |  |  | ca91b85c | 5-docs-and-final-check.md |
| X1 | Vault의 수락은 pending 항목만 받고, 발행한 뒤 resolution에 "Published:"를 적는다 |  |  |  |  | 164f2348 |  |
| X2 | `review resolve`의 인자와 두 갈래 |  |  |  |  | 76a76d71 |  |
| X3 | 정상 처리는 항목 파일과 `wiki/log.md`를 함께 바꾼다 |  |  |  |  | 10d47601 |  |
| X4 | 검토 항목과 초안 사본의 모양 |  |  |  |  | f7055880 |  |
| X5 | vault-graph가 만드는 초안은 세 가지 모양이다 |  |  |  |  | a001e935 |  |
| X6 | vault-graph는 지금 status 글자만 읽어 수락을 센다 |  |  |  |  | 67c26a83 |  |
| X7 | Vault 명령 실행 어댑터에는 publish와 propose만 있다 |  |  |  |  | 64ea7853 |  |
| X8 | 발행 뒤 색인을 시작하는 기존 방법 두 가지 |  |  |  |  | 8663b716 |  |
| X9 | 자식 세션 표시 환경 변수 |  |  |  |  | 2dba135a |  |
| X10 | 쓰기 길의 수를 적은 문서와 수락 방법을 안내하는 곳 |  |  |  |  | ec6e8aa6 |  |
| X11 | cwd에서 연결 Vault를 찾는 기존 코드와 드리밍 기록 |  |  |  |  | be346330 |  |
| X12 | 실제 Vault 도구로 수락과 거절을 도는 e2e가 이미 있다 |  |  |  |  | a78c324e |  |
| X13 | 2026-11-19 첫 실제 드리밍 실행에서 본 것 |  | basis X1, X6 |  |  | a9a15be6 |  |
<!-- bake: index end -->

## 1. Problem
- 날짜: 2026-11-20
- 상태: 초안 (spec 관문 대기)
- bake task: 20261120-vg-review-dream-status-234b
- 조사: [research/repository.md](research/repository.md)

2026-11-19 첫 실제 드리밍 실행에서 제안 2개가 Vault 검토 대기열에 들어갔고, 사용자가 수락하는 과정에서 네 가지가 드러났다(research의 X13).

1. 문제1 찾기 어렵다: 제안 파일이 저장소 밖 Vault 폴더의 `scratch/review/`에 있다(X4).
2. 문제2 읽기 어렵다: 항목 파일에는 요약만 있고 페이지에 들어갈 글은 옆의 `.draft.json`에 있다. 현재 페이지와 무엇이 달라지는지 보여주는 곳이 없다(X4, X5).
3. 문제3 수락이 어렵고 잘못하기 쉽다: Vault 폴더로 가서 긴 `review resolve` 명령을 쳐야 한다. 파일의 `status`를 손으로 `accepted`로 고치면 발행은 되지 않고, 그 뒤 정상 명령도 거부된다(X1, X3). vault-graph에는 이 명령을 실행하는 코드가 없다(X7).
4. 문제4 수치가 틀린다: `vg dream status`가 파일의 `status`만 읽어, 발행되지 않은 항목을 수락으로 세고 수락률 1.00을 보였다(X6). 드리밍을 기본으로 켤지는 이 수락률로 정하기로 했으므로(docs/DECISIONS.md 2026-11-19) 틀린 수치는 그 판단을 흐린다.

## 2. Intent
사용자 말: "vault-graph의 품질과 사용성을 높이는 방법이라면 허용한다. 결정을 변경해도 좋고, 옵션1,옵션2를 함께 개선합니다."

변경 뒤에 참이어야 하는 것:

- 사용자는 프로젝트 폴더에서 명령 하나로 대기 중인 기억 제안을 읽고 수락하거나 거절한다. Vault 폴더로 이동하거나 파일 경로를 찾지 않는다.
- 수락하기 전에, 어느 페이지의 어떤 글이 어떻게 바뀌는지와 그 근거 인용문을 한 화면에서 본다.
- 수락한 기억은 발행되고, 따로 색인 명령을 치지 않아도 검색과 회상에 나온다.
- `vg dream status`의 수락 수와 수락률은 실제로 발행된 것만 센다. 손으로 고쳐 발행되지 않은 항목은 따로 보이고 고치는 방법이 함께 나온다.
- `[가정]` 수락은 계속 사람이 하는 일이다. 에이전트, 훅, 배경 작업자가 스스로 수락하는 길은 생기지 않는다. 드리밍을 허용한 근거가 "사람이 모든 항목을 승인한다"였기 때문이다.

## 3. Non-goals
- vault-builder 저장소 변경. 손으로 고친 항목을 되돌리는 수리 명령도 Vault 쪽 일이다.
- MCP 도구로 수락하거나 거절하기(옵션3, 사용자가 거부).
- 드리밍 판단 프롬프트, 한도, 기본 꺼짐 설정 변경.
- memory-proposal이 아닌 검토 항목(contradiction, merge, contested-claim, human-lock) 처리. 수만 보여준다.
- 제안 글을 `vg review` 안에서 고쳐서 수락하기. 고치려면 거절하고 다시 제안한다.
- 에이전트가 셸로 `vg review accept`를 치는 것을 기술적으로 막기. 지금 Vault 명령도 같은 상태다.

## 4. Design
용어는 둘로 고정한다. "제안"은 Vault 검토 대기열의 memory-proposal 항목이다. "미발행 수락"은 `status`가 `accepted`인데 `resolution`에 Vault가 적는 "Published:" 표시가 없는 제안이다.

**4.1 명령**

`vg review`는 새 Typer 그룹이다(`src/vault_graph/interface/cli/review_commands.py`, `main.py`에 등록). 공통 옵션은 `--cwd`(기본 현재 폴더), `--graph-home`, `--vault-map`이다.

| 명령 | 하는 일 | Vault를 바꾸는가 |
|---|---|---|
| `vg review` | 터미널에서 제안을 하나씩 보여주고 수락, 거절, 건너뛰기, 종료를 고르게 한다 | 수락·거절을 고를 때만 |
| `vg review list` | Vault별 제안 목록, 미발행 수락 목록, 다루지 않는 다른 검토 항목 수 | 아니다 |
| `vg review show ID` | 제안 하나의 대상 페이지, 요약, 바뀌는 글, 근거 | 아니다 |
| `vg review accept ID [--reason TEXT] [--vault NAME]` | 그 제안을 수락한다 | 그렇다 |
| `vg review reject ID --reason TEXT [--vault NAME]` | 그 제안을 거절한다 | 그렇다 |

`ID`는 항목의 `review_id`(파일 이름에서 `.md`를 뺀 것)다.

**4.2 코드 경계**

| 파일 | 역할 |
|---|---|
| `interface/cli/review_commands.py` (새 파일) | 명령, 터미널 입출력, 자식 세션 거부, 수락 뒤 색인 시작 |
| `interface/composition/adapters/vault_review_queue.py` | 읽기 전용. 제안 목록 읽기와 상태 판정을 더한다. 기존 `pending_proposals`, `review_item_status`의 뜻은 그대로 둔다 |
| `interface/composition/adapters/vault_review_cli.py` (새 파일) | `review resolve <path> --status <s> --resolution <text> --json`을 실행하고 `vault-review-result/v1` 객체만 읽는다. 실행 방식은 `VaultPublishCli`와 같다 |
| `operation/memory/proposal_change.py` (새 파일, M18) | 초안과 현재 페이지 글을 받아 "바뀌는 글"을 만드는 순수 함수. 파일을 읽지 않는다 |
| `interface/cli/dream_commands.py`의 `_echo_runs` | 상태 판정을 써서 수락과 미발행 수락을 나눠 센다 |

상태 판정의 서명은 `review_item_state(vault_root: Path, review_path: str) -> str`이고 값은 `pending`, `accepted`, `unpublished`, `rejected`, `resolved`, `missing` 가운데 하나다.

**4.3 문서**

`AGENTS.md`, `docs/SPEC.md` 원칙4·§4·§5, `docs/ARCHITECTURE.md` §4와 모듈 표, `docs/DECISIONS.md`(새 항목), `README.md`, `docs/FEATURES.md`를 고친다.

### I1. vault-graph 프로세스는 검토 흐름에서도 Vault 파일을 직접 쓰지 않는다
- by: 사람 (AGENTS.md Project Boundary, docs/SPEC.md 원칙4)
- area: global
- basis: X3

`vg review`와 `vg dream status`는 Vault 파일을 읽기만 한다. 항목의 `status`, `resolution`, 위키 페이지, `wiki/log.md`를 바꾸는 것은 vault-graph가 하위 프로세스로 실행한 Vault 도구뿐이다. 미발행 수락을 pending으로 되돌리는 일도 vault-graph가 하지 않는다.

### I2. `review resolve`는 `vg review` 명령에서만 실행된다
- by: 가정 (brief의 가정을 불변식으로 적음)
- area: global
- basis: X7, X9

`vault_review_cli.py`를 가져오는 곳은 `interface/cli/review_commands.py` 하나다. `interface/mcp/`, 훅 명령, 드리밍 작업자, facts 작업자, 색인, 회상은 가져오지 않고 실행하지 않는다. MCP 도구 목록에 수락·거절 도구는 없다.

### I3. 수락 수와 수락률에는 발행된 수락만 들어간다
- by: 사람 (brief 옵션2)
- basis: X1, X6

`vg dream status`의 `accepted`와 `acceptance_rate`는 상태가 `accepted`인 제안만 센다. `unpublished`는 분자에도 분모에도 넣지 않는다.

### I4. 보기와 건너뛰기는 아무것도 바꾸지 않는다
- by: 가정 (목록·상세·건너뛰기를 읽기 전용으로 둠)

`vg review list`, `vg review show`, 대화형 흐름의 건너뛰기와 종료는 Vault에도 Graph Home에도 쓰지 않는다. 건너뛴 제안은 다음 실행에 다시 나온다.

### I5. Vault가 처리했다고 답한 것만 수락·거절로 알린다
- by: 가정 (Vault 결과 객체만 믿음)
- basis: X2

`vg review`는 Vault 결과의 `status`가 `resolved`일 때만 "수락됨" 또는 "거절됨"을 출력한다. 색인은 수락 결과에 `written_paths`가 하나 이상 있을 때만 시작한다. 그 밖의 모든 결과는 실패로 출력하고 종료 코드는 1이다.

### I6. 이 변경은 vault-builder 저장소와 기존 MCP 도구를 바꾸지 않는다
- by: 사람 (brief 범위 밖, 브랜치 지시)
- area: global

vault-builder 저장소에는 커밋이 없다. MCP 도구의 이름, 수, 입력 필드는 그대로다. 작업은 `feat/jh/agent-memory-dream` 브랜치에서 하고 새 브랜치를 만들지 않는다.

## 5. Decisions
### D1. `review resolve`를 여섯째 Vault 쓰기 길로 더한다
- by: 사람 (2026-11-20 spec gate: "허용하고 구현 시작")
- status: decided
- area: global
- basis: X2, X7, X10, I2

vault-graph가 Vault의 `review resolve`를 하위 프로세스로 실행하는 길을 더한다. 조건은 하나다. 사람이 친 `vg review` 명령에서만 실행한다. 지금 규칙은 길이 다섯이고 승인은 사람이 Vault 명령으로 한다고 적으므로 규칙 문서를 고쳐야 한다. 드리밍 spec의 "새 쓰기 경로는 없다"는 드리밍 작업자에 대해서는 그대로 참이고, 제품 전체의 길 수만 여섯으로 바뀐다.

### D2. 명령은 대화형 하나와 비대화형 넷이다
- by: 사람 (brief 옵션1), 가정 (`list`와 `show`를 더함, ID는 `review_id`)
- status: decided
- basis: X4
- depends: D1

설계 4.1의 표대로 둔다. `list`와 `show`는 비대화형 `accept`·`reject`에 줄 ID를 찾고 내용을 읽는 데 필요해서 더했다. 대화형 흐름은 Vault 이름, `review_id` 순서로 제안을 하나씩 보여주고 a(수락), r(거절), s(건너뛰기), q(종료)를 받는다. 끝나면 수락, 거절, 건너뜀 수를 한 줄로 낸다.

### D3. cwd 프로젝트에 연결된 모든 Vault를 본다
- by: 사람 (brief 옵션1 "연결된 모든 Vault"), 가정 (Graph Home에 등록되지 않은 Vault도 포함)
- status: decided
- basis: X11

`vault-map.json`에서 cwd의 프로젝트에 연결된 Vault 전부의 `scratch/review/`를 읽는다. 검토에는 Vault 폴더만 있으면 되므로 Graph Home 등록 여부는 보지 않는다. Vault 종류를 코드에 적지 않는다. 같은 `ID`가 두 Vault에 있으면 `--vault NAME`을 요구한다.

### D4. 제안마다 대상, 요약, 바뀌는 글, 근거를 보여준다
- by: 사람 (brief 옵션1), 가정 (초안 모양별 표시 규칙)
- status: decided
- basis: X4, X5, I4

보여주는 것은 Vault 이름, `target_path`, 항목의 `summary`, 만든 날, 바뀌는 글, 근거 줄이다. 바뀌는 글은 초안 모양에 따라 정한다.

1. `upsert-page`이고 대상 페이지가 없으면 새 페이지 전체(frontmatter와 본문)를 보여준다.
2. `upsert-page`이고 대상 페이지가 있으면 본문의 줄 단위 diff와, 값이 달라지는 frontmatter 키의 이전 값과 새 값을 보여준다.
3. `patch-page`이면 초안에 적힌 대로 보여준다. 바꿀 frontmatter 키와 값, 그리고 edit마다 종류와 내용(주장 교체는 옛 주장, 새 주장, 근거)이다. 결과 페이지를 vault-graph가 계산하지 않는다. Vault의 patch 규칙을 다시 구현하면 두 구현이 어긋날 수 있기 때문이다.

근거 줄은 `upsert-page` 본문의 "- Evidence:" 줄과 edit의 `evidence` 값이다. 드리밍 제안에서는 이 줄에 세션 위치와 사용자 인용문이 들어 있다.

### D5. 에이전트가 스스로 수락하는 길을 세 가지로 줄인다
- by: 사람 (2026-11-20 spec gate: 비대화형 수락 명령을 "둔다")
- status: decided
- basis: X9, I2
- depends: D1, D2

1. MCP에 수락·거절 도구를 두지 않는다.
2. 대화형 `vg review`는 표준 입력과 표준 출력이 둘 다 터미널일 때만 묻는다.
3. `VAULT_GRAPH_FACTS_CHILD=1`이면 `vg review`의 모든 하위 명령이 아무것도 하지 않고 종료 코드 1로 끝난다.

비대화형 `accept`와 `reject`는 스크립트와 테스트를 위해 둔다. 에이전트가 셸에서 이 명령을 치는 것은 막지 못한다. 이 한계를 `docs/DECISIONS.md` 새 항목에 적는다.

### D6. 거절 이유는 필수이고 수락 이유에는 기본 문구가 있다
- by: 가정 (Vault 명령이 비어 있지 않은 resolution을 요구함)
- status: decided
- basis: X2

`reject`는 `--reason`이 필수다. 대화형 거절은 이유를 묻는다. `accept`의 `--reason` 기본값은 "Accepted in vg review."이고 대화형 수락은 이유를 묻지 않는다.

### D7. 수락은 "Published:" 표시가 있을 때만 수락으로 센다
- by: 사람 (brief 옵션2), 가정 (상태 이름, 안내 문구, 되돌리지 않음)
- status: decided
- basis: X1, X3, X6, I1, I3

상태 판정은 `status`가 `accepted`이고 `resolution`에 "Published:"가 있으면 `accepted`, 없으면 `unpublished`를 돌려준다. `vg dream status`의 줄은 `proposals: sent=N accepted=A rejected=R pending=P unpublished=U other=O`가 되고, 미발행 수락마다 Vault 이름, 항목 경로, 고치는 방법을 한 줄씩 낸다. `vg review list`도 미발행 수락을 따로 묶어 같은 안내와 함께 보여준다. 고치는 방법은 "항목 파일의 `status`를 `pending`으로, `resolution`을 빈 값으로 되돌린 뒤 `vg review`로 수락한다"이다. 되돌리는 것은 사람이 한다.

### D8. 수락으로 발행되면 그 Vault의 색인을 분리된 프로세스로 시작한다
- by: 사람 (brief 옵션1 "색인을 배경에서 시작"), 가정 (시작 방법과 시점)
- status: decided
- basis: X8, X11, I5

`vg review`는 곧 끝나는 프로세스라서 MCP 서버의 스레드 방식은 쓸 수 없다. 기존 `start_catch_up_index`로 분리된 프로세스를 띄운다. 한 번의 명령 실행에서 발행이 있었던 Vault를 모아 끝날 때 한 번 시작한다. 명령은 색인을 기다리지 않는다. Graph Home에 등록되지 않은 Vault는 색인하지 않고 그 사실을 한 줄로 알린다.

### D9. Vault의 답을 그대로 전하고 다음 할 일을 한 줄 붙인다
- by: 가정 (brief의 가정: target_hash 거부 메시지를 그대로 보여줌)
- status: decided
- basis: X1, X2, X7, I5

어댑터는 계약 JSON의 `status`, `reason`, `written_paths`, `messages`만 읽는다. 실패하면 `messages`를 그대로 출력하고 reason에 따라 안내를 붙인다. `target-changed`면 "거절한 뒤 다시 제안한다", 종료 코드 2면 Vault 도구를 계약 4로 올리라는 기존 안내다. 시간 한도는 `PUBLISH_TIMEOUT_SECONDS`를 쓴다.

### D10. 수락 방법을 안내하는 글을 `vg review`로 바꾼다
- by: 가정 (안내 문구가 새 명령을 가리켜야 쓰임)
- status: decided
- basis: X10
- depends: D1, D7

`vg dream status`의 대기 한도 안내, `README.md`, `docs/FEATURES.md`가 `vg review`를 가리키게 한다. MCP 쓰기 도구의 `proposed` 메시지와 MCP 서버 안내에는 "사람이 프로젝트 폴더에서 `vg review`를 실행한다"는 줄을 더하고 기존 Vault 명령 줄은 남긴다. 규칙 문서(`AGENTS.md`, SPEC 원칙4·§4, ARCHITECTURE §4)의 길 수를 여섯으로 고치면서 SPEC §4 목록에 빠져 있던 사실 첨부도 넣어 세 문서를 맞춘다.

## 6. Failure and boundary behavior
### F1. 파일의 status만 손으로 accepted로 고친 제안
- basis: D7, X1, X3

상태는 `unpublished`다. `vg dream status`는 수락 수와 수락률에서 빼고 따로 센다. `vg review list`는 따로 묶어 보여준다. 둘 다 고치는 방법을 낸다. `vg review accept`에 그 ID를 주면 Vault를 실행하지 않고 같은 안내를 낸 뒤 종료 코드 1로 끝난다.

### F2. 제안 뒤에 대상 페이지가 바뀌었다
- basis: D9, X1

Vault가 reason `target-changed`로 거부하고 제안은 pending으로 남는다. `vg review`는 Vault 메시지와 "거절한 뒤 다시 제안한다"는 안내를 내고, 대화형 흐름은 같은 제안에서 다시 고르게 한다.

### F3. Vault 검증이 수락이나 거절을 막는다
- basis: D9, X2

수락에서 발행이 거부되거나(lint 실패 등), 거절에서 Vault lint가 이미 깨져 있으면 제안은 pending으로 남는다. `vg review`는 Vault 메시지를 그대로 내고 실패로 알린다. 거절이 lint에 막힐 때 Vault 도구가 자기 lint 보고서를 Vault에 쓰는 것은 Vault 도구의 동작이다.

### F4. Vault 도구가 없거나 `review resolve --json`을 모른다
- basis: D9, X7

`tools/wiki/cli.py`가 없으면 그 사실을, 종료 코드 2면 계약 4로 올리라는 안내를 낸다. 목록과 상세 보기는 Vault 도구 없이도 동작한다.

### F5. Vault 명령이 시간 한도를 넘겼다
- basis: D9, X7

결과를 알 수 없다고 알리고 `vg review list`와 Vault의 git 상태를 확인하라고 안내한다. 수락됨으로 알리지 않고 색인도 시작하지 않는다.

### F6. 터미널이 아닌 곳에서 인자 없이 `vg review`를 실행했다
- basis: D5

묻지 않는다. `vg review list`와 같은 목록을 내고, 대화형 검토에는 터미널이 필요하다는 줄을 덧붙인 뒤 종료 코드 0으로 끝난다.

### F7. 드리밍·facts 자식 세션 안에서 실행됐다
- basis: D5, X9

`VAULT_GRAPH_FACTS_CHILD=1`이면 Vault를 읽지도 실행하지도 않고 한 줄 이유와 함께 종료 코드 1로 끝난다.

### F8. 연결된 Vault가 없거나, 제안이 없거나, ID가 맞지 않는다
- basis: D3, D2

cwd에 연결된 Vault가 없으면 `vg setup`을 안내하고 종료 코드 1이다. 대기 제안이 없으면 "대기 중인 제안 없음"을 내고 0이다. ID가 없으면 1이고, 두 Vault에 있으면 후보 Vault 이름을 내고 `--vault`를 요구하며 1이다.

### F9. 초안을 읽을 수 없는 제안
- basis: D4, X4

`.draft.json`이 없거나 JSON이 아니거나 `operation`이 알 수 없는 값이면 목록에 "초안을 읽을 수 없음"과 이유를 붙여 보여준다. 바뀌는 글을 볼 수 없으므로 수락은 받지 않는다. 거절과 건너뛰기는 받는다.

### F10. 수락은 됐지만 색인을 시작하지 못했다
- basis: D8, X8

다른 배경 색인이 잠금을 쥐고 있거나 Vault가 Graph Home에 등록되지 않았으면 수락 결과는 그대로 두고 `vg index --vault-id ID`를 안내한다. 종료 코드는 0이다.

### F11. 이유 없이 거절하려 한다
- basis: D6, X2

`vg review reject`에 `--reason`이 없거나 공백뿐이면 Vault를 실행하지 않고 사용법 오류로 끝난다. 대화형 거절에서 빈 이유를 넣으면 거절하지 않고 같은 제안의 선택으로 돌아간다.

## 7. What could be wrong
### R1. 연결된 Vault에 설치된 도구가 vault-builder 체크아웃과 다를 수 있다
- basis: X2, D9

`review resolve --json`과 결과 필드는 vault-builder 체크아웃에서 확인했다. 사용자의 실제 Vault에 복사된 `tools/wiki/`가 같은 판인지는 확인하지 못했다. 다르면 수락이 종료 코드 2로 끝나고 계약 4 안내가 나온다.

### R2. vault-graph의 frontmatter 읽기가 `resolution` 값을 온전히 돌려주는지 확인하지 못했다
- basis: X6, D7

`resolution` 값에는 콜론과 쉼표가 들어가 Vault가 따옴표로 감싸 쓸 수 있다. `parse_vault_frontmatter`가 이 줄을 잘라 읽으면 발행된 수락이 `unpublished`로 보인다. 실제 Vault 도구가 쓴 항목 파일로 테스트해야 한다.

### R3. "Published:" 표시도 손으로 적을 수 있다
- basis: D7

사람이 `status`와 함께 `resolution`에 그 글자까지 적으면 수락으로 센다. 표시가 가리키는 페이지가 있는지는 확인하지 않는다. 실수로 일어날 일은 아니라고 보고 받아들인다.

### R4. 에이전트가 셸로 수락할 수 있다
- basis: D5, I2

Claude Code가 Bash로 `vg review accept ID`를 치면 사람 없이 수락된다. 자식 세션 환경 변수는 드리밍과 facts가 띄운 세션만 막는다. 지금도 에이전트는 Vault의 `review resolve`를 같은 방법으로 칠 수 있다.

### R5. 배경 색인 잠금을 함께 쓰면 색인이 시작되지 않는 때가 있다
- basis: D8, X8

세션 시작 때 띄운 배경 색인이 아직 돌고 있으면 `start_catch_up_index`가 새로 띄우지 않는다. 그 색인이 이미 이 Vault를 지나갔다면 수락한 페이지는 다음 세션 시작이나 손으로 친 `vg index`까지 검색에 나오지 않는다. 이 함수가 돌려주는 대기 장치를 `vg review`에서 바로 풀어도 되는지는 코드로만 읽었고 실행해 보지 않았다.

### R6. 첫 실제 실행의 관찰은 다시 재현하지 않았다
- basis: X13

발견8~발견11은 brief에 적힌 사용자 관찰이다. 거부 문구와 수락률 계산이 코드와 맞는 것만 확인했다.

## 8. Acceptance criteria
### A1. 프로젝트 폴더에서 연결된 모든 Vault의 제안을 본다
- covers: D2, D3, I4, F8
- check: tests/test_cli_review.py
- evidence:

Vault 두 개가 연결된 프로젝트에서 `vg review list`가 두 Vault의 제안을 Vault 이름과 함께 내고, memory-proposal이 아닌 항목은 수로만 낸다. `list`와 `show` 전후로 두 Vault와 Graph Home의 모든 파일 sha256이 같다. 연결 Vault 없음, 제안 없음, 없는 ID, 두 Vault에 있는 ID가 정해진 메시지와 종료 코드를 낸다.

### A2. 바뀌는 글과 근거가 초안 모양별로 나온다
- covers: D4, F9
- check: tests/test_proposal_change.py, tests/test_cli_review.py
- evidence:

새 페이지 초안은 전체 글, 기존 페이지 `upsert-page`는 본문 diff와 달라지는 frontmatter 키, 폐기 초안은 바뀌는 frontmatter 키, 주장 교체 초안은 옛 주장·새 주장·근거가 나온다. 한국어 본문과 인용문이 깨지지 않는다. 초안이 없거나 깨진 제안은 이유와 함께 목록에 나오고 수락이 거부된다.

### A3. 어댑터는 Vault의 계약 JSON만 읽고 실패를 수락으로 알리지 않는다
- covers: D9, I5, F2, F3, F4, F5
- check: tests/test_vault_review_cli.py
- evidence:

대역 `cli.py`로 resolved, `target-changed`, 발행 거부, 종료 코드 2, JSON이 아닌 출력, 시간 초과, 파일 없음을 만들고 결과 종류와 메시지를 확인한다. 실행 인자가 `review resolve <path> --status <s> --resolution <text> --json`이고 작업 폴더가 Vault 폴더임을 확인한다.

### A4. 대화형은 터미널에서만 묻고 자식 세션에서는 거부한다
- covers: D5, F6, F7
- check: tests/test_cli_review.py
- evidence:

터미널이 아닌 입력으로 `vg review`를 실행하면 목록만 나오고 Vault 명령이 실행되지 않는다. `VAULT_GRAPH_FACTS_CHILD=1`에서 `list`, `show`, `accept`, `reject`, 인자 없는 실행이 모두 종료 코드 1이고 Vault 명령이 실행되지 않는다.

### A5. `review resolve` 실행 코드는 `vg review`에서만 닿는다
- covers: D1, I1, I2
- check: tests/test_review_write_boundary.py
- evidence:

소스의 import를 읽어 `vault_review_cli`를 가져오는 모듈이 `interface/cli/review_commands.py` 하나임을 확인한다. MCP 도구 이름 목록에 수락·거절 도구가 없음을 확인한다. `review_commands.py`, `vault_review_queue.py`, `proposal_change.py`에 파일을 쓰는 호출이 Vault 경로를 향하지 않음을 대역 어댑터로 돌린 수락·거절 전후의 Vault 파일 sha256으로 확인한다.

### A6. 미발행 수락은 수락 수와 수락률에서 빠지고 따로 보인다
- covers: D7, I3, F1
- check: tests/test_vault_review_queue.py, tests/test_cli_dream_status_published.py
- evidence:

드리밍 제안 기록 세 개(발행된 수락, 손으로 고친 수락, 거절)로 `vg dream status`가 `accepted=1 rejected=1 unpublished=1`과 수락률 0.50을 내고, 미발행 수락의 Vault 이름·경로·고치는 방법을 낸다. `vg review list`도 그 항목을 따로 묶어 보여주고, `vg review accept`는 Vault를 실행하지 않고 안내를 낸다.

### A7. 수락으로 발행된 Vault의 색인이 한 번 시작되고 명령은 기다리지 않는다
- covers: D8, F10
- check: tests/test_cli_review.py
- evidence:

한 Vault에서 두 제안을 수락한 실행이 색인 시작을 그 Vault에 대해 한 번 부른다. 거절만 한 실행과 실패한 수락은 부르지 않는다. 시작하지 못한 경우와 등록되지 않은 Vault에서는 `vg index` 안내가 나오고 종료 코드가 0이다.

### A8. 거절에는 이유가 있어야 하고 수락에는 기본 이유가 들어간다
- covers: D6, F11
- check: tests/test_cli_review.py
- evidence:

`reject`에 이유가 없거나 공백뿐이면 Vault 명령이 실행되지 않는다. 이유 없는 `accept`는 기본 문구를 `--resolution`으로 넘긴다.

### A9. 실제 vault-builder 도구로 수락과 거절이 끝까지 돈다
- covers: D1, D2, D7, D8, I1, I5
- check: tests/e2e/test_review_accept.py
- evidence:

기존 e2e와 같은 방법으로 실제 Vault 도구를 쓰는 Vault를 만든다. 추론 제안 둘을 올린 뒤 `vg review accept`로 하나를 수락하면 대상 페이지가 생기고 항목 `resolution`에 "Published:"가 있으며 상태 판정이 `accepted`다. 그 뒤 색인이 끝나면 그 페이지가 검색에 나온다. `vg review reject --reason`으로 다른 하나를 거절하면 페이지는 생기지 않는다. 셋째 항목의 `status`를 테스트가 손으로 `accepted`로 고치면 상태 판정이 `unpublished`다.

### A10. 규칙 문서와 안내가 여섯째 길과 `vg review`를 적는다
- covers: D1, D5, D10
- check: 수동: AGENTS.md, docs/SPEC.md 원칙4·§4·§5, docs/ARCHITECTURE.md §4, docs/DECISIONS.md, README.md, docs/FEATURES.md를 읽고 길 수와 조건, 한계, 명령 안내가 서로 맞는지 본다
- evidence:

세 규칙 문서가 같은 여섯 길을 같은 순서로 적는다. DECISIONS 새 항목에 조건(사람이 친 `vg review`에서만)과 한계(셸로 치는 에이전트는 막지 못함)가 있다. `vg dream status`의 대기 한도 안내와 README가 `vg review`를 가리킨다.

### A11. 사람이 터미널에서 명령 하나로 읽고 고른다
- covers: D2, D4, D5
- check: 수동: 대기 제안이 있는 프로젝트 폴더의 터미널에서 vg review를 실행해 하나를 수락하고 하나를 건너뛴 뒤 vg dream status를 본다
- evidence:

Vault 폴더로 이동하거나 파일 경로를 입력하지 않고 끝난다. 건너뛴 제안은 다음 실행에 다시 나온다.

### A12. 사용자가 준 한계를 지킨다
- covers: I6
- check: 수동: ruff, mypy, 전체 테스트를 실행하고 git 브랜치와 vault-builder 저장소의 변경 여부를 본다
- evidence:

ruff, mypy, 전체 테스트가 통과한다. 커밋은 `feat/jh/agent-memory-dream`에만 있다. vault-builder 저장소에 변경이 없다. MCP 도구 수와 이름이 그대로다.

## 9. Open decisions

남은 것이 없다. 2026-11-20 spec gate에서 사람이 정했다.

- 규칙 변경(D1): 허용하고 구현을 시작한다.
- 비대화형 수락 명령(D5): 둔다.
- 손으로 고친 항목(D7)과 안내 문구(D10)는 권고대로 간다. 사람이 spec 전체를 승인했다.
