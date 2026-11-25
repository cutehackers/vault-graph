# vault-graph 의도 재정의와 기억 층·질의 재설계

<!-- bake: index -->
| ID | title | status | relations | covered by | area | hash | tasks |
|---|---|---|---|---|---|---|---|
| I1 | 기록 층은 한 번 쓰면 바뀌지 않는다 |  | basis X16 | A2 | global | 666c50b3 | 1-spec-intent-layers.md |
| I2 | 모든 기억 단위는 상태 하나와 날짜를 가진다 |  |  | A2 | global | 2aa7d8b7 | 1-spec-intent-layers.md |
| I3 | 질의 때 LLM을 부르지 않는다 |  | basis X22 | A2 | global | 01dfa093 | 1-spec-intent-layers.md |
| I4 | 현재 상태 층은 저장하지 않는다 |  |  | A3 | 기억 층 | f89c836a | 1-spec-intent-layers.md |
| I5 | 층마다 결과 목록을 따로 낸다 |  | basis X4, X6 | A5 | 질의 | 74fb97af | 3-todo-directions.md |
| I6 | 저장 경계는 바뀌지 않는다 |  |  | A2 | global | 2b7ad612 | 1-spec-intent-layers.md |
| I7 | 개념 사전과 코드 앵커는 다시 만들 수 있는 파생 데이터다 |  | basis I6 | A5 | 질의, 코드 앵커 | 195d56a7 | 3-todo-directions.md |
| D1 | SPEC §0 의도를 의도1~5로 바꾼다 | decided | basis I1, I2, I3, I6 | A2 | global, SPEC | 3f9f7959 | 1-spec-intent-layers.md |
| D2 | 기억 층 기록·관측·지식·현재 상태가 L1/L2/L3를 대신한다 | decided | basis I1, I4, X29 | A3 | global, 기억 층 | 696d7a0d | 1-spec-intent-layers.md |
| D3 | 질의는 개념 사전을 거쳐 층별로 답한다 | proposed | basis I3, I5, X1, X3, X4, X22 | A5 | 질의 | 435dee04 | 3-todo-directions.md |
| D4 | 관측 층을 모든 세션에 채운다(3a, 3b, 3d) | proposed | basis X9, X10, X11, X12, X14 | A5 | 관측 층, 사실 추출 | 52952fa8 | 3-todo-directions.md |
| D5 | 사실 계약 v2에 종류와 개념 태그를 더한다(3c) | decided | basis I6, X13; depends D4 | A4 | 관측 층, 사실 추출, vault-builder | 72a0ec50 | 2-decisions-agents.md |
| D6 | 추출기 기본값을 `auto`로 하고 사용자에게 보인다(3e) | decided | basis X17, X19, X28 | A4 | 사실 추출 | 4e1f22ea | 2-decisions-agents.md |
| D7 | 관측과 지식에 코드 앵커를 단다(4a, 4b, 4c, 4e) | proposed | basis I7, X13, X21; depends D5, D9 | A5 | 코드 앵커, 질의 | b38ecf10 | 3-todo-directions.md |
| D8 | 프롬프트마다 강하게 걸릴 때만 기억을 넣는다(4d, 옵션A) | decided | basis I3, X27; depends D3, D7 | A4 | 전달, 코드 앵커 | 573eec03 | 2-decisions-agents.md |
| D9 | `explore_project`는 등록 없이 cwd의 git 저장소를 본다 | decided | basis I6, X20 | A4 | 코드 앵커, explore_project | 0497f644 | 2-decisions-agents.md |
| D10 | 이번 change는 문서만 바꾸고, 개선 방향은 방향마다 나중 spec으로 한다 | proposed | depends D3, D4, D5, D6, D7, D8, D9, D15 | A1 | global | b00375fe | 5-delete-and-verify.md |
| D11 | SPEC은 §0, 원칙1, 옛 층 이름, 보관 문서 링크만 고친다 | proposed | basis X23, X24, X25; depends D1, D2, D6, D15, D16 | A3 | SPEC | 8f86ad53 | 1-spec-intent-layers.md |
| D12 | DECISIONS에는 사용자가 정한 결정만 더하고 옛 층 두 항목에 대체 표시를 단다 | proposed | basis X25, X29; depends D1, D2, D5, D6, D8, D9 | A4 | DECISIONS | 789da4e0 | 2-decisions-agents.md |
| D13 | TODO에 개선 방향을 열린 일로 적는다 | proposed | basis X24, X27; depends D3, D4, D5, D6, D7, D8, D9, D10, D11 | A5 | TODO | f691fd1d | 3-todo-directions.md |
| D14 | 설계 용어집은 고치지 않는다 | proposed | basis X26 | A11 | 문서 정리 | 8eab7c9f | 5-delete-and-verify.md |
| D15 | 옛 설계 문서 네 묶음을 지운다 | decided | basis X24, X25 | A6 | 문서 정리 | 3d5f0fe5 | 5-delete-and-verify.md |
| D16 | 10월 모듈 설계 묶음(`docs/design/specs/`, `plans/`, `intents/`)은 남긴다 | decided | basis X24 | A8 | 문서 정리 | 9139de01 | 5-delete-and-verify.md |
| D17 | 개선 구조를 HTML 한 파일로 그려 `docs/html/`에 둔다 | decided | basis I1, I3, I4 | A10 | 문서 정리, HTML | 0a5511a2 | 4-html-finish.md |
| D18 | AGENTS.md는 Project Boundary 첫 문장만 이번에 고친다 | decided | basis I6, X30 | A11 | 문서 정리, AGENTS | ed1e3bfb | 2-decisions-agents.md |
| D19 | 세션 시작 회상의 추출기 줄은 매 세션 낸다 | decided | depends D6 | A12 | 사실 추출, 회상 | a6249b20 | 3-todo-directions.md |
| F1 | 현재 문서에 지운 폴더 링크가 남는다 |  | basis D15, X24 | A7 |  | 2a78e892 | 5-delete-and-verify.md |
| F2 | 이력 문서 속 지운 경로는 그대로 둔다 |  | basis D15, D16, X24 | A7 |  | 1855eac4 | 5-delete-and-verify.md |
| F3 | 코드 출력과 SPEC 용어가 한동안 다르다 |  | basis D11, X23 | A3 |  | 55782d77 | 1-spec-intent-layers.md |
| F4 | 문서를 읽는 테스트가 깨진다 |  | basis D11, D12, X25 | A9 |  | f10ac94f | 5-delete-and-verify.md |
| F5 | SPEC 본문의 "§0 규칙N" 참조가 옛 번호를 가리킨다 |  | basis D1, D11 | A3 |  | 9cd9bb2a | 1-spec-intent-layers.md |
| F6 | `auto`인데 llama-server가 답하지 않는다 |  | basis D6, X19 | A5 |  | 1711b2be | 3-todo-directions.md |
| F7 | 질의가 어떤 개념에도 걸리지 않는다 |  | basis D3, I3 | A5 |  | f1978493 | 3-todo-directions.md |
| F8 | 주장의 commit 뒤로 그 경로의 코드가 바뀌었다 |  | basis D7, D9 | A5 |  | bb32e69e | 3-todo-directions.md |
| F9 | cwd가 git 저장소 밖이다 |  | basis D9 | A5 |  | d5c28c59 | 3-todo-directions.md |
| R1 | v1 원본 일부가 3a 전에 지워질 수 있다 |  | basis X12 |  |  | 833f7a42 |  |
| R2 | 프롬프트 주입은 vault-builder 훅 확장이 있어야 한다 |  | basis X27 |  |  | 5d84f7bf |  |
| R3 | 사실 계약 v2는 vault-builder 변경에 묶인다 |  | basis X13, X29 |  |  | c293628d |  |
| R4 | 로컬 추출기가 긴 part에서 너무 느릴 수 있다 |  | basis X18, X9 |  |  | bc66c38b |  |
| R5 | 문턱 값이 실제 Vault에서 맞지 않을 수 있다 |  | basis X22 |  |  | c376fa07 |  |
| R6 | 보관 문서를 지우면 SPEC §7·§8의 출처를 저장소 안에서 못 본다 |  | basis X24 |  |  | e0f592fb |  |
| A1 | 제품 코드, 테스트, 설정이 바뀌지 않는다 |  | covers D10 |  |  | 5ffa64d0 | 5-delete-and-verify.md |
| A2 | SPEC §0이 의도1~5 다섯 문장을 담는다 |  | covers D1, I1, I2, I3, I6 |  |  | 58a09e8c | 1-spec-intent-layers.md |
| A3 | SPEC에 옛 층 이름이 코드 인용 말고는 없다 |  | covers D2, D11, I4, F3, F5 |  |  | 10047ef4 | 1-spec-intent-layers.md |
| A4 | DECISIONS에 승인된 결정이 들어가고 옛 층 두 항목에 대체 표시가 있다 |  | covers D12, D5, D6, D8, D9 |  |  | 3a7e08e0 | 2-decisions-agents.md |
| A5 | TODO가 개선 방향을 순서대로 열린 일로 적는다 |  | covers D3, D4, D7, D13, I5, I7, F6, F7, F8, F9 |  |  | e0135f33 | 3-todo-directions.md |
| A6 | 네 묶음이 지워졌다 |  | covers D15 |  |  | 8597b2b4 | 5-delete-and-verify.md |
| A7 | 현재 문서에 지운 경로 링크가 없다 |  | covers F1, F2 |  |  | 75076859 | 5-delete-and-verify.md |
| A8 | 10월 모듈 설계 묶음과 그 링크가 살아 있다 |  | covers D16 |  |  | 2e563a88 | 5-delete-and-verify.md |
| A9 | 문서를 읽는 기존 테스트가 통과한다 |  | covers F4 |  |  | e1c88032 | 5-delete-and-verify.md |
| A10 | HTML이 오프라인에서 열리고 다섯 부분을 보인다 |  | covers D17 |  |  | cc8db6c7 | 4-html-finish.md |
| A11 | 고치지 않기로 한 문서가 그대로이고 AGENTS.md는 첫 문장만 바뀌었다 |  | covers D14, D18 |  |  | 2d2d3393 | 5-delete-and-verify.md |
| A12 | 추출기 회상 줄의 빈도가 TODO 3e 항목에 적혀 있다 |  | covers D19 |  |  | f33fb1ac | 3-todo-directions.md |
| O1 | 10월 모듈 설계 문서 세 폴더도 지울까? |  | decides D15, D16 |  |  | 53500251 |  |
| O2 | AGENTS.md 첫 문장은 사람이 나중에 바꿀까? |  | decides D18 |  |  | 66100893 |  |
| O3 | 추출기 상태 줄을 매 세션 보일까, 바뀔 때만 보일까? |  | decides D19 |  |  | 1756e169 |  |
| X1 | 기본 검색 mode `knowledge`는 세션 원문을 후보에서 뺀다 |  |  |  |  | b3457259 |  |
| X2 | `ask_vault`의 검색 단계도 `knowledge` mode로 돈다 |  | basis X1 |  |  | a6e64404 |  |
| X3 | 답변기는 검색된 조각을 모두 `supported`로 표시하고 발췌만 나열한다 |  |  |  |  | 2e811d4d |  |
| X4 | 세션에만 답이 있는 질문에 `vg ask`가 무관한 wiki 조각 11개를 돌려줬다 |  | basis X2, X3 |  |  | 6317bcae |  |
| X5 | 같은 질의를 `evidence` mode로 하면 해당 세션이 3위로 나온다 |  | basis X1 |  |  | 4884eed7 |  |
| X6 | 프로젝트 폴더에서 검색해도 다른 프로젝트 문서가 상위를 차지한다 |  | basis X4, X5 |  |  | b58261f2 |  |
| X7 | 그래프는 제목·링크·frontmatter 관계를 규칙으로 뽑은 것이고 기본 검색에서 꺼져 있다 |  |  |  |  | 63fa0954 |  |
| X8 | vault-graph Vault의 기억은 대부분 세션에 있다 |  |  |  |  | 915f3101 |  |
| X9 | 사실 첨부가 있는 세션 part는 79개 중 9개다 |  | basis X8 |  |  | a2984600 |  |
| X10 | 사실 작업자는 교환 메타가 있는 v2 part만 처리한다 |  |  |  |  | 1f246821 |  |
| X11 | 사실 작업은 수집 훅만 대기열에 넣는다 |  |  |  |  | d36174d1 |  |
| X12 | v1 35개 part의 원본 jsonl은 모두 남아 있다 |  | basis X10 |  |  | 265001dc |  |
| X13 | 교환 메타의 수정 파일 목록은 키워드 열 텍스트로만 색인된다 |  |  |  |  | 558aa372 |  |
| X14 | 세션 원문의 assistant 줄 상당수는 도구 이름 줄이다 |  |  |  |  | b190cb97 |  |
| X15 | wiki 결정은 세션 교환 줄 범위를 근거로 적는다. 근거 원천이 없는 페이지도 있다 |  |  |  |  | 05cd5a8c |  |
| X16 | Vault `raw/`에 쌓이는 원천은 세션, 자동 기억 노트 사본, 외부 문서다 |  |  |  |  | ac91f04a |  |
| X17 | 추출기는 `claude`와 `llama-server` 두 가지이고 설정 파일이 없으면 `claude`다 |  |  |  |  | 27332fdc |  |
| X18 | 짧은 세션 기준 추출 시간은 Claude 약 6.5초, 로컬 Qwen3.5 27B 약 14초(사고 끔)다 |  | basis X9 |  |  | fa1eee4a |  |
| X19 | 이 Mac에는 llama-server와 모델 파일이 있지만 서버는 꺼져 있다 |  | basis X17 |  |  | b96f1440 |  |
| X20 | 등록된 코드 저장소가 0개라 `explore_project`가 실패한다 |  |  |  |  | e964374d |  |
| X21 | 세션 44개 v2 part의 도구 호출은 Bash 8,368, Read 1,521, Edit 974, Write 595번이다 |  | basis X10 |  |  | 6e00a625 |  |
| X22 | NVIDIA Auto Ontology는 개념 사전·매핑·인증·답 가능성 검사를 두고 질의 때 LLM ReAct로 답한다 |  |  |  |  | 60c17f4e |  |
| X23 | 코드 출력과 입력 값에는 L1 이름이 남아 있고, 회상 제목에는 L3가 없다 |  |  |  |  | 117fea8a |  |
| X24 | 현재 문서가 삭제 후보 폴더를 링크한다 |  |  |  |  | 98b781dd |  |
| X25 | 문서를 읽는 테스트는 넷이다 |  |  |  |  | 787b1042 |  |
| X26 | 설계 용어집은 옛 기억 층을 정의하지 않는다 |  |  |  |  | d5764b91 |  |
| X27 | 훅 실행기는 세 사건만 받고 UserPromptSubmit 처리는 없다 |  |  |  |  | 03398002 |  |
| X28 | `vg facts`는 이미 `--extractor` 선택을 받는다 |  | basis X17 |  |  | 273f2ce5 |  |
| X29 | DECISIONS의 옛 층 결정은 두 항목이고 파일은 영어 형식이다 |  |  |  |  | 2f19a686 |  |
| X30 | AGENTS.md Project Boundary 첫 문장은 vault-graph를 검색·회상 층으로 부른다 |  |  |  |  | de000cac |  |
<!-- bake: index end -->

## 1. Problem

사용자가 세션에서 겪은 일을 물어도 vg는 그 답을 돌려주지 못한다. 2026-11-25에 커밋 `9ddce0c`과 실제 Vault 두 개로 확인한 내용은 `research/findings.md`에 사실로 적었다.

- 답이 세션에만 있는 질문("0.2.0 배포할 때 생긴 문제를 어떻게 해결했지?")에 `vg ask`는 무관한 wiki 조각 11개를 모두 `[supported]`로 돌려줬다(X4). 기본 검색 mode `knowledge`가 `raw/` 세션을 후보에서 빼고(X1, X2), 답변기는 질문과 근거가 맞는지 보지 않는다(X3). `evidence` mode로 바꾸면 그 세션이 3위로 나온다(X5). 프로젝트 폴더에서 물어도 다른 Vault 페이지가 위를 차지한다(X6).
- vault-graph Vault의 기억은 대부분 세션 part 79개에 있고 wiki는 20쪽 남짓이다(X8). 사실 첨부가 있는 part는 9개뿐이다(X9). 사실 작업자는 교환 메타가 있는 v2 part만 처리하고, 이미 저장된 part를 다시 처리하는 명령이 없다(X10, X11). v1 35개 part의 원본은 아직 남아 있지만 Claude Code는 기본 30일 뒤 원본을 지운다(X12).
- 코드를 다룰 때 기억을 찾을 길이 없다. 수정 파일 목록은 키워드 열 문자열로만 색인되고(X13), 등록된 코드 저장소가 없어 `explore_project`가 실패한다(X20). 파일 읽기 상당수가 Bash로 일어난다(X21).
- 설계 문서의 기억 층 L1(자동 기억), L2(Vault 페이지), L3(프로젝트 요약)는 "어디에 저장하나"로 나눈 이름이다. 지금 쓰고 있는 세션 원천, 사실 첨부, 확정 지식, 현재 상태의 구분과 맞지 않는다. 사용자는 이 3계층을 "이질적"이라고 했다. 옛 이름은 SPEC §4·§5·§6과 DECISIONS 두 항목에 남아 있다(X23, X29).
- 문서도 정리가 필요하다. 2026-06~10월의 옛 설계 문서와 같은 내용의 정적 사이트가 `docs/` 아래에 남아 있고, 일부는 현재 문서가 아직 링크한다(X24).

## 2. Intent

사용자는 먼저 vault-graph의 새 의도를 정하고, 그 의도에서 기억 층을 다시 정의하기를 원한다. 아래 다섯 문장이 `docs/SPEC.md` §0을 대신한다(결정1, 2026-11-25 승인). 의도1은 사용자가 원천 저장 형태를 물어 보완한 문장이다.

vault-graph는 지난 작업 경험에서 지금 유효한 뜻을 뽑아, Claude Code가 작업하는 순간에 상태와 출처를 붙여 전달한다. (2026-11-25 대화에서 사용자에게 보인 머리 문장)

1. 의도1 원천은 작업 경험이다. 세션의 대화와 행동, 바뀐 파일, 사용자가 직접 한 말, commit이 원천이다. 원천은 Vault `raw/`에 저장하고(세션, 자동 기억 노트 사본, 외부 문서), commit은 git에 두고 가리키기만 한다. 원천은 한 번 쓰면 바뀌지 않는다. wiki 페이지는 원천에서 뽑아 확정한 지식을 담고, 고치거나 대체하거나 폐기할 수 있다.
2. 의도2 기억은 상태와 시간을 가진다. 모든 기억 단위는 관측, 제안, 확정, 대체됨 중 한 상태와 날짜를 가진다. 질의는 기본으로 지금 유효한 것을 답하고, 요청하면 이력을 답한다.
3. 의도3 뜻은 쓸 때 만들고 읽을 때는 전달만 한다. LLM은 수집 뒤(사실 추출, 드리밍)에만 쓰고 질의 때는 부르지 않는다. vg는 검색 조각이 아니라 정리된 기억 단위를 돌려준다.
4. 의도4 전달 시점은 작업 흐름을 따른다. 세션 시작, 사용자 프롬프트(개념이 강하게 걸릴 때만), 요청할 때 기억을 준다. 파일을 읽거나 고칠 때마다 넣지는 않는다. 코드 경로는 기억을 찾는 일급 열쇠다.
5. 의도5 저장 경계는 그대로다. Vault가 저장소이고, 쓰기는 Vault 도구를 거치며, vg는 다시 만들 수 있는 색인만 가진다. SPEC 원칙2~6은 바뀌지 않는다.

이유: 사용자는 "올바른 메모리 조회 및 결과 제공"과 "session들을 기반으로 하는 메모리 기능에서 있는 데이터는 올바르게 전달"을 원했다. 별도 기억 층의 의미는 "원본 데이터에 대한 3계층 메모리 관리 그리고 올바른 의미전달"에 있고, "claude가 코드를 다룰때 참조하는 방식"도 중요하다고 했다. 그래서 의도는 저장 위치가 아니라 원천, 상태, 전달 시점, 코드 경로로 적는다.

[가정] 다섯 문장은 SPEC §0에 그대로 옮기고, 기존 §0의 여러 Vault 규칙(결정12~15)과 "현재 구현과의 차이"는 그 아래에 남긴다.

## 3. Non-goals

- 이번 change는 제품 코드, 테스트, 설정을 바꾸지 않는다. 개선 방향은 방향마다 나중 spec과 change로 구현한다.
- 출력 문구 "L1 노트", 입력 값 `l1_note`, 함수 이름 `project_l3_list` 같은 코드 속 옛 이름은 바꾸지 않는다. 이름 변경은 구현 spec에서 한다.
- `list_memory_candidates`의 다섯 후보 종류와 정리 흐름은 그대로 동작한다.
- `CLAUDE.md`, `docs/ARCHITECTURE.md`, `docs/FEATURES.md`, README는 고치지 않는다. 이들은 현재 구현을 설명한다. `AGENTS.md`는 Project Boundary 첫 문장만 고친다(D18).
- 질의 때 LLM ReAct로 답하는 NVIDIA Auto Ontology의 질의 방식은 가져오지 않는다.
- 문턱 값(개념 일치 강도, 답 가능성 비율, 주입 200토큰)은 이번에 정하지 않는다. 구현 spec에서 잰다.

## 4. Design

**4.1 기억 층 네 개**

층은 "어디에 저장하나"가 아니라 "기억이 어떤 상태에 있나"로 나눈다. 아래 네 층이 L1/L2/L3를 대신한다(결정2).

| 층 | 담는 것 | 만드는 방법 | 상태 | 위치 |
|---|---|---|---|---|
| 기록 | 세션 교환 원문, 가져온 자동 기억 노트, 외부 문서, commit(가리키기만) | `sessions capture`, `import-source`, ingest | 바뀌지 않음 | Vault `raw/`, commit은 git |
| 관측 | 교환마다 날짜가 붙은 사실. 교환 위치, 종류, 개념 태그, 코드 앵커를 단다 | 사실 작업자가 자동으로 | 관측(검토 전) | `raw/…/*.facts.md` |
| 지식 | 결정, 규칙, 개념을 근거 링크와 대체 링크가 달린 주장으로 | 사용자가 말한 것(stated) 또는 수락된 제안(드리밍, 정리) | 확정, 대체됨 | `wiki/` |
| 현재 상태 | 유효한 결정과 규칙, 열린 일, 최근 관측 | 질의 때 계산 | 저장하지 않음 | 없음 |

옛 L1(자동 기억)은 기록 층의 원천 하나가 된다. 옛 L3 목록은 현재 상태 보기가 된다. 프로젝트 brief는 지식 층 페이지(`type: project`)로 남는다. 의도2의 "제안" 상태는 Vault 검토 대기열에 있는 지식 후보이고, 수락 전에는 회상과 검색에 나오지 않는다. 그래프는 두 가지 일만 한다. 대체 사슬을 따라가는 일과 개념·코드 경로를 잇는 일이다.

**4.2 질의 설계**

질의 때 LLM을 부르지 않는다. NVIDIA Auto Ontology(X22)에서 개념 사전, 매핑, 인증, 답 가능성 검사를 가져오고, 질의 때 추론 모델이 도구를 고르는 방식은 가져오지 않는다.

1. 질의1 개념 사전: 쓸 때 만든다. 개념 이름과 한국어·영어 별칭을 지식 페이지, 관측, 코드 경로에 잇는다. 재료는 페이지 제목과 `aliases`, 사실 추출의 개념 태그, 코드 심볼이다. 새 개념은 `vg review`로 사람이 인증한다.
2. 질의2 해석: 질의 낱말을 개념에 맞춘다(별칭 일치와 개념 이름 임베딩). 질문 종류(현재 상태, 이유, 사건, 코드 위치)는 규칙으로 나누고, 날짜 범위 규칙은 지금 것을 쓴다.
3. 질의3 답 가능성: 질의 핵심 낱말 중 개념에 걸린 비율을 센다. 비율이 낮으면 무관한 페이지 대신 "이 Vault에 그런 개념이 없음"과 가장 가까운 개념을 돌려준다.
4. 질의4 층별 조회: 개념마다 현재 상태, 지식(대체 사슬을 따라 지금 것), 관측(날짜순, 검토 전 표시), 기록 인용 순으로 찾는다. 층마다 목록을 따로 내고 하나의 순위로 섞지 않는다.
5. 질의5 답 단위: 문장, 층, 상태, 날짜, 개념, 코드 앵커, 원천 경로와 줄 범위. 개념별로 묶는다. 원천이 없는 지식(`primary_sources: []`, X15)에는 "출처 원천 없음"을 붙인다.
6. 질의6 대체 길: 개념이 하나도 걸리지 않으면 지금의 하이브리드 검색을 관측과 기록 층에 돌리고 "개념 미연결"을 붙인다.
7. 코드 경로 조회: 경로에서 그 경로에 앵커된 개념과 주장을 찾고 같은 순서로 조회한다. 주장의 commit 뒤로 `git log <commit>..HEAD -- <path>`가 비어 있지 않으면 "코드 바뀜, 다시 확인"을 붙인다.

**4.3 개선 방향과 나중 spec의 수용 기준 초안**

방향마다 나중 spec 하나를 쓴다. 아래 수용 기준 초안은 그 spec이 출발점으로 삼는다.

결정3 관측 층을 모든 세션에 채운다.

- 3a v1 part 35개를 v2로 다시 수집해 교환 메타를 붙인다. 원본이 30일 뒤 지워질 수 있으니 가장 먼저 한다(X12). 초안: v1 part가 0개이고, 다시 수집한 part의 교환 수가 원본과 같다.
- 3b `vg facts backfill`: 사실 파일이 없거나 `source_sha256`이 바뀐 part를 대기열에 넣는다. 지금의 작업자, 잠금, 교환별 캐시를 그대로 쓴다. 초안: 두 번 실행해도 추출 호출이 늘지 않고, 실행 뒤 사실 없는 v2 part가 0개다.
- 3c 사실 계약 v2: LLM이 종류(결정, 변경, 문제, 선호, 질문)와 개념 태그를 단다. 파일과 commit은 교환 메타와 정규식으로 결정적으로 달고 `git cat-file`로 확인한다. vault-builder `attach-facts` 변경이 필요하다. 초안: 확인되지 않은 commit은 첨부에 없고, v1 첨부도 계속 읽힌다.
- 3d 프롬프트에 넣기 전 도구 이름만 있는 줄(`Tools: Bash`)을 뺀다(X14). 초안: 같은 part의 프롬프트 바이트가 줄고 뽑힌 사실 수는 줄지 않는다.
- 3e 추출기 `auto`를 새 기본값으로 한다. `127.0.0.1:8080`이 답하면 llama-server, 아니면 claude를 쓴다. `vg facts on --extractor auto|llama-server|claude`와 `configs/facts.json`으로 바꾼다(X28). `vg facts status`가 설정 값, 지금 고른 추출기, 마지막 작업의 실제 추출기와 모델을 보이고, 세션 시작 회상에 추출기 한 줄(약 15토큰)을 내며, `.facts.md`의 `extractor`, `model` 필드에 남긴다. 초안: 서버를 끄고 켤 때 status 출력이 바뀌고, 첨부 필드가 실제 추출기와 같다.

결정4 코드 앵커를 단다.

- 4a 앵커는 저장소 기준 상대 파일 경로, commit, 심볼(코드 색인이 풀어낼 때만)이다. 파일부터 한다.
- 4b 재료는 교환 메타 `files=`(절대 경로를 git 루트 기준으로 바꿈), 본문에서 찾아 확인한 commit, 지식이 인용한 교환에서 물려받은 앵커다.
- 4c 앵커는 Graph Home의 파생 데이터다(원칙5). 그래프 간선은 개념–경로, 관측–경로, 주장–경로, 대체다.
- 4d 전달은 옵션A다. UserPromptSubmit 때 프롬프트가 개념에 강하게 걸리면 지금 유효한 결정과 규칙을 200토큰 안에서, 묶인 코드 경로와 함께 프롬프트당 한 번 넣는다. 걸리지 않으면 아무것도 넣지 않는다. 파일 읽기·수정마다 넣지 않는다. 당겨 쓰는 도구 `memory_for_path`, `memory_for_concept`를 둔다.
- 4e 신선도는 4.2의 코드 경로 조회 규칙대로 표시한다. 결정5가 먼저 있어야 한다.
- 초안: 경로 하나로 조회하면 그 경로를 바꾼 교환의 관측과 그 관측을 인용한 지식이 나온다. 앵커 데이터를 지우고 색인하면 같은 결과가 나온다. 개념이 걸리지 않는 프롬프트에는 주입 출력이 비어 있다. 주입은 200토큰을 넘지 않는다.

결정5 `explore_project`는 등록 없이 cwd의 git 저장소를 대상으로 한다.

- 초안: 등록 저장소가 0개여도 git 저장소 안의 cwd에서 `explore_project`가 결과를 낸다. cwd가 git 저장소 밖이면 등록 안내가 아니라 "git 저장소가 아님" 오류를 낸다.

**4.4 이번 change의 문서 변경**

`docs/SPEC.md` §0과 §1 원칙1, 옛 층 이름, §7·§8·§10의 보관 문서 링크를 고친다. `docs/DECISIONS.md`에 승인된 결정을 더하고 옛 층 결정 두 항목에 대체 표시를 단다. `docs/TODO.md`에 개선 방향을 열린 일로 적는다. 옛 설계 폴더를 지우고, 개선 구조를 그린 HTML 하나를 `docs/html/`에 둔다. 각각은 §5 결정에 있다.

### I1. 기록 층은 한 번 쓰면 바뀌지 않는다
- by: 사람 (2026-11-25 대화, 의도1 보완 답변)
- area: global
- basis: X16

세션, 자동 기억 노트 사본, 외부 문서는 `raw/`에 쓴 뒤 고치지 않는다. 고치고 대체하고 폐기하는 일은 지식 층 wiki 페이지에서만 한다. commit은 git에 있고 기록 층은 가리키기만 한다.

### I2. 모든 기억 단위는 상태 하나와 날짜를 가진다
- by: 사람 (2026-11-25 대화, 의도2)
- area: global

상태는 관측, 제안, 확정, 대체됨 중 하나다. 질의는 기본으로 지금 유효한 것(확정이면서 대체되지 않은 지식, 그리고 표시를 단 관측)을 답하고, 사용자가 요청할 때만 대체된 것과 이력을 답한다.

### I3. 질의 때 LLM을 부르지 않는다
- by: 사람 (2026-11-25 대화, 의도3)
- area: global
- basis: X22

LLM은 수집 뒤의 사실 추출과 드리밍에서만 쓴다. 검색, 색인, 회상, 프롬프트 주입, 개념 해석, 답 가능성 판단은 규칙과 임베딩만으로 한다. 지금 SPEC 원칙1과 같은 경계다.

### I4. 현재 상태 층은 저장하지 않는다
- by: 사람 (2026-11-25 대화, 결정2)
- area: 기억 층

현재 상태(유효한 결정과 규칙, 열린 일, 최근 관측)는 질의와 회상 때 색인에서 계산하고 Vault에도 Graph Home에도 저장하지 않는다. 옛 L3 목록을 계산하던 규칙을 이어받는다.

### I5. 층마다 결과 목록을 따로 낸다
- by: 가정 (사용자가 보고 거절하지 않은 질의4 제안)
- area: 질의
- basis: X4, X6

현재 상태, 지식, 관측, 기록의 결과를 하나의 관련도 순위로 섞지 않는다. 섞으면 확정 지식과 검토 전 관측, 다른 Vault의 무관한 페이지가 같은 줄에 서서 X4, X6 같은 결과가 다시 나온다.

### I6. 저장 경계는 바뀌지 않는다
- by: 사람 (2026-11-25 대화, 의도5)
- area: global

Vault가 저장소다. vg는 Vault 도구를 실행하는 여섯 쓰기 경로로만 Vault에 쓰고, 기계가 만든 내용은 사실 첨부 말고는 Vault에 쓰지 않는다. vg 쪽에는 다시 만들 수 있는 데이터만 둔다. SPEC 원칙2~6은 그대로다.

### I7. 개념 사전과 코드 앵커는 다시 만들 수 있는 파생 데이터다
- by: 가정 (결정4 세부 4c 제안)
- area: 질의, 코드 앵커
- basis: I6

개념 사전, 코드 앵커, 개념·경로 간선은 Graph Home에 두고 Vault 원천과 git에서 다시 만든다. 지우고 다시 색인하면 같은 결과가 나와야 한다. 사람이 인증한 개념은 Vault 쪽 기록(페이지 `aliases` 등)에 남겨야 다시 만들 수 있다.

## 5. Decisions

앞의 아홉 결정은 설계 결정이고, 나머지는 이번 change의 문서 작업 결정이다. 사용자가 2026-11-25 대화에서 직접 정한 것만 `decided`다.

### D1. SPEC §0 의도를 의도1~5로 바꾼다
- by: 사람 (2026-11-25 대화, 결정1)
- status: decided
- area: global, SPEC
- basis: I1, I2, I3, I6

§2 Intent의 다섯 문장을 SPEC §0 본문으로 옮긴다. §0의 "이 절은 자주 바뀌지 않고 바꿀 때 사용자 확인이 필요하다"는 머리말과 여러 Vault 규칙(결정12~15)은 남긴다. 옛 규칙1~5에서 새 문장에 없는 세부(사용 기록 예외, 수집 실행 시점)는 원칙과 §4에 이미 있으므로 §0에서는 그 절을 가리키기만 한다.

### D2. 기억 층 기록·관측·지식·현재 상태가 L1/L2/L3를 대신한다
- by: 사람 (2026-11-25 대화, 결정2)
- status: decided
- area: global, 기억 층
- basis: I1, I4, X29

§4.1 표가 새 층 정의다. DECISIONS의 2026-11-06 두 항목(L1·L2·L3 관리 이전, L3 목록 계산과 brief)은 이 결정으로 대체된다. 두 항목이 정한 일(정리는 에이전트가 판단, brief는 Vault 페이지, 목록은 계산)은 새 층 이름으로 그대로 유효하다. 바뀌는 것은 층을 나누는 기준과 이름이다.

### D3. 질의는 개념 사전을 거쳐 층별로 답한다
- by: 가정 (사용자가 의도3을 받아들이며 "개선된 형태의 질의를 제안해도 좋다"고 했고, 제안된 질의1~6과 코드 경로 조회를 거절하지 않았다)
- status: proposed
- area: 질의
- basis: I3, I5, X1, X3, X4, X22

§4.2의 질의1~6과 코드 경로 조회를 질의 설계로 삼는다. 지금은 `knowledge` mode가 세션을 빼고(X1) 답변기가 무엇이든 `supported`로 표시해(X3) 엉뚱한 답이 나온다(X4). 개념에 걸리는지 먼저 보고 걸리지 않으면 그렇다고 말하는 편이, 무관한 조각을 근거처럼 내는 것보다 낫다. Auto Ontology(X22)에서 질의 때 LLM을 쓰는 부분은 I3 때문에 버린다.

### D4. 관측 층을 모든 세션에 채운다(3a, 3b, 3d)
- by: 가정 (결정3 세부 제안. 사용자는 세부 설계를 요청했고 3c, 3e만 따로 답했다)
- status: proposed
- area: 관측 층, 사실 추출
- basis: X9, X10, X11, X12, X14

§4.3의 3a, 3b, 3d를 그 순서로 한다. 사실 첨부가 79개 중 9개이고(X9) 작업자는 v2만 처리하며(X10) 다시 처리할 명령이 없다(X11). 3a가 먼저인 것은 원본 보관 기간(X12) 때문이고, 3d는 도구 이름 줄이 많아서다(X14).

### D5. 사실 계약 v2에 종류와 개념 태그를 더한다(3c)
- by: 사람 (2026-11-25 대화, 질문2 승인)
- status: decided
- area: 관측 층, 사실 추출, vault-builder
- basis: I6, X13
- depends: D4

내용은 §4.3의 3c다. 파일과 commit을 LLM에 맡기지 않는 것은 경로를 지어내지 않게 하려는 것이다. 첨부는 지금처럼 Vault `sessions attach-facts`가 쓰므로 vault-builder 계약이 먼저 바뀌어야 한다.

### D6. 추출기 기본값을 `auto`로 하고 사용자에게 보인다(3e)
- by: 사람 (2026-11-25 대화, 질문1과 옵션1, 추출기 상태 표시 요청)
- status: decided
- area: 사실 추출
- basis: X17, X19, X28

내용은 §4.3의 3e다. 사용자는 "로컬 ai가 존재하면 기본으로 이것을 사용하고 아니라면 claude"를, "설정이나 명령어로도 변경가능"하게, 그리고 "로컬 ai인지 아니면 claude 인지" 알 수 있게 해 달라고 했다. 로컬은 끝점이 답할 때만 있는 것으로 본다(옵션1).

### D7. 관측과 지식에 코드 앵커를 단다(4a, 4b, 4c, 4e)
- by: 가정 (결정4 세부 제안. 사용자는 세부 설계를 요청했고 전달 방식 4d만 따로 답했다)
- status: proposed
- area: 코드 앵커, 질의
- basis: I7, X13, X21
- depends: D5, D9

내용은 §4.3의 4a, 4b, 4c, 4e다. 지금은 수정 파일 목록이 키워드 문자열로만 있어(X13) 경로로 기억을 찾지 못한다. Bash로 읽은 파일은 빠질 수 있다(X21). 신선도 표시는 `git log`가 필요하므로 D9가 먼저다.

### D8. 프롬프트마다 강하게 걸릴 때만 기억을 넣는다(4d, 옵션A)
- by: 사람 (2026-11-25 대화, 질문3 옵션A)
- status: decided
- area: 전달, 코드 앵커
- basis: I3, X27
- depends: D3, D7

내용은 §4.3의 4d다. 사용자는 파일을 읽고 고칠 때마다 넣는 방식을 "좋지 못한 선택"이라며 거절하고 옵션A를 골랐다. 200토큰과 문턱은 구현 spec에서 잰다. 훅 실행기는 지금 UserPromptSubmit를 받지 않는다(X27).

### D9. `explore_project`는 등록 없이 cwd의 git 저장소를 본다
- by: 사람 (2026-11-25 대화, 결정5)
- status: decided
- area: 코드 앵커, explore_project
- basis: I6, X20

등록된 저장소가 없어 `explore_project`가 실패하는데, MCP 안내는 코딩 작업이면 이 도구를 먼저 부르라고 한다(X20). 저장소는 읽기만 한다.

### D10. 이번 change는 문서만 바꾸고, 개선 방향은 방향마다 나중 spec으로 한다
- by: 가정 (brief의 가정. 사용자는 스펙, 기존 설계 문서 수정, 삭제, HTML을 요청했고 구현은 요청하지 않았다)
- status: proposed
- area: global
- depends: D3, D4, D5, D6, D7, D8, D9, D15

바꾸는 파일은 이 spec 폴더, `docs/SPEC.md`, `docs/DECISIONS.md`, `docs/TODO.md`, 새 HTML, D15의 삭제 대상뿐이다. 나중 spec 순서는 3a, 3b~3e, D9, 4a~4e, 질의 설계로 제안한다. 질의 설계는 관측과 앵커가 차야 효과를 잴 수 있다.

### D11. SPEC은 §0, 원칙1, 옛 층 이름, 보관 문서 링크만 고친다
- by: 가정 (brief의 편집 대상 목록)
- status: proposed
- area: SPEC
- basis: X23, X24, X25
- depends: D1, D2, D6, D15, D16

1. §0은 D1대로 바꾸고 §4.1 층 표를 옮긴 뒤 이 spec을 링크한다.
2. 원칙1에 "질의 때도 LLM을 부르지 않는다"와 추출기 `auto`(D6, 구현 전이라 "계획")를 적는다.
3. §4·§5·§6의 "L1 노트"는 "자동 기억 노트", "L3 목록"은 "현재 상태 목록", "구획L3"은 "현재 상태 구획"으로 바꾼다. 코드가 출력하거나 받는 문구(`l1_note`, "L1 노트 N개")는 따옴표로 남긴다(X23).
4. "§0 규칙N" 참조는 새 번호나 해당 원칙·절로 고친다.
5. `archive/` 링크(§0 머리, §7, §8, §10)는 "git history의 `docs/archive/…`(커밋 `9ddce0c`)"로 바꾼다. §7 "Minimum JSON shape" 절은 건드리지 않는다(X25). `design/` 링크는 D16대로 둔다.

### D12. DECISIONS에는 사용자가 정한 결정만 더하고 옛 층 두 항목에 대체 표시를 단다
- by: 가정 (AGENTS.md와 DECISIONS 작성 규칙: 확정된 결정만 적는다)
- status: proposed
- area: DECISIONS
- basis: X25, X29
- depends: D1, D2, D5, D6, D8, D9

`2026-11-25 - …` 항목으로 D1, D2, D5, D6, D8, D9를 파일 형식(영어, X29)에 맞춰 더한다. D1과 D2, D5와 D6은 한 항목으로 묶어도 된다. 2026-11-06 두 항목은 본문을 두고 끝에 "Replaced by" 한 줄을 단다. `proposed` 결정은 적지 않는다. INV-05 항목은 그대로다(X25).

### D13. TODO에 개선 방향을 열린 일로 적는다
- by: 가정 (brief의 편집 대상 목록)
- status: proposed
- area: TODO
- basis: X24, X27
- depends: D3, D4, D5, D6, D7, D8, D9, D10, D11

"Memory Intent Redesign (spec 2026-11-25)" 절에 3a~3e, 결정5, 4a~4e, 질의 설계를 D10 순서의 체크박스로 적고 이 spec §4.3과 §6을 링크한다. n차-11(UserPromptSubmit 회상)에는 4d로 옮겼다고 적는다(X27). `archive/` 링크는 D11 방식으로 바꾼다. 다른 문장은 고치지 않는다.

### D14. 설계 용어집은 고치지 않는다
- by: 가정 (brief는 옛 층을 정의할 때만 고치라고 했다)
- status: proposed
- area: 문서 정리
- basis: X26

용어집은 옛 층을 정의하지 않는다(X26). 새 층 이름은 SPEC §0이 정의한다.

### D15. 옛 설계 문서 네 묶음을 지운다
- by: 사람 (2026-11-25 대화, "중복되는 문서들은 과감하게 삭제해도 좋다", spec gate O1)
- status: decided
- area: 문서 정리
- basis: X24, X25

지우는 것: `docs/superpowers/`(2026-06~09 옛 설계의 plan, spec, review), `docs/stenc/`와 이를 여는 `open-docs.sh`(같은 옛 내용의 정적 사이트), `docs/archive/`(SPEC v1.2, v5.0, DESIGN v1.2, SEARCH_ARCHITECTURE v1.2), `docs/html/2026-10-29-vault-memory-design.html`(옛 기억 설계 그림). 테스트, 스크립트, CI는 이 경로를 쓰지 않고, 현재 문서의 링크는 SPEC과 TODO에만 있다(X24, X25). 원본은 git history에 남는다. `docs/design/reports/`와 `docs/specs/`는 남긴다.

### D16. 10월 모듈 설계 묶음(`docs/design/specs/`, `plans/`, `intents/`)은 남긴다
- by: 사람 (2026-11-25 spec gate, O1 "세 폴더는 남김")
- status: decided
- area: 문서 정리
- basis: X24

brief는 "ARCHITECTURE가 이제 다룬다"고 보았지만, ARCHITECTURE는 VG-MOD 명세를 M 번호의 기준으로 링크하고, DEVELOPMENT, SPEC §8, 용어집도 이 문서를 계약으로 링크한다(X24). ARCHITECTURE와 DEVELOPMENT는 이번에 고치지 않는다. 세 폴더는 서로 링크하므로 함께 남긴다.

### D17. 개선 구조를 HTML 한 파일로 그려 `docs/html/`에 둔다
- by: 사람 (2026-11-25 대화, "시각화 문서를 html로 작성해서 docs/html 에 보관"), 가정 (담을 내용과 파일 형식)
- status: decided
- area: 문서 정리, HTML
- basis: I1, I3, I4

`docs/html/2026-11-25-memory-intent-layers.html` 하나에 CSS와 SVG를 넣고 외부 자원을 부르지 않는다. 한국어로 다섯 부분을 보인다. 의도1~5, 층 네 개, 쓰기 흐름(수집 → 사실 추출 → 제안·검토 → wiki), 질의 흐름(질의1~6), 코드 연결(앵커, 신선도, 프롬프트 주입). 개선 방향마다 decided, proposed를 표시하고 이 spec을 링크한다. 옛 기억 설계 그림을 대신한다.

### D18. AGENTS.md는 Project Boundary 첫 문장만 이번에 고친다
- by: 사람 (2026-11-25 spec gate, O2 "이번에 같이 바꿈")
- status: decided
- area: 문서 정리, AGENTS
- basis: I6, X30

Project Boundary 첫 문장은 "local search and recall layer"다(X30). 이번 change에서 그 문장만 이렇게 바꾼다. "Vault Graph is a local long-term memory layer over Vault. It delivers what is valid now, distilled from captured work, with its state, date and source, and calls no LLM at query time." 여섯 쓰기 경로와 나머지 문장은 그대로다. AGENTS.md는 bake 민감 경로라 PR 리뷰에서 따로 표시된다.

### D19. 세션 시작 회상의 추출기 줄은 매 세션 낸다
- by: 사람 (2026-11-25 spec gate, O3 "매 세션 보임")
- status: decided
- area: 사실 추출, 회상
- depends: D6

`facts: auto → claude`처럼 설정과 고른 추출기를 한 줄(약 15토큰)로 매 세션 낸다. 바뀔 때만 내면 서버가 꺼진 줄 모르고 지나가는 날이 생긴다. 문구는 3e 구현 spec이 정한다.

## 6. Failure and boundary behavior

앞의 다섯은 이번 문서 change에서 생길 수 있는 일이고, 뒤의 넷은 나중 구현 spec이 지켜야 할 경계다. 뒤의 넷은 TODO 항목이 이 절을 가리켜 넘긴다.

### F1. 현재 문서에 지운 폴더 링크가 남는다
- basis: D15, X24

지우기 전에 SPEC과 TODO의 `archive/` 링크를 git history 표기로 바꾼다. 지운 뒤 현재 문서를 다시 찾아 지운 경로 링크가 0개여야 한다.

### F2. 이력 문서 속 지운 경로는 그대로 둔다
- basis: D15, D16, X24

DECISIONS의 날짜 항목, PATCH_LOG, `docs/specs/`, 남기는 `docs/design/` 문서는 그 시점의 기록이라 고치지 않는다. SPEC §10에 "지운 보관 문서는 git history(커밋 `9ddce0c`)에서 찾는다"를 남긴다.

### F3. 코드 출력과 SPEC 용어가 한동안 다르다
- basis: D11, X23

코드는 "L1 노트 N개"를 출력하고 `l1_note`를 받는다(X23). SPEC은 이 문구를 따옴표로 그대로 적고 "이름 변경은 구현 spec에서 한다"고 덧붙여, 출력 문구로 SPEC을 찾을 수 있게 한다.

### F4. 문서를 읽는 테스트가 깨진다
- basis: D11, D12, X25

SPEC §7 "Minimum JSON shape" 절과 DECISIONS의 INV-05 항목은 손대지 않고, 새 글에는 `test_naming_conventions.py`의 금지어를 쓰지 않는다. 테스트가 실패하면 문서를 고치고 테스트는 바꾸지 않는다.

### F5. SPEC 본문의 "§0 규칙N" 참조가 옛 번호를 가리킨다
- basis: D1, D11

"§0 규칙3", "§0 규칙5 예외" 같은 참조는 새 의도 번호나 원칙·절 번호로 바꾼다. 사용 기록 예외처럼 새 의도에 없는 규칙은 §4의 해당 문단을 가리킨다.

### F6. `auto`인데 llama-server가 답하지 않는다
- basis: D6, X19

작업마다 끝점을 확인해 답이 없으면 claude로 추출한다. 중간에 서버가 꺼지면 그 작업은 실패로 남기고 다음 작업에서 다시 고른다. `llama-server`로 고정했으면 claude로 바꾸지 않고 실패로 알린다.

### F7. 질의가 어떤 개념에도 걸리지 않는다
- basis: D3, I3

비율이 문턱 아래면 "이 Vault에 그런 개념이 없음"과 가까운 개념을 돌려준다. 하나도 걸리지 않으면 관측과 기록 층을 하이브리드 검색하고 "개념 미연결"을 붙인다. LLM은 부르지 않는다.

### F8. 주장의 commit 뒤로 그 경로의 코드가 바뀌었다
- basis: D7, D9

"코드 바뀜, 다시 확인"을 붙여 돌려주고 결과에서 빼지 않는다. commit을 cwd 저장소에서 찾지 못하면 "확인 불가"로 표시한다.

### F9. cwd가 git 저장소 밖이다
- basis: D9

`explore_project`는 "git 저장소가 아님" 오류를 낸다. `repository_id`를 주면 지금처럼 등록 저장소를 쓴다. 프롬프트 주입은 개념만으로 동작한다.

## 7. What could be wrong

### R1. v1 원본 일부가 3a 전에 지워질 수 있다
- basis: X12

원본 날짜는 하나만 보았다. 10월 말 원본은 며칠 안에 지워질 수 있고, 그러면 그 part는 관측 층에 들어오지 못한다.

### R2. 프롬프트 주입은 vault-builder 훅 확장이 있어야 한다
- basis: X27

UserPromptSubmit을 vault-builder 실행기가 맡을지 vg가 따로 등록할지 확인하지 않았다. 따로 등록하면 settings 쓰기가 하나 늘어난다.

### R3. 사실 계약 v2는 vault-builder 변경에 묶인다
- basis: X13, X29

`attach-facts`가 새 필드(종류, 개념 태그, 앵커)를 받아 주는지 vault-builder 코드는 읽지 않았다. 받지 않으면 3c와 4b가 함께 늦어진다.

### R4. 로컬 추출기가 긴 part에서 너무 느릴 수 있다
- basis: X18, X9

로컬 14초는 짧은 세션 기준이고 실제 part는 294턴짜리도 있다. 70개 part backfill 시간은 재지 않았다.

### R5. 문턱 값이 실제 Vault에서 맞지 않을 수 있다
- basis: X22

Auto Ontology의 coverage는 DB 개념용이다. 한국어와 영어가 섞인 세션 낱말에 맞는지 재지 않았다.

### R6. 보관 문서를 지우면 SPEC §7·§8의 출처를 저장소 안에서 못 본다
- basis: X24

계약 본문은 SPEC 안에 있어 영향이 없다고 보았다. vault-builder 저장소가 이 경로를 링크하는지는 확인하지 않았다.


## 8. Acceptance criteria

이번 change의 기준이다. 설계 결정은 SPEC, DECISIONS, TODO에 옮겨졌는지로 확인하고, 동작 확인은 나중 spec이 §4.3 초안으로 한다.

### A1. 제품 코드, 테스트, 설정이 바뀌지 않는다
- covers: D10
- check: 수동: base `9ddce0c`과 change 끝 commit의 차이 파일 목록을 보고 `src/`, `packages/`, `tests/`, `scripts/`, `pyproject.toml`, `uv.lock`, `.github/`가 없는지 확인한다
- evidence:

### A2. SPEC §0이 의도1~5 다섯 문장을 담는다
- covers: D1, I1, I2, I3, I6
- check: 수동: `docs/SPEC.md` §0을 열어 이 spec §2의 다섯 문장과 한 문장씩 대조한다
- evidence:

머리말과 결정12~15도 남아 있어야 한다.

### A3. SPEC에 옛 층 이름이 코드 인용 말고는 없다
- covers: D2, D11, I4, F3, F5
- check: 수동: `docs/SPEC.md`에서 `L1`, `L2`, `L3`, `§0 규칙`을 찾아 남은 줄이 모두 따옴표나 백틱 안의 코드 문구인지 확인하고, §0 아래에 층 표 네 줄이 있는지 본다
- evidence:

### A4. DECISIONS에 승인된 결정이 들어가고 옛 층 두 항목에 대체 표시가 있다
- covers: D12, D5, D6, D8, D9
- check: 수동: `docs/DECISIONS.md`에서 `2026-11-25` 항목과 두 2026-11-06 항목의 "Replaced by" 줄을 확인한다
- evidence:

2026-11-06 두 항목의 본문은 그대로이고, `proposed` 결정은 없다.

### A5. TODO가 개선 방향을 순서대로 열린 일로 적는다
- covers: D3, D4, D7, D13, I5, I7, F6, F7, F8, F9
- check: 수동: `docs/TODO.md`의 "Memory Intent Redesign" 절에서 항목 수, 순서, 링크를 이 spec §4.3, §6과 대조한다
- evidence:

### A6. 네 묶음이 지워졌다
- covers: D15
- check: 수동: `docs/superpowers`, `docs/stenc`, `open-docs.sh`, `docs/archive`, `docs/html/2026-10-29-vault-memory-design.html`이 작업 트리와 git index에 없는지 확인한다
- evidence:

### A7. 현재 문서에 지운 경로 링크가 없다
- covers: F1, F2
- check: 수동: README 두 개, AGENTS, `docs/` 바로 아래 `.md`(DECISIONS, PATCH_LOG 제외), `docs/design/glossary.md`에서 `superpowers/`, `stenc`, `open-docs`, `archive/`, `2026-10-29-vault-memory-design`을 찾는다
- evidence:

결과는 0줄이다. 예외는 SPEC과 TODO가 vault-builder 저장소의 `docs/superpowers/…` 파일을 가리키는 줄이다. 다른 저장소 경로라 남긴다.

### A8. 10월 모듈 설계 묶음과 그 링크가 살아 있다
- covers: D16
- check: 수동: `docs/ARCHITECTURE.md`, `docs/DEVELOPMENT.md`, `docs/SPEC.md` §8, `docs/design/glossary.md`의 `design/` 링크 대상 파일이 모두 있는지 확인한다
- evidence:

### A9. 문서를 읽는 기존 테스트가 통과한다
- covers: F4
- check: tests/test_context_pack_docs_contract.py, tests/test_retired_search_filter.py, tests/test_naming_conventions.py, tests/test_readme_onboarding_contract.py
- evidence:

### A10. HTML이 오프라인에서 열리고 다섯 부분을 보인다
- covers: D17
- check: 수동: 네트워크를 끊고 `docs/html/2026-11-25-memory-intent-layers.html`을 브라우저로 연다. 파일 안에 `http://`, `https://`로 시작하는 `src`나 스타일시트 `href`가 없는지 찾는다
- evidence:

의도1~5, 층 네 개, 쓰기 흐름, 질의 흐름, 코드 연결이 한국어로 보여야 한다.

### A11. 고치지 않기로 한 문서가 그대로이고 AGENTS.md는 첫 문장만 바뀌었다
- covers: D14, D18
- check: 수동: base `9ddce0c`과 비교해 `CLAUDE.md`, `docs/ARCHITECTURE.md`, `docs/FEATURES.md`, README 두 개, `docs/design/glossary.md`에 차이가 없고, `AGENTS.md`의 차이가 Project Boundary 첫 문장 하나뿐인지 본다
- evidence:

### A12. 추출기 회상 줄의 빈도가 TODO 3e 항목에 적혀 있다
- covers: D19
- check: 수동: `docs/TODO.md`의 3e 항목에 회상 줄을 매 세션 낸다고 적혀 있는지 확인한다
- evidence:

## 9. Open decisions

### O1. 10월 모듈 설계 문서 세 폴더도 지울까?
- decides: D15, D16

배경: 사용자는 중복 문서를 과감히 지워도 된다고 했다. 이 spec은 옛 설계 plan·spec·review(`docs/superpowers/`), 같은 내용의 정적 사이트(`docs/stenc/`, `open-docs.sh`), 옛 SPEC 보관본(`docs/archive/`), 옛 기억 설계 그림을 지운다. 10월 모듈 설계(`docs/design/specs/`, `plans/`, `intents/`)는 ARCHITECTURE, DEVELOPMENT, 용어집, SPEC §8이 아직 모듈 번호와 독립 패키지 계약의 기준으로 링크한다.

추천: 세 폴더는 남긴다. 지우면 이번에 고치지 않는 ARCHITECTURE와 DEVELOPMENT의 링크가 깨지고 패키지 계약 본문이 저장소에서 사라진다.

답에 따라 바뀌는 것: "남긴다"면 지금 spec대로다. "지운다"면 ARCHITECTURE와 DEVELOPMENT 링크 수정과 패키지 계약을 SPEC §8로 옮기는 일이 이번 change에 더해진다. 보관본도 남기고 싶다면 함께 답한다.

답(2026-11-25 spec gate): 세 폴더는 남긴다. D15, D16에 반영했다.

### O2. AGENTS.md 첫 문장은 사람이 나중에 바꿀까?
- decides: D18

배경: AGENTS.md는 이 작업 흐름이 건드리지 않는 파일이다. Project Boundary 첫 문장은 vault-graph를 "검색·회상 층"으로 부르고, 새 의도는 "작업 경험을 상태와 날짜가 있는 기억으로 돌려주는 장기 기억 도구"다. 여섯 쓰기 경로 목록은 그대로 맞다.

추천: change 완료 보고에 D18의 영어 문장을 넣고 사람이 첫 문장만 바꾼다. 경계 규칙은 그대로라 급하지 않다.

답에 따라 바뀌는 것: "나중에 직접"이면 이번 change는 AGENTS.md를 건드리지 않는다. "바꾸지 않음"이면 보고에서 그 문장을 뺀다. "이번에 같이"면 이 파일 편집을 따로 허락해야 한다.

답(2026-11-25 spec gate): 이번에 같이 바꾼다. D18에 반영했다.

### O3. 추출기 상태 줄을 매 세션 보일까, 바뀔 때만 보일까?
- decides: D19

배경: 사용자는 사실 추출에 로컬 AI가 쓰이는지 claude가 쓰이는지 알고 싶다고 했다. `vg facts status`와 사실 첨부 파일에는 항상 남는다. 남은 질문은 세션 시작 회상에 넣는 한 줄(약 15토큰)의 빈도다.

추천: 매 세션 보인다. 로컬 서버가 꺼진 것을 바로 알 수 있고, 1,500토큰 회상 예산에서 15토큰은 작다.

답에 따라 바뀌는 것: "매 세션"이면 회상에 늘 한 줄이 더해진다. "바뀔 때만"이면 토큰은 아끼지만 지난 상태를 Graph Home에 적어야 하고, 서버가 계속 꺼져 있으면 첫날 뒤로는 보이지 않는다.

답(2026-11-25 spec gate): 매 세션 보인다. D19에 반영했다.
