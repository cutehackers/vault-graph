# Research: L1/L2/L3 기억 계층과 vault-graph의 역할

작성 2026-11-05. 다른 저장소 경로는 `vault-builder:` 접두어를 붙였다. 사람 홈 폴더는 `$HOME`으로 적는다. 코드나 문서로 확인하지 못한 내용은 "추정"으로 표시했다.

계층 정의는 `vault-builder:docs/html/project-memory-structure.html:210-350`을 따른다.

- L1 빠른 기억: Claude Code 자동 기억 `$HOME/.claude/projects/<key>/memory/`. Claude Code가 세션 시작 때 `MEMORY.md`를 읽는다.
- L2 장기 기억: Vault 저장소(personal, team, project)의 `wiki/` 페이지. Vault 도구가 검증한다.
- L3 프로젝트 요약: Vault의 `wiki/maps/projects/<project>.md`.

## 1. 현재 구성과 소유

### 1.1 기계 목록

| 코드 | 구성 요소 | 계층 이동 | 소유 | 근거 |
|---|---|---|---|---|
| 부품1 | Claude Code 자동 기억 쓰기와 `MEMORY.md` 로드 | 세션 → L1 | Claude Code | 외부 제품 |
| 부품2 | `memory-scan --json`: L1 노트별 `imported` 여부 판정 (원본 hash를 source page `raw_sha256`과 비교) | L1 읽기 | vault-builder | `vault-builder:tools/wiki/lib/memory_scan.py:209-303`, `:406-419` |
| 부품3 | `memory-cleanup` 스킬: L1 노트를 `raw/imports/claude-memory/`에 복사하고 ingest·draft·publish | L1 → L2 | vault-builder (사람이 Vault 세션에서 요청) | `vault-builder:.agents/skills/memory-cleanup/SKILL.md:30-46` |
| 부품4 | `sessions capture`: transcript jsonl을 `raw/sessions/`에 새 part로 추가 | 세션 → raw | vault-builder | `vault-builder:tools/wiki/lib/session_capture.py:431-479`, `:601-675` |
| 부품5 | `session-capture` 스킬: 수동 수집 | 세션 → raw | vault-builder | `vault-builder:.agents/skills/session-capture/SKILL.md` |
| 부품6 | 훅 실행기 `vault_hooks.py` (`session-start` 20초, `capture` 25초, 직접 수집 30초) | 트리거 | vault-builder | `vault-builder:tools/vault_migration/assets/vault-hooks/vault_hooks.py:41-44`, `:131-164`, `:206-279` |
| 부품7 | `maps build`의 프로젝트 요약 생성 (Open Work, Current Decisions, Corrections and Rules, 1,500토큰) | L2 → L3 | vault-builder | `vault-builder:tools/wiki/lib/maps.py:56-57`, `:255-305` |
| 부품8 | publish 뒤 지도 자동 재생성 | L2 → L3 | vault-builder | `vault-builder:tools/wiki/lib/publish.py:161-172`, `vault-builder:tools/wiki/cli.py:861-868` |
| 부품9 | `recall.sh`: 연결 Vault의 L3 페이지에서 섹션을 잘라 출력 | L3 → 세션 | vault-builder (설치본 `$HOME/.claude/skills/project-memory/scripts/recall.sh`) | `vault-builder:tools/vault_migration/assets/project-memory/scripts/recall.sh:12-27`, `:239-295` |
| 부품10 | `/project-memory` 스킬: 필요할 때 `recall.sh` 호출 | L3 → 세션 | vault-builder | 같은 파일 |
| 부품11 | `vg hook session-start`: 구획A 고정 기억 400토큰, 구획B 최신순, 구획C 대체·폐기 알림, 구획D 검토 대기 수. 기본 1,500토큰 | L2 → 세션 | vault-graph | `src/vault_graph/interface/cli/hook_commands.py:77-148`, `src/vault_graph/context/pack/recall.py:38-50`, `:156-210`, `src/vault_graph/context/pack/recall_pins.py:82-101` |
| 부품12 | 세션 시작 전 빠른 색인 갱신과 백그라운드 `vg index` | 색인 | vault-graph | `hook_commands.py:161-270`, `docs/specs/2026-11-02-vault-long-term-memory/spec.md:339-363` |
| 부품13 | `vg hook capture`: 실행 시점만 정하고 부품6의 `capture --direct` 호출 | 트리거 | vault-graph | `hook_commands.py:272-297` |
| 부품14 | `remember`, `update_memory`, `retire_memory` (stated → publish-draft, inferred → review propose) | 에이전트 → L2 | vault-graph (쓰기는 Vault 도구) | `src/vault_graph/interface/mcp/mcp_memory_tools.py:66-175`, `src/vault_graph/operation/memory/memory_write_service.py`, `src/vault_graph/operation/memory/memory_drafts.py:33-130` |
| 부품15 | `summarize_project_memory`: 질의 시점에 색인에서 결정·이슈·요약을 모아 투영 | L2 → 프로젝트 요약 | vault-graph | `src/vault_graph/context/memory/project_memory.py:43-140` |
| 부품16 | cwd → 프로젝트 판정 (main worktree, origin URL) | 공통 | 양쪽에 각각 구현 | `src/vault_graph/operation/integration/vault_map.py:79-100`, `:262-290`, `vault-builder:tools/wiki/lib/memory_scan.py:82-207`, `recall.sh:58-76` |

vault-graph는 L1을 읽지 않는다. `src` 안에서 `.claude/projects`나 `MEMORY.md`를 찾으면 0건이다.

### 1.2 중복과 어긋남

- 발견1 프로젝트 요약이 세 벌이다. 부품7(Vault L3 페이지), 부품11 구획B(L2 직접), 부품15(질의 시점 투영)가 서로 다른 규칙으로 "이 프로젝트의 기억"을 고른다. 부품7은 frontmatter `project`가 있는 페이지만 쓴다(`maps.py:270-273`). 부품11은 `project`가 없는 페이지를 모든 프로젝트 것으로 본다(`recall.py:358-363`). 이 차이 때문에 vault-graph 회상 18개가 모두 personal Vault에서 왔고 다른 프로젝트 페이지가 섞였다.
- 발견2 회상 경로가 두 개다. vg가 있으면 부품11(L2 직접), 없거나 20초 안에 끝나지 않으면 부품9(L3)로 간다. 두 경로의 출력이 달라서, 같은 세션이라도 vg 응답 시간에 따라 다른 기억이 들어간다. 관측한 vg 시간 16초는 20초 제한에 가깝다.
- 발견3 vault-graph `remember` draft에는 `project` 필드가 없고 `tags`가 빈 목록이다(`memory_drafts.py:39-57`). 그래서 vg로 저장한 기억은 L3에 나오지 않는다. 부품7은 교정을 `tags`의 `correction`·`rule`로 고르는데(`maps.py:276`), vault-graph는 `memory_kind`로 표시한다. 같은 뜻을 두 스키마가 다르게 적는다.
- 발견4 수집 경로는 두 개지만 실제 쓰기는 하나다. 부품13은 부품6의 `capture --direct`를 다시 부르므로 Vault 고르기와 쓰기는 `sessions capture` 한 곳이다. 이것은 의도된 중복이다(`spec.md:180-198`, 결정S4).
- 발견5 L1 → L2 이동은 부품3 하나뿐이고 사람이 Vault 세션에서 요청해야 돈다. 이 프로젝트의 L1 노트 4개가 모두 `imported: false`다.
- 발견6 세션 원문 → L2 증류 경로는 어디에도 없다. `raw/sessions/`는 claim 근거로 인용할 수만 있다(`vault-builder:tools/wiki/lib/ingest.py:44`). 수집된 11개 원문이 wiki에 반영되지 않았다.
- 발견7 프로젝트 판정 코드가 세 곳에 따로 있다(부품16). 규칙이 바뀌면 세 곳을 같이 고쳐야 한다.
- 발견8 문서끼리 다르다. 설계 HTML은 훅이 L3를 넣는다고 한다(`project-memory-structure.html:249`, `:347`, `:545`). `vault-builder:docs/usage.md:697`은 요약을 자동으로 넣지 않는다고 한다. 실제 코드는 `--with-hooks`로 설치하면 넣는다. 단 vg가 성공하면 L3가 아니라 L2를 넣는다. 둘 다 현재 동작과 맞지 않는다.

## 2. 조율을 vault-graph로 옮길 것인가

지켜야 할 규칙:

- 규칙 "Vault는 vault-graph 없이도 동작한다": `docs/SPEC.md:55`, `vault-builder:README.md:67`, 이전 spec 결정10(`docs/specs/2026-10-29-local-graph-memory-layer/spec.md:266`).
- 경계: vault-graph는 Vault 파일과 `raw/`를 직접 쓰지 않는다. 쓰기는 publish-draft, review propose, 수집 실행기 세 길뿐이다(`AGENTS.md:3-20`, `docs/SPEC.md:59-65`).
- 원칙1: vault-graph는 LLM을 부르지 않는다. 요약과 사실 추출은 호출한 에이전트가 한다(`docs/SPEC.md:59`).

| 관심사 | 옮기자는 근거 | 남기자는 근거 | 판단 |
|---|---|---|---|
| (a) 원본과 검증 | 없음 | 원칙2·3, 경계 규칙. Vault만 쓰는 사용자도 검증이 필요하다 | Vault에 남긴다. 논쟁 여지 없음 |
| (b) 읽기·회상·순위 | 이미 vault-graph가 한다. 여러 Vault를 합친 순위, 예산, 증분 색인은 vault-graph만 할 수 있다 | `recall.sh`는 vg가 없을 때의 대체 경로로 필요하다 | vault-graph가 주 경로, `recall.sh`는 대체 경로로 둔다. 단 두 경로가 같은 프로젝트 범위 규칙을 써야 한다(발견1·2) |
| (c) 계층 사이 이동 | L1 미반영과 세션 미증류를 찾는 일은 결정적이고 vault-graph 색인이 이미 `raw/`를 읽는다. 세션 시작마다 알릴 수 있다 | 증류는 판단이 필요해 LLM이 해야 하는데 vault-graph는 LLM을 부르지 않는다. L1 복사본은 `raw/imports/`에 써야 하는데 vault-graph는 `raw/`에 쓸 수 없다. L3 생성은 Vault 도구가 publish마다 이미 한다 | 판단과 쓰기는 에이전트와 Vault 도구에 남긴다. vault-graph는 "후보 찾기"와 "알림"만 맡을 수 있다 |
| (d) 트리거(훅) | 훅 실행기는 이미 vg를 먼저 부른다. vg가 시점을 정하는 모델이 수집에서 동작한다 | 훅에는 LLM이 없고 시간 제한(20초, 25초)이 있다. 증류를 훅에서 돌릴 수 없다 | 훅 설치는 vault-builder에 남긴다. 훅 안에서 vault-graph가 할 일은 회상과 "할 일 알림 한 줄"뿐이다 |

결론: "조율 전체를 vault-graph로" 옮기는 것은 원칙1과 경계 규칙에 막힌다. 옮길 수 있는 것은 (b) 전부와 (c)의 후보 찾기, (d)의 알림이다.

## 3. 목표 구조 후보

공통 흐름: 세션 jsonl → `raw/sessions/` 수집 → 후보 추출 → Vault 도구로 검토·발행 → L3 요약 → 세션 시작 주입.

### 구조A Vault 중심, vault-graph는 L3를 읽기만

- 옮기는 것: 없음. vault-graph 회상의 구획B를 Vault L3 페이지 섹션으로 바꾼다. 구획A(고정)와 구획C(알림)는 유지한다.
- 새로 만드는 것: vault-builder에 세션 증류 스킬(`memory-cleanup`과 같은 형태, 근거는 `raw/sessions/` 경로).
- 경계 변경: 없음.
- 이주: (1) `remember` draft에 `project` 필드 추가(발견3). (2) 구획B가 L3 페이지를 읽게 변경. (3) 증류 스킬 추가.
- 위험: L3는 Vault마다 따로 만들어지므로 여러 Vault를 합친 순위가 사라진다. 결정14(모든 Vault를 합친 순위)와 충돌한다. 증류는 여전히 사람이 Vault 세션에서 요청할 때만 돈다.

### 구조B vault-graph 조율, L3는 vault-graph 파생 투영

- 옮기는 것: L3 생성을 vault-graph로. 부품15를 확장해 색인 발행 때 Graph Home에 프로젝트 요약을 만들고, 세션 시작은 이것을 읽는다. 지울 수 있고 다시 만들 수 있다.
- 새로 만드는 것: vault-graph MCP 도구 `list_memory_candidates`(이름 추정). 결정적으로 고른 후보를 돌려준다. 후보는 미반영 L1 노트와, 어떤 wiki claim도 근거로 인용하지 않은 세션 part다. 에이전트가 읽고 판단해 `remember`(inferred면 검토 대기열)로 쓴다. Vault L3 페이지는 `recall.sh` 대체 경로용으로만 남긴다.
- 경계 변경: vault-graph가 L1 폴더를 읽는다(Vault 밖, 읽기만). L1을 L2 근거로 쓰려면 원본을 `raw/imports/`에 넣어야 하므로 Vault에 `memory import` 같은 결정적 명령이 필요하다(새 계약). vault-graph는 그 명령을 실행만 한다(경계 4번째 길 추가).
- 이주: (1) 발견3 수정. (2) 프로젝트 범위 규칙을 하나로 정하고 투영과 회상에 적용. (3) Graph Home 요약 투영. (4) 후보 도구. (5) Vault `memory import` 계약. (6) 세션 시작에 "미반영 L1 N개, 미증류 세션 M개" 한 줄.
- 위험: 요약 규칙이 Vault 쪽 `maps.py`와 vault-graph 쪽 두 곳에 남는다. 대체 경로와 주 경로가 계속 다른 내용을 낸다. 경계에 쓰기 길이 하나 늘어난다.

### 구조C 분담: Vault는 원본·이동·L3 페이지, vault-graph는 후보 찾기·알림·회상

- 옮기는 것: 없음. 각자 하던 일을 계약으로 맞춘다.
- Vault 쪽: L3 페이지(부품7)는 그대로 Vault가 만든다. vg가 없을 때의 기본 경로다. `memory-cleanup`에 세션 증류 단계를 더하거나 별도 스킬을 둔다. 세션 part가 증류됐는지는 "그 part를 근거로 인용한 wiki 페이지가 있는가"로 판정한다. 상태 파일 없이 `memory-scan`의 `raw_sha256` 방식과 같다.
- vault-graph 쪽: (1) 회상 구획B에 L3와 같은 프로젝트 범위 규칙을 쓴다. (2) 세션 시작 회상에 구획D처럼 "미반영 L1 N개, 미증류 세션 M개, 정리 방법" 한 줄을 더한다. L1은 읽기만 한다. (3) `remember`가 `project`를 채운다. (4) 증류 판정과 범위 규칙을 계약 문서로 고정해 양쪽이 같은 결과를 낸다.
- 경계 변경: vault-graph가 L1 폴더를 읽는 것 하나. 쓰기 길은 늘지 않는다. 증류의 판단과 쓰기는 에이전트가 기존 `remember`(근거: `raw/sessions/` 경로) 또는 Vault 스킬로 한다.
- 이주: (1) `remember` draft에 `project` 추가와 `memory_kind`·`tags` 대응 정리. (2) 범위 규칙 결정(미결1) 뒤 `recall.py:358-363` 변경. (3) 문서 정정(발견8). (4) 세션 시작 알림 한 줄. (5) Vault 증류 스킬. (6) 세션 시작 16초 원인 측정과 단축.
- 위험: 증류는 여전히 사람이나 에이전트가 시작해야 돈다. 알림을 무시하면 원문이 계속 쌓인다. 발견1의 세 벌 중 부품15는 남는다.

| 비교 | 구조A | 구조B | 구조C |
|---|---|---|---|
| Vault만 쓰는 사용자 | 그대로 동작 | 그대로 동작, 단 요약 규칙이 갈라짐 | 그대로 동작 |
| 경계 변경 | 없음 | L1 읽기 + 새 쓰기 길 | L1 읽기 |
| 여러 Vault 합친 회상(결정14) | 잃음 | 유지 | 유지 |
| 새 계약 | 증류 스킬 | `memory import`, 후보 도구 | 증류 판정·범위 규칙 문서 |
| 작업량 | 작음 | 큼 | 중간 |

## 4. 권고

구조C를 권한다. 이유는 세 가지다.

1. 지금 막힌 원인은 소유 위치가 아니라 규칙 불일치다. 발견1·3이 고쳐지면 지금 있는 L1 → L2(부품3)와 L2 → L3(부품8)가 이 프로젝트에서 바로 동작한다.
2. 증류는 LLM 판단이 필요해 원칙1 때문에 vault-graph 안에 들어갈 수 없다. vault-graph가 할 수 있는 일은 "무엇이 밀려 있는지 알리기"이고, 이것은 경계를 바꾸지 않는다.
3. Vault만 쓰는 사용자의 경로(`recall.sh` + L3)가 그대로 남고, 두 회상 경로가 같은 범위 규칙을 쓰면 발견2의 출력 차이가 줄어든다.

### 사용자가 정할 것

미결1 회상에서 `project` frontmatter가 없는 페이지를 어떻게 다룰 것인가

- 배경: 지금 vault-graph는 모든 프로젝트 것으로 보고, L3는 빼고 있다. 결정15 때문에 Vault 종류(role)로 나눌 수 없다.
- 옵션1: 구획B에서 뺀다(L3와 같음). 잃는 것: `project`를 안 단 기존 personal 페이지가 회상에서 빠진다.
- 옵션2: `vault-map.json` 프로젝트 항목에 "이 Vault의 무표시 페이지를 포함" 선택 필드를 둔다. 잃는 것: vault-builder 계약 변경이 필요하다.
- 옵션3: 지금대로 둔다. 잃는 것: 다른 프로젝트 기억이 계속 섞인다.

미결2 세션 원문을 L2로 증류하는 일을 어디서 시작할 것인가

- 옵션1: Vault 스킬(`memory-cleanup` 확장). 잃는 것: 프로젝트 세션 안에서는 바로 못 하고 Vault 세션을 따로 열어야 한다.
- 옵션2: 프로젝트 세션의 에이전트가 vault-graph `remember`로 한다(근거는 `raw/sessions/` 경로, inferred는 검토 대기열). 잃는 것: L1 노트의 `raw/imports/` 복사 단계가 없어 L1 증류에는 못 쓴다.

미결3 세션 시작 회상에 "밀린 정리" 알림 한 줄을 넣을 것인가

- 옵션1: 넣는다. vault-graph가 L1 폴더를 읽기 시작한다. 잃는 것: 매 세션 약 30토큰(추정).
- 옵션2: 넣지 않는다. 잃는 것: 밀린 정리를 사람이 따로 확인해야 한다.

미결4 L3의 원본을 Vault 페이지로 둘 것인가, vault-graph 파생 투영으로 둘 것인가

- 옵션1: Vault 페이지(구조C). 잃는 것: 여러 Vault를 합친 요약이 L3에 없다. vault-graph 회상이 이를 대신한다.
- 옵션2: vault-graph 투영(구조B). 잃는 것: 요약 규칙이 두 곳에 생긴다.

미결5 vault-graph 회상 구획B가 L3 페이지를 읽을 것인가, L2를 직접 읽을 것인가

- 옵션1: L2 직접(지금). 잃는 것: vg 경로와 `recall.sh` 경로의 출력이 계속 다르다.
- 옵션2: L3 섹션을 먼저 넣고 남은 예산을 L2 최신순으로 채운다. 잃는 것: Vault마다 L3가 있어야 효과가 있고, 예산 분배 규칙을 새로 정해야 한다.

## 5. 외부 사례

아래 요약은 이번에 원문을 다시 열어 확인하지 않았다. 전부 추정으로 본다.

- Claude Code memory (https://docs.claude.com/en/docs/claude-code/memory): `CLAUDE.md` 계층과 자동 기억을 세션 시작 때 읽는다. 주는 시사점: L1은 Claude Code가 소유하고 형식이 바뀔 수 있으므로, vault-graph는 읽기만 하고 형식 해석을 Vault의 `memory-scan` 한 곳에 두는 편이 안전하다.
- MemGPT / Letta (https://arxiv.org/abs/2310.08560, https://docs.letta.com/): 문맥 안 core memory(예산 고정), 대화 기록을 검색하는 recall memory, 장기 archival memory 세 층. 층 사이 이동은 에이전트가 도구 호출로 한다. Letta의 sleep-time agent는 정리를 대화 밖에서 비동기로 한다. 시사점: L1≈core, `raw/sessions/`≈recall, L2≈archival로 대응하고, 이동은 에이전트의 도구 호출(remember)로 하며 훅 같은 짧은 경로에 넣지 않는다.
- mem0 (https://arxiv.org/abs/2504.19413, https://github.com/mem0ai/mem0): 대화에서 후보 사실을 추출하고, 비슷한 기존 기억과 비교해 ADD·UPDATE·DELETE·NOOP 중 하나를 고른다. 시사점: 증류 결과를 `remember`·`update_memory`·`retire_memory`에 대응시키면 되고, 비교를 위해 후보마다 관련 기존 페이지를 함께 보여줘야 한다.
- Zep / Graphiti (https://arxiv.org/abs/2501.13956, https://github.com/getzep/graphiti): 원문 episode를 보존하고, 사실에 유효 시작·종료 시점을 달아 지우지 않고 무효화한다. 요약은 그래프에서 다시 만드는 파생물이다. 시사점: `raw/sessions/` 보존, `retired`·`superseded_by` 방식과 맞고, L3를 다시 만들 수 있는 파생물로 보는 구조B·C 모두와 맞는다.
