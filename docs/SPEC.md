# Vault Graph Specification: Local-Graph

- 상태: 활성 제품 계약
- 시작: 2026-10-29 (결정4 옵션1, [DECISIONS](DECISIONS.md))
- 상세 설계: [spec 2026-10-29-local-graph-memory-layer](specs/2026-10-29-local-graph-memory-layer/spec.md)
- 보관 문서: [SPEC v1.2](archive/SPEC-v1.2.md), [SPEC v5.0 Software Invariant Engine](archive/SPEC-v5.0.md)

## 목차

0. 의도
1. 제품 정의와 원칙
2. 역할 분담
3. 가치
4. 읽기·쓰기 경계
5. 인터페이스
6. 외부 계약
7. Context Pack 계약
8. 독립 모듈 5개
9. 단계
10. 보관 문서

## 0. 의도

이 절은 자주 바뀌지 않는다. 아래 절의 세부 계약은 모두 이 절의 규칙 중 하나를 따라야 한다(2026-11-02 사용자 확정).

vault-graph는 Vault를 기반으로 한 Claude Code용 장기 기억 도구다.

1. 기억이 사는 곳: 기억은 Vault에만 저장한다. vault-graph는 여러 Vault를 함께 다루며, Vault마다 종류가 있다. 기본 종류는 개인(personal)과 프로젝트(project)이고, 소유자가 팀(team) Vault를 더할 수 있으며, 다른 종류가 더 생길 수 있다. 프로젝트가 쓰는 Vault와 각 Vault의 종류는 `vault-map.json`이 정한다.
2. vault-graph가 쓰는 것: Vault의 기억 페이지를 추가, 수정, 폐기한다. 사용자가 직접 말한 사실은 Vault 검증을 통과하면 확정한다. 에이전트가 추론한 사실은 승인될 때까지 Vault 검토 대기열에 둔다.
3. 쓰는 방법: 모든 쓰기는 Vault 자체 도구를 거친다. vault-graph는 Vault 파일을 직접 고치지 않는다. 세션 원문 저장도 같다. 저장은 Vault의 `sessions capture`가 하고, vault-graph가 없으면 사용자가 직접 실행하며, vault-graph가 있으면 vault-graph가 실행 시점을 정한다.
4. 에이전트에 기억을 주는 방법: 세션 시작 때 정해진 토큰 예산 안에서 짧은 회상을 넣는다. 작업 중에는 의미, 코드, 페이지 간 연결로 검색하고, 모든 결과에 출처를 붙인다.
5. vault-graph 쪽에 남기는 것: 다시 만들거나 버려도 되는 데이터(검색 색인, 사용 기록)만 둔다. 사용 기록이 순위나 정리에 영향을 주기 시작하면 그 값은 Vault로 옮긴다. vault-graph 저장소를 지워도 기억은 사라지지 않는다.

이유: Claude Code 기본 기억은 매 세션 통째로 읽는 평평한 파일 몇 개이고, 대화 기록은 기본 30일 뒤 지워진다. vault-graph는 기억을 Vault에 영구히 두고, 지금 작업에 필요한 부분을 찾아 정해진 예산 안에 넣는다.

여러 Vault 규칙(결정12~15):

- 결정12 새 기억의 저장 Vault: (1) 에이전트가 `vault`를 지정하면 그 Vault. (2) 없으면 프로젝트의 기본 저장 Vault(`vault-map.json`에 둔다, 보통 project Vault). (3) 그것도 없고 후보가 여럿이면 저장하지 않고 `vault_required`로 묻는다. 기억 유형으로 Vault를 자동 선택하지 않는다.
- 결정13 검색 결합: 프로젝트에 연결된 모든 Vault를 검색해 관련도 순 한 목록으로 돌려준다. 결과마다 Vault 이름과 종류를 붙인다. 종류 간 고정 우선순위는 없다.
- 결정14 세션 시작 회상 예산: 고정(pin) 기억을 Vault와 상관없이 먼저 넣고, 나머지는 모든 Vault를 합친 순위로 한도까지 채운다. Vault별 고정 비율은 두지 않고, 측정에서 한 Vault가 예산을 독차지할 때 다시 정한다.
- 결정15 Vault 종류: 종류는 `vault-map.json`의 이름표다. 코드는 특정 종류 이름으로 분기하지 않으므로, 새 종류는 설정만 더하면 된다.

참고한 사례: OpenWiki의 workspace 규칙(위키마다 독립, 사용자 범위 등록부, 후보가 여럿이고 선택이 없으면 `workspace_required`, 결과마다 출처 위키 표시).

현재 구현과의 차이(남은 일만 적는다, 2026-11-02 기준):

- 프로젝트 Vault가 Graph Home에 하나도 등록되지 않았을 때 `search`는 빈 결과와 "`vg setup` 필요" 경고를 돌려주지만, `ask`, `context`와 MCP `find_related` 등 다섯 도구는 같은 내용을 오류로 낸다.
- Vault 이름·종류(`vault_name`, `vault_role`)는 검색 결과에만 붙고, 답변과 context pack 결과에는 없다(의도 검수 F12). HTTP의 선택 필드 `cwd`는 `/search`에만 있다.
- 폐기(`retired`) 페이지를 포함해 검색하는 옵션은 없다.
- 2026-11-02 최초 의도 기준 검수([intent-audit](specs/2026-11-02-vault-long-term-memory/research/intent-audit.md))에서 다음 작업으로 넘긴 것:
  - F9: personal과 project Vault를 함께 연결한 프로젝트는 기본 저장 Vault가 없어 첫 쓰기가 `vault_required`다(vault-builder).
  - F10: 고정 기억의 `summary`가 제목과 같아 내용이 회상에 들어가지 않는다.
  - F11: 대기 중인 추론 제안 수를 어디서도 보여 주지 않는다.
  - F13: 설치한 훅이 worktree의 `.venv` 안 vg를 가리킨다. 병합 뒤 고정 경로의 vg로 다시 설치한다.

실제 Vault로 시나리오 ①~⑥을 도는 자동 E2E(`tests/e2e/test_long_term_memory_scenarios.py`)는 `VAULT_BUILDER_ROOT`를 주고 실행해 6개 모두 통과했다(2026-11-02, [실행 기록](specs/2026-11-02-vault-long-term-memory/research/e2e-run.log)). `VAULT_BUILDER_ROOT`가 없으면 이 테스트는 건너뛴다. 실제 Claude Code 세션 하나로 하는 수동 확인도 마쳤다(2026-11-02, 장기 기억 spec 작업23).

## 1. 제품 정의와 원칙

vault-graph는 Vault 위에서 도는 로컬 장기 기억 계층이다. Vault 원문, wiki, 코드를 읽어 색인하고, 에이전트가 필요한 기억을 출처와 함께 토큰 예산 안에 돌려주며, 기억 기록은 Vault 도구에 맡긴다. Vault는 vault-graph 없이도 동작한다.

방향 이름은 Local-Graph다. 핵심은 Local이고, Graph(관계 추적)는 보조 가치다.

1. 원칙1 Local: 모든 처리가 이 컴퓨터 안에서 끝난다. 호스팅 서비스, API 키, LLM 호출이 없다(결정7). 질의 답변, 요약, 사실 추출을 vault-graph 안에서 생성하지 않는다. 추론은 호출한 에이전트가 한다.
2. 원칙2 원본은 Vault: 기억의 원본은 Vault의 Markdown 파일이다. vault-graph 색인은 지워도 다시 만들 수 있는 파생 데이터이며 지식 원본이 아니다.
3. 원칙3 `wiki/`는 검증 경로로만 바뀐다: Vault `wiki/`는 Vault 도구의 검증 경로(publish-draft 등)를 거쳐서만 바뀐다.
4. 원칙4 vault-graph는 Vault 파일을 직접 쓰지 않는다: vault-graph 프로세스는 Vault 파일을 직접 만들거나 고치거나 이름을 바꾸거나 지우지 않는다. Vault에 쓸 때는 Vault 도구를 실행해 그 검증을 거친다. 구현된 길은 세 가지다. 사용자가 말한 사실의 추가·수정·폐기는 publish-draft, 에이전트가 추론한 사실은 `review propose`(사람이 `review resolve`로 승인), 세션 원문은 훅 실행기를 거친 `sessions capture`다(§4).
5. 원칙5 `raw/`에 직접 쓰지 않는다: vault-graph는 Vault `raw/`에 직접 쓰지 않는다. 세션 원문은 Vault의 `sessions capture`가 쓰고, vault-graph는 그 실행 시점만 정할 수 있다(§0 규칙3).
6. 원칙6 연결 정보는 `vault-map.json` 하나: 프로젝트와 Vault의 연결 정보는 사용자 범위의 `vault-map.json`이 원본이고, vault-graph는 이 파일을 읽기만 한다(결정9).

## 2. 역할 분담

| 영역 | Vault (llm-wiki) | 사용자 범위 (vault-builder가 설치) | vault-graph |
|---|---|---|---|
| 저장 | 기억 원본 Markdown | 없음 | 없음. 색인은 지워도 다시 만든다 |
| 쓰기 | `wiki/`는 publish-draft 등 검증 경로로만. 추론 사실은 `review propose`로 검토 대기열 `scratch/review/`에 두고, 사람이 `review resolve --status accepted`로 승인하면 발행한다 | 없음 | `remember`·`update_memory`·`retire_memory`가 draft를 만들어 Vault 도구에 맡긴다. `basis: stated`는 publish-draft, `basis: inferred`는 `review propose`를 실행한다. 직접 쓰는 곳은 Graph Home뿐이다 |
| 세션 수집 | `sessions capture`가 `raw/sessions/`에 새 턴만 덧붙인다 | 훅 실행기 `vault_hooks.py`가 PreCompact·SessionEnd 훅을 받아 vg가 있으면 `vg hook capture`, 없으면 직접 수집을 실행한다. 수집할 Vault를 고른다 | `vg hook capture`가 실행 시점만 정하고 실행기의 `capture --direct`를 부른다. Vault와 내용은 고르지 않고 수집 뒤 색인하지 않는다 |
| Vault·프로젝트 연결 | 자기 폴더 하나만 다룬다 | `vault-map.json`, llm-wiki router. vault-builder가 install·link·unlink·`set-role`·`set-default-write`로 고친다 | `vault-map.json`을 읽기만 한다(결정9). 프로젝트 연결 Vault, Vault 종류(`role`), 기본 저장 Vault(`default_write_vault`)를 읽는다 |
| 검색 | `wiki/`만. 질의마다 파일을 다시 읽고 한국어 조사를 뗀다 | router가 연결된 Vault 전체에 검색을 보낸다 | `raw/`·`wiki/`·`docs/`·`scratch/reports/`를 상시 색인하고 키워드·의미·그래프 후보를 합친다. 범위를 주지 않으면 `cwd` 프로젝트에 연결된 Vault 전부를 관련도 순 한 목록으로 찾고, 결과마다 Vault 이름과 종류를 붙인다 |
| 회상 | 없음 | `recall.sh`: 고정 섹션 3개, 1,500토큰 | 세션 시작 회상. 고정(`pin: true`) 기억을 400토큰 구획에 먼저 넣고, 나머지는 모든 연결 Vault를 합쳐 최신순으로 채운다. vault-graph가 없으면 훅 실행기가 `recall.sh`를 쓴다(결정10) |
| 코드 | 없음 | 없음 | 심볼, 호출, 영향 범위와 결정 기록을 연결한다 |
| LLM | 정리 스킬에서 쓴다 | 없음 | 부르지 않는다(결정7) |

## 3. 가치

| 코드 | 가치 | Vault만으로는 | vault-graph 현재 | 남은 일 |
|---|---|---|---|---|
| 가치1 | 대량 원문 검색: 세션 원문 수천 개에서 찾기 | `wiki/`만 찾고 매번 전체를 다시 읽는다 | 구현. `raw/` 포함 상시 색인, 증분 색인 | 세션 수집(의존2, 의존3)이 먼저 있어야 성립한다. 규모 측정 |
| 가치2 | 의미 검색: "인증 실패"로 "로그인 오류" 찾기 | 없음 | 구현. 다국어 MiniLM 임베딩 | 한국어 품질 측정(n차-4). 한국어 키워드는 지금 Vault 검색이 낫다(1차-5에서 보강) |
| 가치3 | 코드 위키: 코드와 결정·작업 기록을 함께 조회 | 코드를 읽지 않는다 | 일부. Python·Dart 코드 투영, `explore_project`. 검색 색인과 분리 | `explain_symbol`, 질의 하나로 코드와 기억 찾기(n차-3) |
| 가치4 | 관련 기억만 담은 회상 | `recall.sh`는 고정 섹션만 출력한다 | 구현. context pack(기본 8,000토큰 예산), 세션 시작 회상(고정 기억 구획 포함) | 질문 기반 회상(n차-8) |
| 가치5 | 문단 단위 근거: 중복 제거, 인용 검증 | 페이지 단위 결과 | 구현. 문단 조각, provenance 묶음, 인용 검증 | 대체된 claim 제외를 Vault와 맞추기(n차-1) |
| 가치6 | 관계 추적(보조) | 링크와 지도만 있다 | 구현. `find_related`, `get_decision_trace` | 없음 |

가치가 아닌 것:

- 세션 수집 자체. Vault 도구의 몫이다.
- `wiki/`만 대상으로 한 "빠른 검색". `wiki/` 126쪽 규모에서는 측정 전이고 근거가 약하다.
- 쓰기 검증과 Vault·프로젝트 연결 설정. 검증은 Vault 도구, `vault-map.json` 수정은 vault-builder의 몫이다. vault-graph는 Vault 도구를 실행해 기억을 쓰고, `vault-map.json`을 읽어 여러 Vault를 함께 검색한다.

가치1과 가치2는 아직 숫자로 확인되지 않았다. 측정1(6절)로 확인한다.

## 4. 읽기·쓰기 경계

읽는 대상:

- Vault의 `raw/`, `wiki/`, `docs/`, `scratch/reports/` (기본 색인 범위 `DEFAULT_CONTENT_SCOPES`). 검토 대기열 `scratch/review/`는 색인하지 않는다(결정6).
- 등록한 코드 저장소의 소스.
- 사용자 범위의 `vault-map.json`.

쓰는 대상:

- Graph Home(`$HOME/.vault-graph` 등) 아래의 파생 데이터와 설정. 명시적 명령(setup, index, watch, MCP 등록 등)과 바로 아래의 색인 갱신 두 경우에서만 기록한다. 정상 조회는 색인·설정을 기록하지 않는다. 예외는 세션 시작 회상과 MCP 페이지 리소스 읽기가 Graph Home `usage/`에 사용 기록을 덧붙여 쓰는 것 하나다. 사용 기록은 순위에 영향을 주지 않는다. 회상의 구획C 알림 중복 방지에만 쓰므로, `usage/`를 지워도 검색 결과와 회상 구획A·B는 같다.
- Graph Home 색인은 두 경우에 명시적 `vg index` 없이도 갱신된다(2026-11-02 의도 검수 F1). 저장한 기억이 다음 세션 회상과 검색에 바로 나오게 하기 위해서다. 둘 다 Vault 파일은 읽기만 한다.
  1. MCP 쓰기 도구가 `published`를 돌려주면, MCP 서버가 그 Vault의 증분 색인(`vg index --vault-id`와 같은 동작)을 백그라운드로 시작하고, 끝나면 검색 서비스를 다시 연다. 도구 결과는 색인을 기다리지 않고, 색인이 실패해도 쓰기 결과는 바뀌지 않는다. MCP 도구와 페이지·문서·그래프 리소스는 읽을 때마다 활성 세대를 확인해, 다른 프로세스가 새 세대를 발행했으면 서비스를 다시 연다(2026-11-02 3차 검수 발견7).
  2. `vg hook session-start`는 회상 전에, 이미 색인된 연결 Vault에서 바뀐 파일만 메타데이터와 그래프로 다시 색인하고 새 세대를 발행한다. 임베딩은 만들지 않는다. 시간 한도는 기본 5초(`--refresh-budget`)이고, 바뀐 파일 찾기도 이 한도 안에서 한다. 바뀌거나 지운 파일만 읽어 메타데이터에 쓴다. 한도를 넘거나, 바뀌거나 지운 파일이 200개를 넘거나, 다른 실행이 세대 발행 잠금을 1초 넘게 쥐고 있거나, 실패하면 아무것도 발행하지 않고 경고 한 줄을 낸 뒤 기존 색인으로 회상한다. 훅은 이 때문에 실패하지 않는다. 연결 Vault에 색인된 문서가 1,500개를 넘거나, Graph Home `logs/quick-refresh-times.json`에 남은 지난 갱신 시간(하루 안의 기록만 쓴다)으로 보아 남은 시간 안에 끝나지 않으면 쓰기 전에 건너뛴다. 그래서 문서가 1,500개를 넘는 Vault에서는 MCP 밖에서 바뀐 파일(세션 원문 등)이 다음 세션의 백그라운드 색인을 거쳐 그다음 세션 회상부터 나온다(2026-11-02 3차 검수 발견8).
  3. 같은 훅은 바뀐 파일 찾기가 끝나면 분리된 백그라운드 프로세스 하나를 띄운다. 이 프로세스는 훅의 갱신이 끝나기를 기다린 뒤, 바뀐 파일이 있는 연결 Vault와 벡터가 오래됐거나 없는 연결 Vault마다 일반 `vg index --vault-id`(임베딩 포함)를 실행한다. 새 조각의 벡터는 이 색인이 만들고, 중간에 죽은 색인은 다음 세션 시작에서 다시 실행된다. 훅은 기다리지 않는다. 이 프로세스는 살아 있는 동안 Graph Home `logs/session-start-index.lock`에 flock을 쥐고, 잠금이 잡혀 있으면 다음 세션 시작은 새로 띄우지 않는다. 출력은 `logs/session-start-index.log`에 쓴다(2026-11-02 재검수 발견1·3, 3차 검수 발견10).
- `vg watch`는 메타데이터·벡터·그래프에 바뀐 것이 있을 때만 새 세대를 발행한다(2026-11-02 3차 검수 발견11).
- 세대 발행은 프로세스 간 파일 잠금(`projections/.publish.lock`)으로 한 번에 하나만 한다. 발행 뒤에는 현재 세대와 바로 이전 세대만 남기고 나머지 세대 폴더를 지운다. 중단된 실행이 남긴 스테이징 폴더는 1시간이 지나면 다음 스테이징을 시작할 때 지운다(2026-11-02 재검수 발견4·5).
- Vault에는 Vault 도구를 실행하는 세 경로로만 쓴다.
  1. publish-draft: `remember`(추가), `update_memory`(수정), `retire_memory`(폐기)에 `basis: stated`를 주면 Vault 검증을 통과하는 순간 확정된다.
  2. `review propose`: 같은 세 도구에 `basis: inferred`를 주면 검토 항목을 만들고 `proposed`와 `review_path`를 돌려준다. 사람이 `review resolve <review_path> --status accepted`로 승인하면 Vault가 발행한다. 승인 전에는 회상과 검색에 나오지 않는다. 사람이 `--status rejected`로 거부하면 기억 페이지는 만들어지거나 바뀌지 않고, `wiki/log.md`에 "Review rejected" 한 줄만 더해진다(2026-11-02 사용자 결정).
  3. 수집 실행기: `vg hook capture`가 훅 실행기 `vault_hooks.py capture --direct`를 실행하고, 실행기가 Vault `sessions capture`로 세션 원문을 쓴다. vault-graph는 실행 시점만 정한다.
- 일반 조회·색인·watch·회상과 다른 MCP 도구는 이 세 경로를 실행하지 않는다.
쓰지 않는 대상:

- Vault 파일을 직접 만들거나 고치거나 이름을 바꾸거나 지우지 않는다.
- Vault `raw/`에 직접 쓰지 않는다. 세션 원문 저장은 Vault `sessions capture`의 몫이다(§0 규칙3).
- 코드 저장소 소스와 `vault-map.json`은 고치지 않는다.

이 경계는 `AGENTS.md` Project Boundary, [ARCHITECTURE.md](ARCHITECTURE.md) §4, [VG-MOD](design/specs/2026-10-15-vault-graph-modular-architecture-ko.md) INV-01·INV-02·INV-04와 같은 원칙이다.

## 5. 인터페이스

유지한다:

- 기존 CLI 명령(`vg setup`, `vg vault add`, `vg index`, `vg watch`, `vg search`, `vg ask`, `vg context`, `vg status` 등)의 이름·인자·응답 형식.
- 기존 MCP 도구 11개: `ask_vault`, `search_vault`, `build_context_pack`, `find_related`, `get_decision_trace`, `check_index_status`, `explain_result`, `summarize_project_memory`, `get_open_questions`, `get_recent_changes`, `explore_project`. 기존 이름과 입력·출력 필드를 바꾸지 않는다. `search_vault`, `ask_vault`, `build_context_pack`과 `find_related`, `get_decision_trace`, `summarize_project_memory`, `get_open_questions`, `get_recent_changes`는 선택 입력 `cwd`를 더 받는다. `cwd`가 없으면 MCP 서버 프로세스의 작업 디렉터리를 쓰고, 그 프로젝트에 연결되고 등록된 Vault 전부를 범위로 쓴다(뒤의 다섯 도구는 2026-11-02 의도 검수 F4). `search_vault` 결과에는 선택 필드 `vault_name`, `vault_role`이 붙는다.
- 호환 규칙: 기존 필드는 바꾸지 않는다. 선택 필드와 도구를 더하는 것은 허용한다. 기존 호출자는 모르는 필드를 무시하면 그대로 동작한다(2026-11-02, 위험12).
- MCP 리소스와 로컬 HTTP(FastAPI) 응답.
- `project-bindings.json`, `vg setup --vault`, `vg vault add`는 1차에서 지우지 않는다. 제거는 n차-7이다.

추가한다(1차):

- CLI `vg hook session-start [--graph-home PATH] [--vault-map PATH] [--max-tokens N] [--refresh-budget S]`. 표준 입력으로 Claude Code SessionStart 훅 JSON을 받아 회상 묶음(Markdown)을 표준 출력에 낸다. 종료 코드 0은 "처리함"(출력이 비어 있을 수 있음), 3은 "회상할 수 없음"이다. 세부는 상세 설계 4.2.3. 회상 전에 연결 Vault의 바뀐 파일을 임베딩 없이 색인한다(§4). `--refresh-budget`은 그 시간 한도(초, 기본 5)이고 0이면 하지 않는다. `--vault-map`이 없을 때의 경로 규칙은 §6-1이다.
- MCP 쓰기 도구 3개. MCP 도구는 모두 14개다. 세부는 [장기 기억 spec](specs/2026-11-02-vault-long-term-memory/spec.md) V3.
  - `remember(title, kind, body, evidence, basis, cwd=None, vault=None, pin=False, memory_kind=None)`: 새 페이지를 추가한다. 같은 경로가 있으면 `rejected`이고 `update_memory`를 쓰라고 안내한다.
  - `update_memory(path, body, evidence, basis, vault=None, cwd=None, title=None, pin=None, memory_kind=None)`: 페이지 본문을 통째로 바꾼다. frontmatter는 현재 값을 두고 준 값과 `updated`만 바꾼다. 읽은 뒤 페이지가 바뀌었으면 `rejected`다.
  - `retire_memory(path, reason, basis, vault=None, cwd=None, replaced_by=None)`: frontmatter만 바꾼다. 대체가 없으면 `status: retired`와 `retired_reason`, `retired_at`, 대체가 있으면 `status: deprecated`와 `superseded_by`다.
  - `basis`(`stated` 또는 `inferred`)는 세 도구 모두 필수이고 기본값이 없다.
  - 도구 스키마는 `basis`, `kind`(`decision`, `system`), `memory_kind`(`rule`, `correction`, `decision`, `preference`)의 허용 값을 enum으로 보인다(2026-11-02 의도 검수 F8).
  - `cwd`가 없으면 MCP 서버 프로세스의 작업 디렉터리를 `cwd`로 쓴다. 그래서 다른 프로젝트 Vault에 쓰지 않는다(2026-11-02 의도 검수 F7).
  - 결과 `status`는 `published`, `proposed`, `rejected`, `vault_required`, `error` 중 하나다. `proposed`면 `review_path`가 붙고, `messages`에 사람이 실행할 승인 명령 `review resolve <review_path> --status accepted --resolution "<reason>"`이 들어간다. `vault_required`면 후보 `{name, role}` 목록이 붙는다.
  - 새 페이지의 저장 Vault는 결정12대로 고른다. `vault`는 `cwd` 프로젝트의 연결 Vault 안에서만 찾고, 연결되지 않은 이름이면 `rejected`와 연결 Vault 목록을 돌려준다. 수정·폐기는 `path`가 있는 연결 Vault를 찾는다. 하나면 그 Vault, 없으면 `rejected`, 둘 이상이면 `vault_required`다.
  - `published`면 MCP 서버가 그 Vault를 백그라운드로 색인한다(§4). 색인을 시작하면 `messages`의 "`vg index`를 실행하라" 안내가 "백그라운드로 색인 중" 안내로 바뀐다.
- CLI `vg hook capture [--vault-map PATH] [--timeout S]`. 표준 입력으로 Claude Code PreCompact 또는 SessionEnd 훅 JSON을 받아 `vault-map.json` 폴더의 `vault_hooks.py capture --direct`에 그대로 넘긴다. 결과(`status`, `vault`, `path`)를 표준 오류에 한 줄로 요약한다. 종료 코드 0은 실행기가 정상으로 끝났음(written, no-new-turns, skipped 모두), 3은 실행기를 찾지 못했거나 실패했거나 시간 제한(기본 20초)을 넘었음이다. 3이면 훅 실행기가 직접 수집한다. Graph Home에 쓰지 않고 수집 뒤 색인하지 않는다. 수집한 원문은 다음 `vg hook session-start`의 색인 갱신이 반영한다.
- `vg setup --agent claude --mcp`: Claude Code 사용자 설정 `.claude.json`의 `mcpServers.vault-graph`에 `vg serve --mcp` 항목을 더한다(2026-11-02 의도 검수 F5). 파일 위치는 Claude Code와 같다. `CLAUDE_CONFIG_DIR`가 비어 있지 않으면 `$CLAUDE_CONFIG_DIR/.claude.json`, 아니면 `$HOME/.claude.json`이다(2026-11-02 재검수 발견6). 한글 등 ASCII가 아닌 글자는 `\u` 이스케이프로 바꾸지 않고 그대로 쓴다. 다른 키와 MCP 서버는 그대로 두고, 바꾸기 전 파일을 `.claude.json.bak`으로 남기며, 파일이 JSON이 아니면 쓰지 않는다. `--mcp-config-path`, `--dry-run`, `--print-mcp-config`는 codex와 같다. `vg mcp config`·`vg mcp register`도 `--agent claude`를 받는다.

## 6. 외부 계약

1. `vault-map.json` version 2 읽기
   - 경로는 다음 순서로 정한다(2026-11-02 3차 검수 발견9). vault-builder가 쓰는 위치와 같다.
     1. CLI `--vault-map PATH`
     2. 환경 변수 `VAULT_GRAPH_VAULT_MAP`
     3. `CLAUDE_CONFIG_DIR`가 비어 있지 않으면 `$CLAUDE_CONFIG_DIR/vault-builder/vault-map.json`
     4. `$HOME/.claude/vault-builder/vault-map.json`
   - 형식: `vaults`는 이름 → `{path, role}`, `projects`는 프로젝트 id → `{root, vaults: [Vault 이름…], remote, default_write_vault}`.
   - `default_write_vault`는 선택 필드이며 프로젝트의 기본 저장 Vault 이름이다(결정12). 문자열이 아니거나 그 프로젝트 `vaults` 밖이면 그 필드만 무시하고 경고한다. `vg status`가 프로젝트별 기본 저장 Vault와 경고를 보인다. `role`은 표시용 이름표이며 코드는 값으로 분기하지 않는다(결정15).
   - 프로젝트 찾기 규칙은 llm-wiki router(`find_project`)가 소유하고, vault-graph는 같은 규칙을 따른다.
   - `version`이 2가 아니거나 형식이 깨졌으면 쓰지 않고 경고한다. 파일을 고치거나 만들지 않는다.
2. publish-draft·`review propose` 호출과 draft 형식
   - Vault 루트를 작업 디렉터리로 하여 `<vault-graph의 Python> -I -B tools/wiki/cli.py publish-draft <draft_path> --json`(계약1) 또는 `... review propose --draft <draft_path> --summary <text> --json`(계약4)을 실행한다. `--report`는 주지 않는다. 시간 제한은 120초다.
   - 표준 출력의 JSON 객체만 읽고 사람이 읽는 텍스트는 해석하지 않는다. publish-draft는 `format: vault-publish-result/v1`(`status`, `reason`, `written_paths`, `messages`), `review propose`는 `format: vault-review-result/v1`(`status`, `review_path`, `messages`)이다.
   - 종료 코드 2와 `unrecognized arguments`는 Vault 도구가 계약 4 미만이라는 뜻으로 보고 "계약 4로 마이그레이션하라" `error`를 돌려준다. JSON이 아니면 표준 출력·오류 마지막 20줄을 담은 `error`다. `reason: human-locked`는 Vault 메시지와 함께 `rejected`로 전한다.
   - draft는 에이전트가 넘긴 필드와 실행 날짜만으로 결정적으로 만든다. 추가·수정은 `upsert-page`, 폐기는 frontmatter만 바꾸는 `patch-page`(계약3)다. Vault와 Graph Home 밖의 임시 디렉터리에 만들고 실행 뒤 지운다.
3. Vault 검색과의 비교 방법(측정1)
   - 같은 질문 20개를 Vault 검색(`tools/wiki/cli.py search <질문> --limit 5`)과 `vg search`(기본 모드, 상위 5개)에 넣어 실제 대기 시간과 상위 5개 적중률을 비교한다.
   - 조건A는 지금 Vault, 조건B는 세션 원문이 쌓인 Vault다.
   - 성공 기준: 두 조건 모두에서 `vg search`의 상위 5개 적중률이 Vault 검색보다 높다.
   - 질문과 질문별 결과는 저장소 밖에 두고, 합계만 `docs/design/reports/`에 커밋한다.

## 7. Context Pack 계약

보관본 [SPEC v5.0](archive/SPEC-v5.0.md) §9.6 "기존 Context Pack 호환성 계약"을 그대로 옮긴다. 이 절의 JSON은 `tests/test_context_pack_docs_contract.py`가 DTO와 비교한다.

1단계(공존 단계)에서 기존 Vault Graph 컨텍스트 팩 빌더 및 회귀 테스트 스위트와의 100% 하위 호환성을 보장하기 위해 유지되는 Context Pack JSON 규격입니다:

Minimum JSON shape:

```json
{
  "context_pack_schema_version": "context-pack-v1",
  "pack_id": "sha256-of-canonical-pack-identity",
  "goal": "Implement GraphRAG MVP",
  "scope": {
    "requested": {
      "vault_ids": ["main"],
      "content_scopes": ["wiki", "docs"],
      "include_cross_vault": false
    },
    "actual_scopes": [
      {
        "vault_ids": ["main"],
        "content_scopes": ["wiki", "docs"],
        "include_cross_vault": false,
        "scope_key": "main:wiki,docs:local"
      }
    ]
  },
  "vaults": [
    {
      "vault_id": "main",
      "display_name": "Main Vault"
    }
  ],
  "vault_revisions": [
    {
      "vault_id": "main",
      "revision": "git-sha-or-file-snapshot-id",
      "revision_kind": "git"
    }
  ],
  "backend": {
    "metadata_store": {
      "name": "sqlite",
      "used": true
    },
    "keyword_index": {
      "name": "sqlite-fts5",
      "used": true
    },
    "vector_store": {
      "name": "chroma",
      "used": true
    },
    "graph_store": {
      "name": null,
      "used": false
    },
    "graph_projection": {
      "name": null,
      "used": false
    }
  },
  "retrieval_policy_version": "retrieval-policy-v1",
  "budget": {
    "max_tokens": 8000,
    "max_evidence_items": 24,
    "max_excerpt_tokens": 320,
    "used_tokens": 0,
    "omitted_items": 0
  },
  "store_revisions": [
    {
      "kind": "metadata",
      "revision": "metadata-revision-id",
      "vault_id": "main",
      "scope_key": "main:wiki,docs:local"
    },
    {
      "kind": "keyword",
      "revision": "keyword-revision-id",
      "vault_id": "main",
      "scope_key": "main:wiki,docs:local"
    },
    {
      "kind": "vector",
      "revision": "vector-revision-id",
      "vault_id": "main",
      "scope_key": "main:wiki,docs:local"
    }
  ],
  "generated_at": "2026-06-04T00:00:00+09:00",
  "current_state": [],
  "relevant_pages": [],
  "relevant_sources": [],
  "decisions": [],
  "constraints": [],
  "open_questions": [],
  "warnings": [],
  "evidence": []
}
```

## 8. 독립 모듈 5개

보관본 [SPEC v5.0](archive/SPEC-v5.0.md) §10~12를 그대로 옮긴다. 이미 구현된 패키지(`graph_search`, `graph_document`, `text_embeddings`, `vector_search`, `vector_index`)의 계약이기 때문이다. 아래 본문의 §10은 8.1절을 가리키고, §1.7·§7.1·§9.3은 보관본 SPEC v5.0의 절을 가리킨다.

### 8.1 Independent Graph Search Design Proposal

**Status:** Proposed supplementary design. Implementation and default-engine
replacement are not approved or completed by this documentation addition.

독립적으로 설치·호출 가능한 `graph_search`의 상세 계약과 검증 계획은
[GS-20261003: 독립 graph_search 상세 설계](design/specs/2026-10-03-graph-search-ko.md)에,
기존 시스템과 연결하는 계층은
[GS-20261003-INTEGRATION: 연동 설계](design/specs/2026-10-03-graph-search-integration-ko.md)에
정의한다. 연동 설계는 같은 부모 계약의 보조 문서다.

코어는 노드·간선 ID와 끝점만 받고, 대표 최단 경로 탐색과 제한된 단순 경로
열거를 별도 API로 제공한다. Vault ID, 신뢰도, 관계 종류, 근거, 리비전,
저장소와 CLI/MCP/HTTP는 코어의 계약에 포함하지 않는다.

연동 어댑터는 기존 `GraphProjection` 입출력을 유지하며 필터·간선 상한,
ID 대응, 복수 경로 점수·순위, 빌드 ID, 근거 연결을 보존한다.
대표 경로만으로 기존 복수 경로 결과를 대체하지 않는다. 순환을 피해 탐색이
종료되는 동작은 §7.1과 §9.3의 전역 SCC 검증을 대체하지 않는다.

설계 문서의 완성, 모듈 구현, 실제 연동, production-ready 검증은 각각
구분한다. 모듈의 FA-01–FA-11과 연동의 IT-01–IT-12, 독립 wheel 설치,
공개 조회 경로의 회귀, 운영 부하·메모리 측정 증거가 해당 완료 판단의 기준이다.
미확정 운영 상한과 v1 호환성 보정은 새 설계의 Open Decisions에 유지한다.
기존 Phase 3C 계약과 본 문서의 승인된 제품 경계는 이번 추가로 변경하지 않는다.


### 8.2 Independent Graph Document Design Proposal

독립 문서 그래프 패키지의 상세 제안은
[DG-20261004: graph_document](design/specs/2026-10-04-graph-document-ko.md)에,
기존 Vault 기능 재사용과 호환성 경계는
[DG-20261004-INTEGRATION](design/specs/2026-10-04-graph-document-integration-ko.md)에 정의한다.
연동 문서는 같은 부모 계약의 보조 설계다.

패키지는 일반 문서의 구조에서 항목·관계·근거를 추출하고, 문서별 기여와 SQLite 파생 상태를 관리한다.
경로 계산은 §10의 graph_search를 사용한다. 기본 추출은 규칙 기반이며 의미 추출은 외부 스키마 제한
추출기로 연결하는 대안과 검증 gate를 부모 §15에 기록한다.

새 설계는 기존 graph_search 계약, Vault ID·근거·scope·순위, sqlite-graph-v2와 기본 factory를 변경하지 않는다.
독립 package 구현, 기존 공개 경로의 전환, 운영 준비 완료는 DG-FA·DG-IT 실행 증거와 별도 gate로 판정한다.
이 추가는 설계 문서 제출이며 데이터 이전이나 모듈 구현을 완료했다는 의미가 아니다.


패키지별 독립 사용을 먼저 검증하고 연동을 단계적으로 구현하는 순서는
[graph_search·graph_document 구현 순서](design/plans/2026-10-04-graph-modules-implementation-order-ko.md)에 정리한다.
이는 실행 순서 제안이며 기존 네 설계 계약의 범위·승인 상태를 변경하지 않는다.

### 8.3 Independent Embedding And Vector Modules

사용자가 승인한 2차 리팩터링의 책임·입출력·삭제 범위·실패 처리·호환성 계약은
[임베딩·벡터 모듈 계약](design/specs/2026-10-06-vector-modules-ko.md)에 정의한다.
`text_embeddings`, `vector_search`, `vector_index`는 Vault와 그래프 모듈에 의존하지 않는다.
Vault 전용 정책과 기존 저장 형식의 변환은 `vault_graph.indexing.vector_index_adapter` 등 Vault Graph의 책임별 어댑터에서 수행한다([ARCHITECTURE.md](ARCHITECTURE.md) §2).
이 분리는 §1.7의 포트·어댑터 경계를 따르며 불변성 엔진의 기능이나 정책을 변경하지 않는다.

## 9. 단계

상세 계약, 실패 동작, 수용 기준은 [spec 2026-10-29-local-graph-memory-layer](specs/2026-10-29-local-graph-memory-layer/spec.md)에 있다. 이 절은 요약이다.

### 9.1 1차 작업

| 단계 | 내용 | 선행 |
|---|---|---|
| 1차-0 | 제품 계약 문서 정리(이 SPEC, v5.0 보관, 경계 문서 원칙 통일) | 없음 |
| 선행 | 모듈화 보완1(기능 간 가져오기 방향 테스트)·보완5(M12↔M17 binding 순환)는 1차-2 전에, 보완6은 1차-3 전에. 나머지 보완은 1차와 나란히 또는 1차 뒤 | 1차-0 |
| 1차-1 | 측정1 기준선(변경 전) | 1차-0 |
| 1차-2 | `vault-map.json` 읽기(결정9) | 보완1, 보완5 |
| 1차-3 | 세션 시작 회상 `vg hook session-start`(결정10) | 1차-2 |
| 1차-4 | MCP `remember`(결정8)와 README 수정. 2026-11-02 [장기 기억 spec](specs/2026-11-02-vault-long-term-memory/spec.md)이 `update_memory`·`retire_memory`와 `basis`별 경로(publish-draft, `review propose`)로 넓혔다 | 1차-2 |
| 1차-5 | 한국어 조사 처리(색인 때 조사를 뗀 별도 열) | 1차-1 |
| 1차-6 | 측정1 재측정, 결과 기록 | 1차-5 |

### 9.2 n차 로드맵 (1차 이후)

각 항목은 시작 전에 별도 spec으로 승격한다. 1차에서는 구현하지 않는다.

| 코드 | 내용 | 선행 |
|---|---|---|
| n차-1 | 대체된 claim을 기본 결과와 회상에서 빼고 최근 기억에 가중치를 준다. Vault `supersede-claim` 결과를 읽는다 | 의존4, 의존5 |
| n차-2 | 기억 frontmatter(`peer`, `kind`, `observed_at`, claim 상태) 해석과 프로필 조회 `get_profile`. 모르는 스키마 버전은 경고한다 | 의존5 |
| n차-3 | 코드와 기억을 질의 하나로 찾는다. MCP `explain_symbol`, 코드 청크 색인 여부 결정 | 1차 완료 |
| n차-4 | 임베딩 모델 교체를 측정1과 같은 방법으로 비교한 뒤 정한다 | 측정1 |
| n차-5 | 폴링 watch를 파일 변경 이벤트(`watchfiles`) 기반으로 바꾼다 | 없음 |
| n차-6 | `raw/sessions/<agent>/`를 수집 대상별(Claude Code, Codex, ChatGPT)로 역할 분류하고 evidence 모드에서 찾는다 | 의존2 |
| n차-7 | `project-bindings.json`과 자체 Vault 등록을 `vault-map.json` 읽기로 대체하고 정리한다 | 1차-2 |
| n차-8 | MCP `recall` 도구와 질문 기반 회상 | 1차-3 |
| n차-9 | 측정1 조건B를 실제 수집기 결과로 다시 측정한다 | 의존2 |
| n차-10 | `vg memory review`(읽기 전용): 사용 기록으로 고정·정리·모순 후보를 보인다 | 1차-3, 사용 기록 2주 운영 |
| n차-11 | 첫 사용자 프롬프트로 검색해 본문 상위 몇 개를 넣는 회상(UserPromptSubmit 훅) | 측정1, 의존1 확장 |
| n차-12 | `raw/sessions/` 대화 기록에서 `m:` ID 언급을 세어 사용 집계를 보강한다 | 의존2 |

### 9.3 Vault·vault-builder 쪽 의존성

vault-graph는 아래 항목을 만들지 않는다. 소유한 쪽이 구현한다.

| 코드 | 의존 | 소유 | 상태 | vault-graph에 미치는 영향 |
|---|---|---|---|---|
| 의존1 | 훅 실행기 `vault_hooks.py`. SessionStart는 vg가 있으면 `vg hook session-start`의 출력을, 0이 아니면 `recall.sh`를 쓴다. PreCompact·SessionEnd는 `vg hook capture`를 부르고, 0이 아니면 직접 수집한다 | vault-builder(사용자 범위 훅, 계약6) | 구현됨. `install --with-hooks`가 `$HOME/.claude/settings.json`에 SessionStart·PreCompact·SessionEnd 항목을 하나씩 더한다. 수집 항목(PreCompact·SessionEnd)의 시간 제한은 60초다. uninstall은 실행기를 부르는 항목만 지운다 | 회상과 수집 시점이 실제 세션에 들어간다. `--with-hooks` 없이 설치하면 훅 항목이 없다 |
| 의존2 | 세션 수집기 `sessions capture`와 `raw/sessions/`(결정5) | Vault 도구, vault-builder 템플릿 배포 | 구현됨 | 측정1 조건B, 가치1, n차-6·9·12, `vg hook capture` |
| 의존3 | Vault `AGENTS.md` 규칙1 예외: 수집기가 `raw/sessions/`에 새 파일을 추가하는 것만 허용(결정11) | Vault, vault-builder | 구현됨 | 의존2의 전제 |
| 의존4 | 정리 스킬, 자동 기억 확정 규칙(결정6) | Vault 도구 | 추론 사실의 검토 경로(`memory-proposal`, `review propose`, 승인 시 발행, 계약4)는 구현됨. 정리 스킬은 미구현 | `basis: inferred` 쓰기, n차-1 |
| 의존5 | 기억 frontmatter 스키마 `vault-memory/v1`. `pin`, `memory_kind: rule\|correction\|decision\|preference`, status `retired`와 `retired_reason`·`retired_at`(계약2) | vault-builder가 Vault 도구에 담아 배포 | 구현됨 | 회상 구획A·C, 쓰기 draft, 검색의 `retired` 제외, n차-2 |
| 의존6 | publish-draft `--json` 결과와 draft 형식의 버전 표시(`draft_version`, 계약1), frontmatter만 바꾸는 `patch-page`(계약3) | Vault 도구 | 구현됨. 기존 Vault에는 계약 버전 4 마이그레이션(계약7)으로 전한다. 마이그레이션 전 Vault에서는 세 쓰기 도구가 "계약 4로 마이그레이션하라" `error`를 돌려준다 | 세 쓰기 도구 |
| 의존7 | `vault-map.json` version 2 형식 유지, 선택 필드 `default_write_vault`, `set-role`·`set-default-write` 명령(계약5) | vault-builder | 구현됨 | 1차-2, 저장 Vault 고르기 |

vault-builder 요청 문서: vault-builder 저장소 `docs/superpowers/specs/2026-10-29-vault-graph-requests-ko.md`(커밋 전). 요청1=의존3, 요청2=의존2, 요청3=의존1, 요청4=의존6, 요청5=의존7, 요청6=의존5, 요청7=의존4.

## 10. 보관 문서

- [SPEC v1.2](archive/SPEC-v1.2.md): Vault 위 읽기 전용 검색 계층 시기의 계약. 현재 코드 대부분이 이 시기에 만들어졌다.
- [SPEC v5.0](archive/SPEC-v5.0.md): Software Invariant Engine. 2026-10-29에 보관했다. VS-1~6은 구현하지 않는다.

보관 문서는 고치지 않는다. 과거 설계 문서가 `docs/SPEC.md`의 절을 가리키면 해당 시기의 보관본에서 찾는다.
