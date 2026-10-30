# Spec: vault-graph를 Vault 위 로컬 검색·회상 계층(Local-Graph)으로 재정의

- task: 20261029-vault-graph-vault-973b
- spec id: 2026-10-29-local-graph-memory-layer
- route: design-first
- base: `feat/jh/local-graph` @ 28f1c96 (v0.2.1)

## 1. Problem

vault-graph의 코드와 README는 "Vault 위의 읽기 전용 검색 계층"을 구현하고 있는데, 활성 제품 계약은 다른 제품을 정의한다. 그리고 사람이 원하는 기억 기능(세션 시작 회상, 직접 기록, 한국어 검색)은 아직 없다.

1. 문제1 활성 계약과 코드가 다른 제품을 말한다.
   - 활성 `docs/SPEC.md`는 v5.0 Software Invariant Engine이다. 목표4는 "문서와 코드 사이 접점 제거"(`docs/SPEC.md:108@28f1c96`)로, 코드와 결정 기록을 함께 조회하는 가치(설계 페이지 가치3)와 정면으로 부딪친다. 3단계에서는 Vault 연동을 선택 플러그인으로 강등한다(`docs/SPEC.md:1416-1419@28f1c96`).
   - v5.0 작업 VS-1~6은 하나도 구현되지 않았다(`docs/TODO.md:17-42@28f1c96`). 소스에 `invariants` 패키지가 없다(VG-MOD §9).
   - README 정의는 이미 검색 계층이다(`README.md:5@28f1c96`).
2. 문제2 경계 문서가 "Vault 쓰기 금지"를 말해서 결정8(remember)과 충돌한다.
   - `AGENTS.md:5-7@28f1c96` "read-only ... do not add behavior that edits ... Vault content"
   - `docs/TODO.md:10-12@28f1c96` "Do not add ... hidden write paths, or Vault mutation"
   - `docs/ARCHITECTURE.md:192-196@28f1c96` "Vault 문서 ... 읽기만 한다", "이 예외는 Vault 문서 편집 권한을 주지 않는다"
   - VG-MOD INV-01·INV-04(`docs/design/specs/2026-10-15-vault-graph-modular-architecture-ko.md:126,129@28f1c96`) "Vault 내용 기록은 허용하지 않는다". brief의 대상 목록에는 없지만 같은 원칙을 담고 있어 함께 확인했다.
   - `README.md:11-13@28f1c96` "does not publish wiki pages ... or replace Vault's validation workflow"
3. 문제3 프로젝트와 Vault 연결 정보가 두 벌이다(발견23). vault-graph는 자체 `<graph-home>/configs/project-bindings.json`(`src/vault_graph/operation/integration/project_binding_catalog.py:43@28f1c96`)과 자체 Vault 등록을 쓰고, `src` 전체에 `vault-map` 참조가 없다. 사용자 범위의 `vault-map.json`은 vault-builder가 install·link·unlink로 관리한다(brief §4).
4. 문제4 세션 시작 회상 진입점이 없다. CLI에 session-start 명령이 없다(`src/vault_graph/interface/cli/main.py`, `src` 전체 검색 결과 0건). 지금 실제로 쓰이는 회상은 vault-builder의 `recall.sh`로, 고정 섹션 3개를 최대 1,500토큰으로 출력한다(brief §4). 세션 시작 때 무엇을 어떤 형식으로 넣을지는 시장 제품 조사 `research/session-start-recall.md`(2026-10-30)를 근거로 정했다(4.2.3).
5. 문제5 MCP에 기록 도구가 없다. MCP 도구는 11개이고 `remember`가 없다(`src/vault_graph/interface/mcp/mcp_tools.py:42-52@28f1c96`).
6. 문제6 한국어 키워드 검색이 조사를 처리하지 못한다(발견24). FTS5 토크나이저가 `unicode61`이고(`src/vault_graph/storage/local/sqlite_keyword_index.py:46@28f1c96`), 질의는 토큰을 그대로 따옴표로 묶어 OR로 잇는다(`sqlite_keyword_index.py:252-260@28f1c96`). 그래서 "결정"으로 찾으면 본문의 "결정을"이 맞지 않는다. Vault 검색은 조사를 뗀다(Vault `tools/wiki/lib/search.py:116`, brief §4).
7. 문제7 vault-graph의 검색 가치(가치1 대량 원문 검색, 가치2 의미 검색)는 숫자로 확인되지 않았다. 이 컴퓨터에는 Graph Home(`$HOME/.vault-graph`)이 없어 운영 중이 아니다(brief §4).

확인 방법: `28f1c96` 기준으로 `docs/SPEC.md`, `docs/TODO.md`, `docs/ARCHITECTURE.md`, `AGENTS.md`, `README.md`, VG-MOD 문서를 직접 읽었다. `src`에서 `vault-map`, `session_start`, MCP 도구 이름, `tokenize=`, `DEFAULT_CONTENT_SCOPES`, `DEFAULT_CONTEXT_MAX_TOKENS`를 검색해 위 위치를 확인했다. Vault와 vault-builder(다른 저장소) 쪽 사실은 brief §4의 기록을 근거로 했다. spec 초안 뒤 메인 세션이 그 저장소와 사용자 범위 파일을 직접 읽어 7절 2~6번을 확인하고 4.2.1, 4.2.2, 4.2.4에 반영했다.

## 2. Intent

사람은 vault-graph를 "Vault 위에서 검색을 잘하는 도구"로 정하고 싶어 한다. 사람의 말로는 "의미검색 및 코드 기반 위키, 관계 추적 등"이다. 방향 이름은 Local-Graph다. 핵심은 Local이다. 모든 처리가 이 컴퓨터 안에서 끝나고 호스팅 서비스, API 키, LLM 호출이 없다. Graph(관계 추적)는 보조 가치다.

변경 후 성립해야 하는 것:

1. 제품 계약 문서가 하나만 활성 상태이고, 그것이 Local-Graph를 정의한다. 불변성 엔진 v5.0은 보관 문서로만 남는다(결정4 옵션1).
2. 프로젝트와 Vault의 연결 정보는 `vault-map.json` 하나가 원본이고, vault-graph는 그 파일을 읽기만 한다(결정9).
3. 새 세션이 시작될 때 vault-graph가 설치돼 있으면 vault-graph가 고른 관련 기억이 토큰 예산 안에서 문맥에 들어가고, 없으면 지금처럼 `recall.sh`가 돈다. 사람은 이것을 "핵심"이라고 했다(결정10).
4. 에이전트는 vault-graph MCP 하나로 기억을 남길 수 있고, 그 기록은 Vault 도구의 검증을 거친다(결정8).
5. vault-graph의 검색 가치가 숫자로 확인된다. 사람이 정한 성공 기준은 두 가지다. 측정1에서 `vg search`의 상위 5개 적중이 Vault 검색보다 높아야 하고, 새 세션 시작 때 관련 기억이 예산 안에 주입되어야 한다.
6. 1차 작업 이후의 일(n차)과 Vault 쪽에서 아직 구현되지 않은 일이 문서에서 보인다. 사람의 말로는 "vault에서 아직 구현되지 않은 부분들이 있다면 문서상에 표시 정도는 해둘 것"이다.

[가정] 기존 CLI·MCP 사용자는 1차 작업 동안 아무것도 고치지 않아도 된다고 기대한다(brief §6).

## 3. Non-goals

1. Vault 쪽 미구현 부분은 만들지 않는다. 세션 수집기(기능1, 결정5), Vault `AGENTS.md` 규칙1 예외(결정11), 정리 스킬(기능2, 결정6), 기억 frontmatter 스키마(`vault-memory/v1`), SessionStart 훅 스크립트의 분기는 의존성으로만 적는다(4.4절).
2. vault-builder에 보내는 요청 문서는 이 작업에서 쓰지 않는다. 메인 세션이 따로 추가하고, 이 spec은 그 경로만 참조한다.
3. vault-graph는 LLM을 부르지 않는다(결정7). 질의 답변, 요약, 사실 추출을 vault-graph 안에서 생성하지 않는다.
4. vault-graph는 Vault 파일을 직접 만들거나 고치거나 지우지 않는다. `raw/`에는 어떤 경로로도 쓰지 않는다. Vault에 쓰는 일은 remember가 Vault 도구의 publish-draft를 실행하는 것 하나다.
5. SPEC v5.0 불변성 엔진(VS-1~6)은 구현하지 않고, 내용을 고치지도 않는다. 파일 위치만 옮긴다.
6. 1차 작업에서 기존 CLI 명령, MCP 도구 11개, HTTP 응답의 이름·인자·응답 형식을 바꾸거나 지우지 않는다. `project-bindings.json`과 `vg setup --vault`, `vg vault add`도 1차에서는 지우지 않는다.
7. 1차 작업에서 n차 항목(4.3절 표)은 구현하지 않는다. 임베딩 모델 교체, 이벤트 기반 watch, claim 단위 대체 제외, `explain_symbol`, 코드 청크 색인, Codex·ChatGPT 수집 대상 색인이 여기에 해당한다.
8. 모듈화 보완 계획(보완1~9)의 내용은 이 spec에서 다시 설계하지 않는다. 1차 작업의 선행 조건으로 연결만 한다.
9. 측정1의 질문과 정답 목록, Vault의 개인 메모 내용은 이 저장소에 커밋하지 않는다.

## 4. Design

핵심 계약: vault-graph는 Vault 위에서 도는 로컬 검색·회상 계층이다. Vault 원문, wiki, 코드를 읽어 색인하고, 에이전트가 필요한 기억을 출처와 함께 토큰 예산 안에 돌려준다. 색인은 지워도 다시 만들 수 있는 파생 데이터다. vault-graph 프로세스는 Vault 파일을 직접 열어 쓰지 않는다. Vault에 쓰는 길은 하나이며, remember가 Vault 도구의 publish-draft를 실행해 그 검증을 거치게 하는 것이다. 연결 정보는 `vault-map.json`을 읽기만 한다. Vault는 vault-graph 없이도 동작한다.

용어: "Vault 도구"는 Vault 안의 `tools/wiki`와 스킬, "Vault 검색"은 Vault 도구의 `tools/wiki/lib/search.py`, "회상 묶음"은 세션 시작 때 문맥에 넣는 Markdown 결과, "넘김"은 vault-graph가 회상 묶음을 만들지 못해 훅이 `recall.sh`를 쓰게 하는 동작을 말한다.

### 4.1 제품 계약 문서 (결정4 옵션1, 문제1·문제2)

이 단계는 문서만 바꾸며, 1차 작업의 다른 모든 단계보다 먼저 한다.

1. `docs/SPEC.md`를 `docs/archive/SPEC-v5.0.md`로 옮긴다(`git mv`). 맨 위에 "2026-10-29 보관, 활성 계약은 `docs/SPEC.md`(Local-Graph)"라는 안내 한 줄만 추가하고 본문은 바꾸지 않는다.
2. 새 `docs/SPEC.md`(Local-Graph)를 쓴다. 다음 내용을 담는다.
   1. 제품 정의와 원칙: Local(호스팅·API 키·LLM 호출 없음), 원본은 Vault, `wiki/`는 검증 경로로만 바뀜, vault-graph는 Vault 파일을 직접 쓰지 않음, `raw/`에 쓰지 않음.
   2. 역할 분담 표: Vault, 사용자 범위(vault-builder가 설치한 router와 `vault-map.json`), vault-graph.
   3. 가치1~6과 가치가 아닌 것(설계 페이지 §01 요약).
   4. 읽기·쓰기 경계: 읽는 대상(Vault `raw/`·`wiki/`·`docs/`·`scratch/reports/`, 등록 저장소, `vault-map.json`), 쓰는 대상(Graph Home 파생 데이터와 설정, remember를 통한 publish-draft 실행).
   5. 인터페이스: 기존 CLI 명령·MCP 도구 11개·HTTP를 유지한다고 적고, 새 `vg hook session-start`와 MCP `remember`를 추가한다.
   6. 외부 계약: `vault-map.json` version 2 읽기, publish-draft 호출과 draft 형식, Vault 검색과의 비교 방법(측정1).
   7. Context pack 계약: 보관본 §9.6 "기존 Context Pack 호환성 계약"을 그대로 옮긴다. `tests/test_context_pack_docs_contract.py:18,29@28f1c96`가 `docs/SPEC.md`의 "Minimum JSON shape" 다음 JSON을 DTO와 비교하므로 이 제목과 JSON이 남아야 한다.
   8. 독립 모듈 5개: 보관본 §10~12(설계 문서 링크와 경계 요약)를 그대로 옮긴다. 이미 구현된 패키지의 계약이기 때문이다.
   9. 단계 표: 1차 작업(4.2절), n차 로드맵(4.3절), Vault 쪽 의존성(4.4절)의 요약과 이 spec 링크.
   10. 보관 문서 링크: `docs/archive/SPEC-v1.2.md`, `docs/archive/SPEC-v5.0.md`.
3. `AGENTS.md` "Project Boundary"(`AGENTS.md:3-7@28f1c96`)를 다음 뜻으로 고친다(영어 유지). Vault Graph는 Vault 위의 로컬 검색·회상 계층이고, 색인은 다시 만들 수 있는 파생 데이터이며 지식 원본이 아니다. Vault Graph는 Vault 파일을 직접 만들거나 고치거나 이름을 바꾸거나 지우지 않는다. Vault에 쓰는 유일한 길은 `remember`이고, 이것은 Vault 도구의 publish-draft를 실행해 그 검증을 거친다. `raw/`에는 쓰지 않는다.
4. `docs/TODO.md`
   - Operating Rules(`8-15행`)를 3번과 같은 원칙으로 고친다. "Vault mutation 금지"를 "Vault 쓰기는 remember → publish-draft만"으로, "read-only behavior 테스트"를 "remember 밖의 경로에서 Vault 무변경 테스트"로 바꾼다.
   - "Active Roadmap: Software Invariant Engine (SPEC v5.0)"(`17-42행`)을 "Active Roadmap: Local-Graph"로 바꾸고 1차 작업과 n차 항목을 체크리스트로 적는다. VS-1~6은 보관본 링크 한 줄로 줄인다.
   - 다른 항목(Deferred Product Candidates 등)은 바꾸지 않는다.
5. `docs/ARCHITECTURE.md` §4(`190-196행`)에 다음을 반영한다. Vault 문서는 vault-graph 프로세스가 직접 쓰지 않는다. remember는 Vault 도구의 publish-draft 하위 프로세스를 실행하는 명시적 쓰기 경로이며, 일반 조회·색인·watch는 이 경로를 쓰지 않는다. `vault-map.json`은 읽기만 한다.
6. VG-MOD(`docs/design/specs/2026-10-15-vault-graph-modular-architecture-ko.md`) INV-01·INV-04를 다시 정의한다(9절 질문3 답). 사용자 판단: vault-graph의 읽기 전용은 제품 차별점이 아니다. 새 규칙은 다음과 같다. INV-01: 코드 저장소 소스는 읽기만 한다. Vault 문서는 vault-graph 프로세스가 직접 만들거나 고치거나 지우지 않고, Vault에 쓰는 일은 Vault 도구의 검증 경로(1차는 publish-draft)를 실행해서만 한다. `raw/`에는 쓰지 않는다. 파생 투영은 다시 만들 수 있어야 한다. 증거: 조회·색인·watch 전후 원본 해시가 같고, 쓰기 경로 실행은 remember 같은 명시적 쓰기 도구에서만 일어난다. INV-04: 설정 기록과 Vault 쓰기는 명시적 명령·도구에서만 허용한다. "Vault 내용 기록은 허용하지 않는다" 문장은 지운다. INV-02도 다시 정의한다(9절 질문9 답). 정상 조회는 색인 재생성·모델 내려받기·파일 초기화·설정 기록을 실행하지 않는다. 예외는 사용 기록 하나다. 세션 시작 회상과 MCP 페이지 리소스 읽기는 이미 있는 Graph Home 아래 `usage/`에 JSON Lines를 덧붙여 쓸 수 있다. 덧붙이기만 하고 고치거나 지우지 않는다. 기록이 실패해도 조회는 그대로 성공한다. Graph Home이 없으면 만들지 않는다. 색인·설정 파일은 바꾸지 않는다. `usage/`를 지워도 검색 결과는 같고, 회상 묶음 구획B의 순서만 기본(최근성)으로 돌아간다. 증거: 조회 전후로 `usage/` 밖의 Graph Home 바이트가 같다.
7. `docs/DECISIONS.md`에는 spec 승인 후에만 결정4, 7, 8, 9, 10, 11을 Question/Decision/Reason/Implications 형식으로 추가한다. 결정11은 Vault·vault-builder가 소유한 정책이라고 적는다.
8. `README.md:5-13`은 remember를 머지하는 단계(4.2.4)에서 함께 고친다. 그 전까지는 README가 현재 동작과 맞다. `tests/test_readme_onboarding_contract.py`가 확인하는 문자열은 유지한다.

### 4.2 1차 작업

#### 순서와 선행 조건

| 단계 | 내용 | 선행 |
|---|---|---|
| 1차-0 | 4.1 문서 변경 | 없음 |
| 선행 | 모듈화 보완1(기능 간 가져오기 방향 테스트), 보완5(M12↔M17 binding 순환)는 1차-2 전에, 보완6은 1차-3 전에. 나머지 보완은 9절 질문2의 순서표대로 나란히 또는 1차 뒤 | 1차-0 |
| 1차-1 | 측정1 기준선(변경 전) | 1차-0 |
| 1차-2 | `vault-map.json` 읽기(결정9) | 보완1, 보완5 |
| 1차-3 | 세션 시작 회상(결정10, 변경3·변경6 중 1차 범위) | 1차-2 |
| 1차-4 | remember(결정8, 변경8) + README 수정 | 1차-2 |
| 1차-5 | 한국어 조사 처리(변경9) | 1차-1 |
| 1차-6 | 측정1 재측정, 결과 기록 | 1차-5 |

각 단계는 독립 커밋으로 끝내고, 단계마다 전체 테스트와 보완1 경계 테스트를 통과해야 한다.

#### 4.2.1 측정1 (문제7)

- 스크립트 `tests/benchmarks/measure_vault_search_parity.py`. 시그니처 `def main(questions: Path, vault: Path, graph_home: Path, out_dir: Path) -> None`.
- 질문 파일은 저장소 밖에 둔다. JSON Lines이고 한 줄은 `id`, `question`, `expected`(Vault 기준 상대 경로 목록, 정답 문서)를 가진다. 질문 20개는 사람이 실제 Vault 내용으로 만든다(brief §6).
- 질문마다 두 시스템을 하위 프로세스로 실행한다. Vault 검색은 Vault 루트에서 `python -I -B tools/wiki/cli.py search <질문> --limit 5`로 실행한다(Vault `tools/wiki/cli.py:69-73`). 출력은 JSON이 아니라 `render_hits`가 만든 텍스트이므로(`cli.py:196`) 스크립트가 결과 경로를 텍스트에서 읽는다. vault-graph는 vault-graph는 `vg search --graph-home <graph_home>`(기본 모드, 상위 5개, JSON 출력)로 실행한다. 두 쪽 모두 프로세스 시작을 포함한 실제 대기 시간을 잰다.
- 질문마다 3회 실행해 첫 실행 시간과 3회 중앙값을 기록한다.
- 적중: 상위 5개 결과의 문서 경로(청크는 그 청크의 문서 경로) 중 하나라도 `expected`에 있으면 그 질문은 적중이다. 적중률은 적중 질문 수 / 전체 질문 수다.
- 조건A: 현재 Vault 그대로. 조건B: 세션 원문이 쌓인 Vault. 수집기(의존2)가 아직 없으므로 1차에서는 사람이 Claude Code 대화를 손으로 Markdown으로 옮겨 넣은 임시 Vault 복사본으로 조건B를 잰다(9절 질문1 답). 복사본은 저장소와 실제 Vault 밖에 두고, 옮긴 세션 수와 형식을 보고서에 적는다. 수집기가 생기면 실제 수집 결과로 다시 잰다(n차-9).
- 출력: 질문별 결과 JSON은 `out_dir`(저장소 밖)에만 쓴다. 저장소에는 질문 내용 없이 합계(질문 수, 시스템별 적중률, 시간 중앙값, 조건, 커밋)만 담은 보고서를 `docs/design/reports/`에 커밋한다.
- 측정 전에 이 컴퓨터에 Graph Home을 만들고 실제 Vault를 등록·색인해야 한다(`vg setup`, `vg index`). 이 작업은 Graph Home에만 쓴다.

#### 4.2.2 `vault-map.json` 읽기 (결정9, 문제3)

- 새 읽기 모듈 `src/vault_graph/operation/integration/vault_map.py`. 공개 표면:
  - `def load_vault_map(path: Path) -> VaultMap`
  - `class VaultMap: def vaults_for(self, cwd: Path) -> tuple[MappedVault, ...]`
  - M12·M01이 쓰는 읽기 Protocol은 보완5의 binding 읽기 Protocol과 같은 자리에 둔다.
- 경로: 기본값은 `$HOME/.claude/vault-builder/vault-map.json`. CLI `--vault-map PATH`와 환경 변수 `VAULT_GRAPH_VAULT_MAP`으로 바꿀 수 있다. [가정]
- `version`이 2가 아니거나 형식이 깨졌으면 그 파일을 쓰지 않고 경고를 낸다. 파일을 고치거나 만들지 않는다.
- 파일 형식(version 2, 확인함): `vaults`는 이름 → `{path, role}`, `projects`는 프로젝트 id → `{root, vaults: [Vault 이름…], remote}`이다.
- 프로젝트 찾기: llm-wiki router의 규칙(`$HOME/.claude/vault-builder/llm_wiki_router.py` `find_project`, 204행부터)과 같게 한다. router 파일이 이 규칙의 소유자이고 vault-builder의 link 명령도 같은 규칙을 쓴다. 단계는 순서대로 (1) `cwd`가 속한 git 저장소의 main worktree 루트와 `root` 비교, (2) origin remote와 `remote` 비교(정규화 후), (3) 폴더 이름이다. 처음으로 하나만 맞는 단계에서 정하고, 한 단계에서 둘 이상 맞으면 정하지 않는다(넘김 또는 `error`). git 저장소 밖이면 정하지 않는다. worktree에서 실행해도 main worktree 루트로 같은 프로젝트를 찾는다. 프로젝트의 `vaults` 목록 전체를 연결 Vault로 돌려준다.
- 우선순위(1차): `vault-map.json`에 그 프로젝트가 있으면 그것을 쓴다. 없을 때만 기존 `project-bindings.json`을 쓴다. `project-bindings.json` 제거는 n차-7이다.
- Vault 등록: 조회는 Graph Home에 아무것도 쓰지 않는다(VG-MOD INV-02). `vault-map.json`의 Vault를 Graph Home에 등록하는 것은 명시적 명령에서만 한다. 지금 `vg setup`의 `--vault`는 필수 인자다(`src/vault_graph/interface/cli/main.py:359@28f1c96`). 1차에서 이를 선택 인자로 바꾸고, 생략하면 `vault-map.json`의 Vault 전체를 등록한다. `--vault`를 주면 지금과 같다. 필수 인자를 선택으로 푸는 추가 변경이라 기존 호출은 깨지지 않는다. [가정]
- `vg status`는 `vault-map.json`의 위치, 버전, 그리고 map에는 있으나 Graph Home에 등록되지 않은 Vault를 보여준다.
- Vault 일치 판정: map의 Vault 경로와 Graph Home에 등록된 Vault 경로를 실제 경로로 비교한다.

#### 4.2.3 세션 시작 회상 (결정10, 문제4)

설계 근거: `research/session-start-recall.md`(2026-10-30) 4절과 7절. 9절 질문6 답(옵션1 "고정 핵심 + 목록 + 변경 알림"), 질문9·10·11 답을 반영했다.

진입점과 조립

- CLI `vg hook session-start [--graph-home PATH] [--vault-map PATH] [--max-tokens N]`. 표준 입력으로 Claude Code SessionStart 훅 JSON(`cwd`, `session_id`, `source`)을 받는다.
- 조립 함수 `def recall(cwd: Path, *, source: str, session_id: str, max_tokens: int, max_chars: int) -> RecallBundle`을 `context/pack`(M08)에 둔다. 사용 기록 읽기·쓰기는 포트로 주입한다.
- 회상은 키워드·벡터 검색을 부르지 않고 임베딩 모델과 벡터 저장소를 열지 않는다. 세션 시작을 늦추지 않기 위해서다.
- 범위: 4.2.2로 `cwd`의 프로젝트와 연결된 Vault를 찾는다. 프로젝트 범위 밖 문서는 어느 구획에도 넣지 않는다.

출력 구획 (이 순서로 출력한다)

| 구획 | 형식 | 내용 | 예산 목표 |
|---|---|---|---|
| A 고정 핵심 | 전문, 항목당 1~3줄 | Vault frontmatter `pin: true` 문서. 유형은 `memory_kind` | 최대 400토큰 |
| B 기억 목록 | 한 줄 목록 | 열린 질문, 최근 결정, 최근 변경 | 나머지 |
| C 변경 알림 | 한 줄 목록 | 지난 주입 이후 대체·폐기된 항목 | 최대 150토큰 |
| D 가져오는 방법 | 고정 문장 한 줄 | 본문을 여는 MCP 리소스 | 약 50토큰 |

1. 구획A 고정 핵심. `pin`과 `memory_kind` 필드는 Vault에 아직 없다(의존5, 9절 질문10). 필드가 생기기 전까지 구획A는 비어 있고 제목도 출력하지 않는다. 남은 예산은 구획B로 간다. vault-graph는 본문을 보고 규칙인지 추측하지 않는다.
2. 구획B 기억 목록. 한 줄에 항목 하나이며 ID, 유형, 마지막 변경 날짜, 상태, 제목, Vault 기준 상대 경로, 본문 추정 토큰 수를 적는다. 줄 모양 예: `- [m:3f2a9c1d] decision · 2026-10-28 · stated · 제목 (wiki/decisions/x.md, ~180t)`.
   - ID는 `m:`과 Vault ID·상대 경로로 만든 짧은 해시다. 같은 문서는 늘 같은 ID를 갖고, 사용 기록의 `injected`와 `fetched`를 잇는 데 쓴다.
   - 유형은 `memory_kind`가 생기기 전까지 frontmatter `type`을 쓴다.
   - Vault가 둘 이상이면 경로 앞에 Vault 이름을 붙인다.
   - `stale`·`deprecated`·`superseded` 문서는 넣지 않는다(`src/vault_graph/context/memory/project_memory.py:39` `STALE_STATUSES` 재사용). `inferred`는 "추정", `contested`는 "논쟁 중" 표시를 붙여 넣는다. claim 단위 제외는 n차-1이다.
   - 순서: 마지막 변경 날짜 내림차순. 지난 주입 뒤 바뀐 항목은 위로 올린다. 최근 10회 주입되고 한 번도 열리지 않은 항목은 한 단계 내린다(9절 질문9). 내리기만 하고 빼지 않는다. 유형별 상한은 열린 질문 8, 결정 10, 최근 변경 8이다. [가정: 시작값, 측정으로 조정]
3. 구획C 변경 알림. 이 프로젝트에 지난번 주입했던 항목(사용 기록의 `injected`) 중 그 뒤 상태가 `superseded`·`deprecated`가 된 것을 "옛 제목 → 새 제목 (날짜)" 한 줄로 보인다. 새 문서는 Vault frontmatter `superseded_by`로, 반대 방향은 `supersedes`로 찾는다(Vault `tools/wiki/lib/lint.py:46`에 두 필드가 있음). `superseded_by`가 없으면 "옛 제목 → 폐기됨 (날짜)"로 적는다. 사용 기록이 없거나 읽지 못하면 "최근 14일 안에 대체·폐기된 항목"으로 대신한다.
4. 구획D 가져오는 방법. "본문은 MCP 리소스 `vault://{vault_id}/pages/{path}`로 연다" 한 줄이다. 이 리소스는 이미 있다(`src/vault_graph/interface/mcp/mcp_resources.py:262`). 새 MCP 도구를 만들지 않는다.

예산

- 기본 1,500토큰과 9,000자 두 한도를 함께 둔다. 먼저 닿는 한도에서 멈춘다. 9,000자는 Claude Code 훅 출력 한도(문자열당 10,000자, 넘으면 앞 2,000자만 보임)보다 작게 잡은 값이다.
- 한도를 넘으면 구획B의 뒤쪽 줄부터 줄이고 끝에 "N개 생략" 한 줄을 적는다. 구획A·C·D는 각 예산 목표 안에서 먼저 확보한다.
- `--max-tokens`로 토큰 한도만 바꿀 수 있다. 글자 한도는 바꾸지 않는다.
- 토큰 수는 context pack이 쓰는 기존 추정 함수로 센다.

`source`별 동작 (9절 질문11)

| `source` | 동작 |
|---|---|
| `startup`, `clear`, `compact` | 구획 A~D 전체를 출력한다. |
| `resume`, `fork` | 구획C만 출력한다. 알릴 변경이 없으면 표준 출력을 비우고 종료 코드 0으로 끝난다(처리함, 더할 것 없음). |
| 그 밖의 값이나 값 없음 | `startup`과 같이 다룬다. |

종료 코드

- 0: 처리했다. 표준 출력은 회상 묶음이거나 비어 있다(`resume`에서 변경 없음).
- 3: 회상할 수 없다(넘김). 프로젝트를 찾지 못함, Vault 미등록·색인 없음, Graph Home 없음, `startup` 계열에서 구획 A·B·C가 모두 비어 있음. 표준 출력은 비우고 이유 한 줄을 표준 오류에 쓴다. 훅은 `recall.sh`를 쓴다.
- 그 밖의 0이 아닌 값: 예상하지 못한 예외. 표준 출력은 비어 있다. 훅은 3과 똑같이 `recall.sh`를 쓴다.

사용 기록 (9절 질문9)

- 위치: Graph Home 아래 `usage/`의 JSON Lines 파일. 덧붙이기만 한다. Graph Home이 있을 때만 쓰고, `usage/` 디렉터리가 없으면 그것만 만든다.
- 사건: `injected`(세션 시작 회상이 낸 항목 ID, 구획, `session_id`, 프로젝트, 시각), `fetched`(MCP 리소스 `vault://{vault_id}/pages/{path}` 읽기가 성공했을 때의 항목 ID, `session_id`가 있으면 그것, 시각).
- "쓰임"의 정의: 같은 `session_id`에서 `injected` 뒤 `fetched`가 있으면 쓰인 것으로 본다. 리소스 읽기에서 `session_id`를 알 수 없으면 시각으로만 기록하고, 순서 조정은 "주입 수 대비 열린 수"로 계산한다.
- 기록이 실패해도(디스크 가득 참, 권한 없음 등) 회상과 리소스 읽기는 그대로 성공한다. 실패는 표준 오류에 경고 한 줄로만 알린다.
- 사용 기록의 쓰임: 구획B 순서 조정과 구획C 대상 찾기 두 가지뿐이다. 정리 후보를 보여 주는 `vg memory review`는 n차-10이다.

경계

- Vault 파일, 색인, 설정 파일은 쓰지 않는다. Graph Home에서 쓰는 곳은 `usage/` 하나다(VG-MOD INV-02 재정의, 4.1절 6번).
- 훅 스크립트 쪽 분기는 종료 코드만 본다. 0이면 표준 출력을 그대로 쓰고, 0이 아니면 `recall.sh`를 쓴다. 이 부분은 vault-builder 몫이다(의존1).

#### 4.2.4 remember (결정8, 문제5)

- MCP 도구 `remember(title: str, kind: str, body: str, evidence: list[str], cwd: str | None = None, vault: str | None = None) -> RememberResult`. `interface/mcp/mcp_tools.py`에 등록한다. MCP 도구는 12개가 된다.
- 서비스 `src/vault_graph/operation/integration/remember_service.py`. 다음 포트를 주입받는다.
  - `VaultMap` 읽기(4.2.2)
  - `class VaultPublisher(Protocol): def publish_draft(self, vault_root: Path, draft_path: Path, *, timeout_s: float) -> PublishOutcome`
- 하위 프로세스 구현은 `src/vault_graph/interface/composition/adapters/vault_publish_cli.py`에 둔다. Vault 루트를 작업 디렉터리로 하여 `<vault-graph의 Python> -I -B tools/wiki/cli.py publish-draft <draft_path>`를 실행한다. llm-wiki router가 Vault CLI를 부르는 방식과 같다(`llm_wiki_router.py:839-845`, 시간 제한 `CLI_TIMEOUT_SECONDS = 120`). publish-draft의 인자는 draft 경로 하나와 선택 `--report`다(Vault `tools/wiki/cli.py:96-98`). `--report`는 Vault `scratch/reports/`에 보고서를 쓰므로 remember는 이 옵션을 주지 않는다. 다만 publish-draft는 성공 시 `--report` 없이도 Vault 도구 스스로 `scratch/reports/<날짜>-lint.md`를 쓰고 탐색 지도(maps)를 다시 만든다(Vault `cli.py` `_write_lint_report`, `_rebuild_maps_after_publish`). 이 기록은 Vault 도구의 검증 경로 안의 동작이다. 같은 경로의 페이지가 이미 있으면 remember는 publish-draft를 부르지 않고 `rejected`를 돌려준다(사람이 쓴 페이지를 덮어쓰지 않기 위해, 작업12에서 추가).
- 입력 확인: `title`, `body`가 비어 있지 않고, `evidence`가 하나 이상이며, `kind`가 허용 목록(1차: `decision`, `system`)에 있어야 한다. [가정]
- draft 조립: vault-graph가 에이전트가 넘긴 필드만으로 결정적으로 만든다. 날짜는 실행 시각, 형식은 Vault 도구의 draft 형식을 따른다. 내용을 바꾸거나 요약하지 않는다(결정7).
- draft 위치: Vault와 Graph Home 밖의 운영체제 임시 디렉터리에 만들고, 실행이 끝나면 성공·실패와 관계없이 지운다. [가정]
- 대상 Vault: `vault` 인자가 있으면 `vault-map.json`의 이름으로 찾는다. 없으면 `cwd`의 프로젝트에 연결된 Vault가 정확히 하나일 때만 그것을 쓴다. 그 밖의 경우는 기록하지 않고 오류를 돌려준다. 추측하지 않는다.
- 같은 프로세스 안에서는 같은 Vault에 대한 remember를 한 번에 하나만 실행한다.
- 시간 제한: 120초(router와 같음).
- 응답 `RememberResult`: `status`(`published`, `rejected`, `error`), `vault`, `written_paths`, `messages`(publish-draft 출력 요약). 기록된 내용은 다음 색인 이후에 검색된다고 `messages`에 적는다. remember는 색인을 실행하지 않는다.
- 1차의 remember는 사용자가 기억하라고 직접 말한 내용(stated)만 다룬다. 추론한 사실을 검토 대기열로 보내는 경로는 만들지 않는다. [가정]
- 다른 MCP 도구 11개와 일반 조회·색인·watch는 publish-draft를 실행하지 않는다.

#### 4.2.5 한국어 조사 처리 (변경9, 문제6)

방식: 색인할 때 조사를 떼어 별도 열에 저장한다(9절 질문5 답, 옵션3).

- 대상: `src/vault_graph/storage/local/sqlite_keyword_index.py`의 FTS5 테이블 정의(`44-47행`), 문서 기록 경로, `_match_query`·`_query_tokens`(`252-260행`). 새 순수 함수 `def strip_korean_particle(token: str) -> str`를 색인과 질의 양쪽이 같이 쓴다.
- 규칙: 한글이 들어간 토큰은 끝에 붙은 조사 하나를 긴 것부터 떼어 낸다. 남은 어간이 2글자 이상일 때만 떼고, 1글자 이하면 원래 토큰을 쓴다. 한글이 없는 토큰은 그대로 둔다. 조사 목록은 Vault 검색(`search.py:116`)의 목록과 같게 한다.
- 색인: FTS5 테이블에 조사를 뗀 본문 열(예: `body_stem`)을 추가한다. 조각을 기록할 때 기존 본문 열과 함께 이 열을 채운다. 기존 본문 열과 토크나이저(`unicode61`)는 그대로 둔다.
- 질의: 한글 토큰이 있으면 질의 토큰에도 같은 함수를 적용해 `body_stem` 열에서 찾는다. 한글이 없는 질의는 지금처럼 기존 열에서만 찾아 결과가 바뀌지 않게 한다. 접두 검색(`*`)은 쓰지 않으므로 "결정론" 같은 다른 단어는 맞지 않는다.
- 스키마 변경: 테이블 정의가 바뀌므로 색인 세대(투영 형식) 버전을 올린다. 기존 Graph Home은 `vg index --full`로 다시 색인해야 한다. 다시 색인하기 전에는 `vg status`가 "키워드 색인 형식이 오래됨, `vg index --full` 필요"를 경고하고, 검색은 기존 열로만 동작한다(INV-02에 따라 조회가 자동 재색인하지 않는다).
- 이 변경은 한글 질의의 키워드 점수와 순서를 바꾼다. VG-MOD INV-05(점수·순서 유지)의 예외로 DECISIONS에 기록하고, 측정1 적중률이 기준선보다 낮아지지 않는 것을 조건으로 한다. 한글이 없는 질의의 결과는 바뀌지 않는다.
- 코드 투영 FTS(`sqlite_code_projection_store.py:135`)는 바꾸지 않는다.

### 4.3 n차 로드맵 (1차 이후)

| 코드 | 내용 | 설계 연결 | 선행 |
|---|---|---|---|
| n차-1 | 대체된 claim을 기본 결과와 회상에서 빼고, 최근 기억에 가중치를 준다. Vault의 `supersede-claim` 결과를 읽는다(발견18) | 변경2 | 의존4, 의존5 |
| n차-2 | 기억 frontmatter(`peer`, `kind`, `observed_at`, claim 상태)를 해석하고, 프로필 조회 `get_profile`을 추가한다. 모르는 스키마 버전은 경고한다 | 변경1, 위험3 | 의존5 |
| n차-3 | 코드와 기억을 질의 하나로 찾는다. MCP `explain_symbol`이 M11 코드 사실에 결정과 에피소드를 붙인다. 코드 청크를 검색 색인에 넣을지도 여기서 정한다 | 변경4, 기능7 | 1차 완료 |
| n차-4 | 임베딩 모델 교체를 측정1과 같은 방법(한국어 대화 질문)으로 비교한 뒤 정한다 | 변경7 | 측정1 |
| n차-5 | 폴링 watch를 파일 변경 이벤트(`watchfiles`) 기반으로 바꾼다 | 변경5 | 없음 |
| n차-6 | `raw/sessions/<agent>/`를 수집 대상별(Claude Code, Codex, ChatGPT)로 역할 분류하고 evidence 모드에서 찾는다 | 기능1, 기능6 | 의존2 |
| n차-7 | `project-bindings.json`과 자체 Vault 등록을 `vault-map.json` 읽기로 대체하고 정리한다(결정9 완결) | 발견23 | 1차-2 |
| n차-8 | MCP `recall` 도구와 질문 기반 회상(`prompt` 사용) | 변경3 | 1차-3 |
| n차-9 | 측정1 조건B를 실제 수집기 결과로 다시 측정 | 방향2 | 의존2 |
| n차-10 | `vg memory review`(읽기 전용): 사용 기록으로 고정 후보, 정리 후보, 모순 후보를 보인다. 고정·상태 변경은 사람이 Vault 검증 경로로 한다 | research 4.2 | 1차-3, 사용 기록 2주 운영 |
| n차-11 | 첫 사용자 프롬프트로 검색해 본문 상위 몇 개를 넣는 회상(UserPromptSubmit 훅) | research 옵션3 | 측정1, 의존1 확장 |
| n차-12 | `raw/sessions/` 대화 기록에서 `m:` ID 언급을 세어 사용 집계를 보강 | research 4.2 | 의존2 |

순서는 설계 페이지 단계3(n차-1·2), 단계4(n차-3), 단계5(n차-4·5·6)를 따른다. n차-7~12는 선행 조건이 갖춰지는 대로 한다. 각 항목은 시작 전에 별도 spec으로 승격한다.

### 4.4 Vault·vault-builder 쪽 의존성 (미구현 표시)

| 코드 | 의존 | 소유 | 상태 | vault-graph에 미치는 영향 |
|---|---|---|---|---|
| 의존1 | SessionStart 훅 스크립트 분기. vg가 있으면 `vg hook session-start`에 훅 입력을 그대로 넘기고, 종료 코드 0이면 표준 출력을 그대로 쓴다(비어 있어도 그대로). 0이 아니면 `recall.sh`를 쓴다. `source`는 vg가 읽으므로 훅이 보지 않는다 | vault-builder(사용자 범위 훅) | 미구현 | 1차-3 결과가 실제 세션에 들어가려면 필요하다 |
| 의존2 | 세션 수집기와 `raw/sessions/`(결정5) | Vault 도구, vault-builder 템플릿 배포 | 미구현 | 측정1 조건B, 가치1, n차-6 |
| 의존3 | Vault `AGENTS.md` 규칙1 예외: 수집기가 `raw/sessions/`에 새 파일을 추가하는 것만 허용(결정11) | Vault, vault-builder | 미구현. 요청1로 전달 | 의존2의 전제 |
| 의존4 | 정리 스킬, 자동 기억 확정 규칙(결정6) | Vault 도구 | 미구현 | n차-1 |
| 의존5 | 기억 frontmatter 스키마 `vault-memory/v1`. 고정 표시 `pin: true`와 기억 유형 `memory_kind: rule\|correction\|decision\|preference`를 포함해 달라고 요청한다(9절 질문10). `supersedes`·`superseded_by`는 이미 있다(Vault `tools/wiki/lib/lint.py:46`) | vault-builder가 Vault 도구에 담아 배포 | 미구현 | 구획A(필드 전까지 비어 있음), 구획B 유형, n차-1, n차-2 |
| 의존6 | publish-draft 명령과 draft 형식의 버전 표시 | Vault 도구 | 명령은 있음, 버전 표시 없음 | 4.2.4 |
| 의존7 | `vault-map.json` version 2 형식 유지 | vault-builder | 있음 | 4.2.2 |

vault-builder 요청 문서: vault-builder 저장소 `docs/superpowers/specs/2026-10-29-vault-graph-requests-ko.md`(커밋 전). 요청1(규칙1 예외)=의존3, 요청2(수집 도구)=의존2, 요청3(훅 연결)=의존1, 요청4(publish-draft 호출 계약)=의존6, 요청5(`vault-map.json` 계약)=의존7, 요청6(스키마 버전)=의존5, 요청7(확정 규칙)=의존4. 새 `docs/SPEC.md` 단계 표에도 이 경로를 적는다.

## 5. Decisions

표기: [사용자] 사람이 대화에서 정한 것(spec gate에서 최종 확인), [가정] 작성자가 정한 것. 결정 번호는 설계 페이지 번호를 그대로 쓰고, 이 spec에서 새로 정한 것은 S로 시작한다.

1. 결정4 [사용자] 옵션1. v5.0을 `docs/archive/SPEC-v5.0.md`로 옮기고 Local-Graph를 유일한 활성 SPEC으로 한다. 이유: 코드와 README가 이미 검색 계층이고, v5.0 작업은 하나도 구현되지 않았으며 목표4가 가치3과 충돌한다.
2. 결정7 [사용자, 2026-10-30 확정] vault-graph는 LLM을 부르지 않는다. 이유: Local 원칙(키·비용 없음)과 결과 재현성. remember의 draft도 이 때문에 에이전트가 넘긴 필드로만 만든다.
3. 결정8 [사용자] vault-graph MCP에 remember를 두고 실제 기록은 Vault 도구의 publish-draft에 맡긴다. 원칙은 "읽기 전용"에서 "Vault에 쓰는 일은 Vault 도구의 검증을 거친다"로 바뀐다. 이유: 에이전트는 MCP 하나만 알면 되고, 기록은 llm-wiki MCP와 같은 검증을 거친다. 검토자 한 명의 제거 권고(발견25)는 사람이 받아들이지 않았다.
4. 결정9 [사용자] `vault-map.json`이 연결 정보의 유일한 원본이고 vault-graph는 읽기만 한다. 이유: 연결 정보를 두 벌로 관리하지 않는다.
5. 결정10 [사용자] SessionStart 훅은 vault-graph가 있으면 vault-graph 회상을, 없으면 `recall.sh`를 쓴다. 이유: 에이전트가 기억을 체감하는 첫 지점이고, Vault는 vault-graph 없이도 동작해야 한다.
6. 결정11 [사용자] Vault 규칙1에 `raw/sessions/` 새 파일 추가만 허용하는 예외를 둔다. vault-builder에 요청 문서로 알린다. 이유: 수집기는 publish-draft를 거칠 수 없다(발견20). vault-graph 쪽 작업은 없다.
7. 측정 [사용자] 같은 질문 20개로 시간과 상위 5개 적중을 비교하고 `raw/sessions/`가 있는 경우도 잰다. 성공 기준은 `vg search` 상위 5개 적중률이 Vault 검색보다 높은 것이다.
8. S1 [가정] 1차에서 기존 공개 동작을 지우거나 바꾸지 않고 추가만 한다. 예외는 셋이다. (1) S7: 한글 질의의 키워드 점수와 순서, 키워드 색인 형식 변경과 한 번의 전체 다시 색인. (2) S11: 세션 시작 회상과 MCP 페이지 리소스 읽기가 Graph Home `usage/`에 덧붙여 기록한다. 응답 내용은 바뀌지 않는다. (3) S10: remember의 Vault 쓰기. 이유: brief §6, VG-MOD INV-05.
9. S2 [가정] 1차에서는 `vault-map.json`에 프로젝트가 없을 때 `project-bindings.json`을 쓴다. 제거는 n차-7이다. 이유: 결정9를 따르면서도 기존 사용자의 연결이 갑자기 끊기지 않게 한다.
10. S3 [사용자, 2026-10-30, 질문6 옵션1] 세션 시작 회상은 질문 없이 프로젝트 범위에서 "고정 핵심 + 기억 목록 + 변경 알림 + 가져오는 방법" 네 구획을 1,500토큰과 9,000자 안에 담고, 검색과 임베딩 모델을 쓰지 않는다. 본문은 에이전트가 기존 MCP 리소스로 연다. 이유: 시장 제품의 표준이 "작은 고정 핵심 + 목록"이고, 한 줄 목록이면 같은 예산에 항목을 훨씬 많이 보일 수 있다. 9,000자는 Claude Code 훅 출력 한도 때문이다(`research/session-start-recall.md` 발견1·3·5).
11. S4 [사용자, 2026-10-30, 질문11] 회상 묶음은 표준 출력에 Markdown으로 낸다. 종료 코드 0은 "처리함"(출력이 비어 있을 수 있음), 3은 "회상할 수 없음"이다. 훅은 종료 코드만 보고 분기한다. 이유: `resume`에서 더할 것이 없는 경우와 회상할 수 없는 경우를 구분해야 `recall.sh`가 중복 주입되지 않는다.
12. S5 [사용자, 2026-10-30] remember 세부. draft는 임시 디렉터리에 만들고 지우며, 대상 Vault는 명시 인자 또는 연결된 Vault가 하나일 때만 정하고, publish-draft가 실패하면 그 이유를 돌려줄 뿐 다른 쓰기 경로로 옮기지 않는다. 이유: 발견25의 세 가지 미정 사항을 "추측하지 않고, Vault 안에 vault-graph 파일을 남기지 않는다"는 원칙으로 정한다. 9절 질문4에서 확인한다.
13. S6 [가정] 1차 remember는 stated만 다루고 `kind`는 `decision`, `system`만 받는다. 이유: 검토 대기열 경로는 결정6(정리 규칙)과 함께 정해야 하고, 설계 페이지 기능3의 기록 대상이 `wiki/decisions`, `wiki/systems`다.
14. S7 [사용자, 2026-10-30] 한국어 조사는 색인할 때 떼어 별도 열에 저장하고, 한글 질의도 같은 규칙으로 떼어 그 열에서 찾는다(옵션3). 스키마가 바뀌므로 한 번 전체 다시 색인한다. 아래는 원래 추천(옵션1)의 근거로, 기록으로만 남긴다. 원래 추천: 한국어 조사는 질의 쪽에서 떼고 FTS5 접두 검색으로 찾는다. trigram 토크나이저는 쓰지 않는다. 이유: 테이블과 색인을 바꾸지 않아 다시 색인할 필요가 없고, Vault 검색과 같은 조사 목록을 써서 비교가 공정하다. 9절 질문5에서 확인한다.
15. S8 [가정] 측정1은 두 시스템을 모두 하위 프로세스로 실행해 사용자가 체감하는 시간을 잰다. 질문과 질문별 결과는 저장소 밖에 두고, 합계만 커밋한다. 이유: 개인 메모 내용을 저장소에 넣지 않는다.
16. S9 [사용자] 모듈화 보완1~9를 모두 한다. 보완1·보완5는 1차-2 전에, 보완6은 1차-3 전에 하고, 나머지는 우선순위와 난이도 순서(9절 질문2 표)로 1차와 나란히 또는 1차 뒤에 한다. 이유: 새 모듈이 기능 간 방향 규칙을 지키는지 검사가 먼저 있어야 하고, 1차-2가 보완5가 고치는 binding 경계를 직접 건드린다.
17. S10 [사용자, 2026-10-30] VG-MOD INV-01·INV-04를 "읽기 전용"에서 "Vault 쓰기는 Vault 도구의 검증 경로로만, 직접 파일 쓰기와 `raw/` 쓰기는 하지 않음"으로 다시 정의한다(4.1절 6번). 이유: 사용자는 읽기 전용이 제품 가치에 영향이 없다고 보고, 프로젝트 규칙을 다시 정해 쓰기를 허용하기로 했다.
18. S11 [사용자, 2026-10-30, 질문9] 세션 시작 회상과 MCP 페이지 리소스 읽기는 Graph Home `usage/`에 사용 기록을 덧붙여 쓴다. 기록 실패는 회상을 막지 않는다. VG-MOD INV-02를 이에 맞게 다시 정의한다(4.1절 6번). 1차에서 사용 기록은 구획B의 작은 순서 조정과 구획C에만 쓴다. `vg memory review`는 n차-10이다. 이유: 어떤 기억이 들어가고 실제로 열렸는지 알아야 예산과 선택 기준을 측정으로 고칠 수 있다. 1차는 최소로 둔다.
19. S12 [사용자, 2026-10-30, 질문10] Vault에 `pin`, `memory_kind` frontmatter 필드를 요청한다(의존5). 필드가 생기기 전까지 구획A는 비어 있고, 유형은 frontmatter `type`을 쓴다. 이유: 무엇을 늘 넣을지는 사람이 정해야 하고, vault-graph는 LLM 없이 내용으로 규칙을 추측하지 않는다.
20. S13 [사용자, 2026-10-30, 질문11] vg가 SessionStart `source`를 읽는다. `resume`·`fork`에서는 구획C만 내고, 알릴 변경이 없으면 빈 출력과 종료 코드 0으로 끝낸다. 이유: 이전 주입이 대화 기록에 남아 있어 다시 넣으면 중복이고, 훅이 `source`를 몰라도 되게 한다.

## 6. Failure and boundary behavior

| 상황 | 기대 동작 |
|---|---|
| `vault-map.json`이 없음 | 경고 없이 기존 `project-bindings.json`과 자체 등록을 쓴다. `vg status`가 "vault-map 없음"을 보여준다. |
| `vault-map.json`의 `version`이 2가 아니거나 JSON이 깨짐 | 그 파일을 쓰지 않고 경고를 낸다. 파일을 고치지 않는다. 세션 시작 회상은 프로젝트를 찾지 못하면 넘김(종료 코드 3)으로 끝난다. |
| `cwd`가 `vault-map.json`과 `project-bindings.json` 어디에도 없음 | 세션 시작 회상은 넘김. remember는 `vault` 인자가 없으면 `error`와 "대상 Vault를 정할 수 없음"을 돌려주고 아무것도 실행하지 않는다. |
| map의 Vault가 Graph Home에 등록되지 않았거나 색인이 없음 | 세션 시작 회상은 넘김. 표준 오류에 `vg setup` 또는 `vg index` 안내를 쓴다. 색인을 자동으로 실행하지 않는다. |
| Graph Home이 없음 | 세션 시작 회상은 넘김. Graph Home을 만들지 않는다. |
| `startup`·`clear`·`compact`에서 구획 A·B·C가 모두 비어 있음 | 넘김(종료 코드 3). 구획D 한 줄만 있는 회상 묶음은 내보내지 않는다. 훅이 `recall.sh`를 쓴다. |
| `resume`·`fork`이고 지난 주입 이후 대체·폐기된 항목이 없음 | 표준 출력을 비우고 종료 코드 0으로 끝난다. 훅은 아무것도 넣지 않고 `recall.sh`도 쓰지 않는다. |
| `resume`·`fork`이고 알릴 변경이 있음 | 구획C만 출력하고 종료 코드 0. 구획 A·B·D는 내지 않는다. |
| `source`가 없거나 모르는 값 | `startup`과 같이 다룬다. |
| Vault 문서에 `pin`·`memory_kind` 필드가 없음(의존5 전) | 구획A를 출력하지 않는다(제목도 없음). 남은 예산은 구획B로 간다. 유형은 frontmatter `type`을 쓰고, `type`도 없으면 "기타"로 적는다. |
| 항목이 1,500토큰 또는 9,000자를 넘음 | 먼저 닿는 한도에서 멈춘다. 구획B의 뒤쪽 줄부터 줄이고 "N개 생략" 한 줄을 적는다. 출력 전체가 두 한도를 넘지 않는다. |
| 구획A 고정 문서 하나가 400토큰을 넘음 | 앞부분을 잘라 넣고 "(일부, 전문은 리소스로)"를 붙인다. [가정] |
| 지난번 주입 항목이 `superseded`가 되었고 `superseded_by`가 있음 | 구획C에 "옛 제목 → 새 제목 (날짜)". 새 문서가 프로젝트 범위 밖이면 새 제목 대신 경로를 적는다. |
| 지난번 주입 항목이 `deprecated`이거나 `superseded_by`가 없음 | 구획C에 "옛 제목 → 폐기됨 (날짜)". |
| 사용 기록이 없음(첫 실행, `usage/` 삭제) 또는 읽기 실패 | 구획C는 "최근 14일 안에 대체·폐기된 항목"으로 만들고, 구획B는 최근성 순서만 쓴다. 회상은 성공한다. |
| 사용 기록 쓰기 실패(권한, 디스크 가득 참) | 회상 묶음과 종료 코드는 그대로다. 표준 오류에 경고 한 줄을 쓴다. 리소스 읽기도 그대로 성공한다. |
| Graph Home은 있으나 `usage/`가 없음 | `usage/`만 만들고 기록한다. Graph Home의 다른 파일은 만들거나 바꾸지 않는다. |
| 같은 문서를 여러 세션이 동시에 기록 | 줄 단위 덧붙이기만 하며 순서는 보장하지 않는다. 깨진 줄은 읽을 때 건너뛴다. |
| 세션 시작 회상 중 예상하지 못한 예외 | 표준 출력은 비우고 0이 아니고 3도 아닌 코드로 끝난다. 훅은 `recall.sh`로 넘어간다. |
| 프로젝트가 여러 Vault에 연결됨 | 세션 시작 회상은 모든 연결 Vault에서 모아 같은 예산 안에 담는다. 구획B 경로 앞에 Vault 이름을 붙인다. remember는 `vault` 인자가 없으면 `error`로 끝난다. |
| remember 입력이 비었거나 `kind`가 허용 목록 밖이거나 `evidence`가 없음 | publish-draft를 실행하지 않고 `rejected`와 이유를 돌려준다. |
| publish-draft가 검증·lint 실패로 0이 아닌 코드로 끝남 | `rejected`, `written_paths` 비어 있음, publish-draft 출력 요약을 돌려준다. 되돌리기는 publish-draft가 한다. vault-graph는 재시도하거나 다른 쓰기 경로(검토 대기열 등)로 옮기지 않는다. |
| 기록 전부터 Vault 전체 lint가 깨져 있음 | publish-draft가 실패한다. remember는 `rejected`와 "Vault lint가 기록 전부터 실패함" 안내를 돌려준다. 사람이 Vault를 먼저 고쳐야 한다. |
| publish-draft가 120초 안에 끝나지 않음 | 하위 프로세스를 종료하고 `error`와 "결과를 확인할 수 없음, Vault의 git 상태를 확인할 것"을 돌려준다. |
| Vault에 `tools/wiki/cli.py`가 없음(Vault 도구가 설치되지 않은 Vault) | `error`와 "이 Vault에는 publish-draft가 없음"을 돌려준다. |
| draft 형식 버전을 Vault 도구가 받아들이지 않음(의존6) | publish-draft 실패로 처리한다(`rejected`). 버전 표시가 생기면 실행 전에 확인한다. |
| 서로 다른 MCP 프로세스가 같은 Vault에 동시에 remember | 같은 프로세스 안에서는 순서대로 실행한다. 프로세스 사이 동시 실행은 막지 않는다. 충돌 처리는 publish-draft의 되돌리기에 맡긴다. |
| remember 내용에 비밀값이 섞임 | vault-graph는 검사하지 않는다. 에이전트가 넘긴 그대로 publish-draft에 전달한다. 7절 위험 참고. |
| remember 성공 직후 같은 내용을 검색 | 다음 색인 전까지는 검색되지 않는다. `messages`에 이 사실을 적는다. |
| 한글 질의 "결정을" | 질의 토큰에서 조사를 떼어 "결정"으로 `body_stem` 열에서 찾는다. 본문의 "결정", "결정을", "결정은"이 맞고 "결정론"은 맞지 않는다. |
| 한글 질의 "책을"(어간 1글자) | 조사를 떼지 않고 "책을" 그대로 찾는다. 색인 쪽도 같은 규칙이라 본문의 "책을"이 맞는다. |
| 옛 형식 키워드 색인(`body_stem` 열 없음)에서 한글 질의 | 기존 열로만 찾고, `vg status`가 `vg index --full` 필요 경고를 낸다. 자동으로 다시 색인하지 않는다. |
| 한글이 없는 질의 | 1차 전후의 키워드 결과가 같다. |
| 측정1 질문 파일이 20개가 아님 | 측정은 진행하되 보고서에 질문 수를 적는다. 성공 기준 판정(A-19)에는 20개 실행만 쓴다. |
| 측정1에서 Vault 검색 CLI 실행이 실패 | 그 질문을 Vault 검색 미적중으로 세지 않고 "실행 실패"로 따로 센다. 실패가 하나라도 있으면 성공 기준 판정을 보류한다. |
| `docs/SPEC.md` 교체 후 과거 문서의 `docs/SPEC.md` 링크 | 링크는 새 SPEC을 가리킨다. 과거 문서(`docs/superpowers/**` 등)는 고치지 않는다. |

## 7. What could be wrong

1. Vault·vault-builder 쪽 사실은 처음에 brief §4에 기댔다. 2~6번은 spec 초안 뒤 메인 세션이 직접 확인했다. 다른 저장소이므로 구현 시점에 다시 확인해야 한다.
2. 확인함: `vault-map.json` version 2는 `vaults: {이름: {path, role}}`, `projects: {id: {root, vaults: [이름…], remote}}`이다. 프로젝트 찾기 규칙은 router가 소유한다(4.2.2). vault-graph가 같은 규칙을 따로 구현하므로 router 규칙이 바뀌면 어긋날 수 있다. 1차-2 테스트는 router와 같은 경우(root·remote·이름 단계, 같은 단계의 다중 일치, worktree)를 fixture로 둔다. fixture는 경로를 가린 구조만 남긴다.
3. 일부 확인: publish-draft 명령행은 `tools/wiki/cli.py publish-draft <path> [--report]`이고 router와 같은 방식으로 실행한다(4.2.4). draft JSON의 필수 필드와 성공 시 기록 경로 출력 형식은 아직 읽지 않았다. 1차-4 시작 전에 Vault `tools/wiki/lib/draft.py`를 읽어 draft 조립과 응답 해석을 정한다(요청4로 계약 고정을 요청함).
4. 확인함: Vault 검색은 `tools/wiki/cli.py search <query> --limit N`이고 텍스트로 출력한다(4.2.1). 출력 형식이 바뀌면 측정 스크립트의 해석이 깨진다.
5. 확인함: `recall.sh`는 표준 출력에 일반 텍스트를 쓴다(vault-builder `assets/project-memory/scripts/recall.sh:337,347`). S4와 같은 방식이다.
6. 확인함: `vg setup`의 `--vault`는 지금 필수다(4.2.2). 선택으로 푸는 것은 추가 변경이다.
7. M10이 제공하는 "최근 결정", "최근 변경"이 회상에 쓸 만큼 날짜와 제목을 갖고 있는지, 세 섹션 조립이 기존 서비스 호출만으로 되는지 확인하지 않았다. 새 조회가 필요하면 M10 변경이 1차-3에 더해진다.
8. 세션 시작 회상이 임베딩 모델 없이 몇 초 안에 끝나는지 재지 않았다. 2초 목표(A-10h)는 가정이다. 메타데이터 SQLite를 여는 시간과 Vault 크기에 따라 달라진다.
9. 조사 목록을 Vault `search.py:116`과 같게 하려면 그 목록을 vault-graph 코드에 복사해야 한다. 두 저장소의 목록이 나중에 달라질 수 있다.
10. 색인 때 조사를 떼는 방식은 규칙 기반이라 조사가 아닌 끝 글자(예: 명사 끝의 "이", "과")를 잘못 뗄 수 있다. 별도 열 추가로 키워드 색인 크기가 늘고, 전체 다시 색인 시간이 든다. 둘 다 재지 않았다. 측정1 재측정(1차-6)과 색인 크기 비교로 확인한다.
11. 모듈화 보완 계획은 사용자 검토 전 초안이다(`docs/design/plans/2026-10-29-modularization-remediation-plan-ko.md:5`). 보완1·보완5가 늦어지면 1차-2 이후가 막힌다.
12. remember 내용의 비밀값을 vault-graph도 publish-draft도 가리지 않을 수 있다. Vault가 git으로 동기화되면 밖으로 나간다(설계 페이지 위험1과 같은 종류). publish-draft lint가 비밀값을 검사하는지 확인하지 않았다.
13. 결정7은 2026-10-30에 사람이 확정했다(9절 질문7). 남은 위험 없음.
14. 측정1 성공 기준이 조건A에서 충족되지 않을 수 있다. Vault 검색은 wiki 126쪽 규모에서 제목 가중치가 커서 강할 수 있다(설계 페이지 §01 "가치가 아닌 것"). 그 경우의 처리는 9절 질문1에 포함한다.
15. 과거 설계 문서 약 90개가 `docs/SPEC.md`를 링크한다. 그 링크가 가리키던 v5.0 또는 v1.2 절은 새 SPEC에 없다. 과거 문서는 고치지 않으므로 읽는 사람이 보관본을 따로 찾아야 한다.
16. 구획C는 문서 단위 상태와 `supersedes`·`superseded_by`만 본다. 문서는 현재인데 그 안의 claim 하나가 `superseded`인 경우는 n차-1 전까지 알리지 못한다.
17. MCP 리소스 읽기 요청에 Claude Code `session_id`가 들어오는지 확인하지 않았다. 들어오지 않으면 "같은 세션에서 주입 뒤 열림"을 정확히 잇지 못하고, 순서 조정은 "주입 수 대비 열린 수"라는 거친 기준으로 한다(4.2.3). 10회 주입·0회 열림 기준도 시작값이다.
18. 1,500토큰과 9,000자 중 어느 쪽이 먼저 닿는지 한국어 Vault에서 재지 않았다. 한글은 글자당 토큰 비율이 영어와 달라 글자 한도가 실제로 더 자주 작동할 수 있다. Claude Code 훅 출력 한도 10,000자는 research가 공식 문서에서 확인한 값이며, 이후 바뀔 수 있다.
19. `memory_kind`가 생기기 전 유형으로 쓰는 frontmatter `type`이 모든 기억 문서에 있는지 확인하지 않았다.
20. 에이전트가 구획B 목록만 보고 본문을 열지 않으면 결정 내용이 문맥에 들어가지 않는다. 구획A가 이를 일부 막지만 의존5 전에는 비어 있다(research 옵션1 단점).
21. Claude Code 대화 기록(JSONL)에 SessionStart 훅 출력이 남는지 확인하지 않았다. `resume`에서 구획C만 내는 설계(S13)는 이전 주입이 대화 기록에 남는다는 전제에 기댄다.

## 8. Acceptance criteria

명령은 저장소 루트에서 Python 3.12로 실행한다. "수동"이라고 적은 항목은 실행 결과를 PR 설명에 남긴다.

문서 (1차-0)

- A-1 `docs/archive/SPEC-v5.0.md`가 있고, 맨 위 안내 한 줄을 빼면 본문이 `28f1c96`의 `docs/SPEC.md`와 같다. 새 `docs/SPEC.md`의 제목은 Local-Graph이고 4.1절 2번의 항목 1~10을 모두 담는다.
- A-2 새 `docs/SPEC.md`에 "Minimum JSON shape" 제목과 JSON이 있고, `tests/test_context_pack_docs_contract.py`가 바꾸지 않은 채로 통과한다.
- A-3 `AGENTS.md` Project Boundary, `docs/TODO.md` Operating Rules, `docs/ARCHITECTURE.md` §4, VG-MOD INV-01·INV-04가 모두 같은 원칙을 적는다. vault-graph는 Vault 파일을 직접 쓰지 않는다, Vault 쓰기는 remember가 publish-draft를 실행하는 것뿐이다, `raw/`에 쓰지 않는다. `docs/TODO.md`에 "Active Roadmap: Software Invariant Engine" 제목이 없다.
- A-4 1차-0 커밋은 `AGENTS.md`와 `docs/**`만 바꾼다(`git diff --stat 28f1c96 -- src tests packages pyproject.toml`이 비어 있다). `docs/DECISIONS.md`는 spec 승인 전에는 바뀌지 않는다.
- A-5 새 `docs/SPEC.md`와 `docs/TODO.md`에 n차-1~9와 의존1~7이 있고, 의존 항목마다 소유자와 "미구현" 여부가 적혀 있다.

선행과 측정

- A-6 1차-2 커밋 전에 보완1의 기능 간 가져오기 방향 테스트가 있고 통과한다. 새 모듈 `vault_map`, `remember_service`, `vault_publish_cli`, `recall`이 그 테스트의 영역 표에 들어 있다.
- A-7 (수동) 1차-1 기준선 보고서가 `docs/design/reports/`에 있다. 질문 수 20, 시스템별 적중률, 첫 실행 시간과 중앙값, 조건, 커밋이 적혀 있고, 질문 파일의 질문 문장은 하나도 들어 있지 않다.

`vault-map.json` 읽기 (1차-2)

- A-8 구조만 남긴 fixture로 다음을 테스트한다. version 2를 읽는다. 다른 version이나 깨진 JSON은 경고를 내고 무시한다. 파일이 없으면 `project-bindings.json`을 쓴다. root, remote, 폴더 이름 순서로 프로젝트를 고르고, 한 단계에서 둘 이상 맞으면 정하지 않는다. git worktree 안의 `cwd`와 심볼릭 링크 `cwd`도 같은 프로젝트로 찾는다. 모든 테스트 전후로 fixture 파일의 해시가 같다.
- A-9 `vg setup`에서 `--vault`를 생략하면 map의 Vault가 모두 등록되고, `--vault`를 주면 `28f1c96`과 같은 결과가 나온다. `vg status`가 map 위치, 버전, 등록되지 않은 map Vault를 보여준다. 조회 명령은 Graph Home에 새 파일을 만들지 않는다.

세션 시작 회상 (1차-3)

- A-10 출력 계약(근거 `research/session-start-recall.md` 7절). fixture Vault와 map으로 다음을 테스트한다.
  - A-10a `source=startup` 입력이면 종료 코드 0, 표준 출력에 구획 A(비어 있으면 제목 없이 생략), B, C(해당 없으면 생략), D 순서의 Markdown이 나온다. 추정 토큰 수가 `--max-tokens`(기본 1,500) 이하이고 글자 수가 9,000자 이하다.
  - A-10b 구획B의 모든 줄에 ID, 유형, 날짜, 상태, 제목, Vault 상대 경로, 추정 토큰 수가 있다. `stale`·`deprecated`·`superseded` 문서는 없다. `inferred`·`contested` 항목에는 "추정", "논쟁 중" 표시가 있다. 프로젝트 범위 밖 문서는 없다. `pin`·`memory_kind`가 없는 fixture에서는 구획A가 출력되지 않고 유형은 frontmatter `type` 값이다.
  - A-10c 직전 실행에서 주입된 항목 하나에 `status: superseded`와 `superseded_by`를 주고 다시 색인한 뒤 실행하면 구획C에 "옛 제목 → 새 제목 (날짜)" 줄이 정확히 하나 나온다. `usage/`를 지운 상태에서는 같은 항목이 "최근 14일" 규칙으로 나온다.
  - A-10d 실행 뒤 Graph Home `usage/`에 `injected` 사건이 출력 항목 수만큼 덧붙는다. MCP 리소스 `vault://{vault_id}/pages/{path}` 읽기가 성공하면 `fetched` 사건이 하나 덧붙는다. 실행 전후로 Vault 파일 바이트와 `usage/` 밖 Graph Home 바이트가 같다.
  - A-10e `source=resume`이고 바뀐 것이 없으면 표준 출력이 비고 종료 코드가 0이다. 바뀐 것이 있으면 구획C만 나오고 종료 코드 0이다. `source=fork`도 같다.
  - A-10f `--max-tokens 300`이면 구획A·C·D가 남고 구획B가 줄며 끝에 "N개 생략"이 있다. 9,000자를 넘는 fixture에서는 토큰 한도 안이어도 9,000자에서 멈춘다.
  - A-10g 임베딩 제공자나 벡터 저장소를 만들면 실패하는 대역으로도 A-10a가 통과한다.
  - A-10h (수동) 실제 Vault에서 연속 20회 실행의 p95가 2초 이하다.
  - A-10i `usage/`를 쓰기 금지로 만든 상태에서도 A-10a 결과와 종료 코드가 같고, 표준 오류에 경고 한 줄이 있다. 리소스 읽기도 성공한다.
- A-11 종료 코드와 넘김. 6절의 "회상할 수 없음" 상황(map 없음 + binding 없음, Vault 미등록, Graph Home 없음, `startup`에서 구획 A·B·C가 모두 빔) 각각에서 표준 출력이 비고 종료 코드가 정확히 3이다. 예상하지 못한 예외는 표준 출력이 비고 0도 3도 아닌 코드다. 종료 코드 3인 경우에는 `usage/`에 아무것도 덧붙지 않고, Graph Home이 없으면 만들지 않는다.
- A-12 (수동, 의존1이 없으면 사람이 임시로 훅을 설정) map에 연결된 프로젝트에서 새 Claude Code 세션을 열면 회상 묶음이 잘리지 않고 문맥에 들어간다(`/context`로 확인). 같은 세션을 resume하면 바뀐 것이 없을 때 아무것도 추가되지 않고 `recall.sh` 결과도 들어가지 않는다. vg를 PATH에서 빼면 `recall.sh` 결과가 들어간다. 2주 운영 뒤 `usage/`에서 계산한 "주입 대비 열린 비율"을 측정1 보고서에 적는다.

remember (1차-4)

- A-13 가짜 `VaultPublisher`로 다음을 테스트한다. 입력 확인 실패는 `rejected`이고 publisher가 불리지 않는다. 대상 Vault는 `vault` 인자, 연결 Vault 하나, 그 밖에는 `error` 순서로 정해진다. draft 임시 디렉터리는 성공·실패·시간 초과 모두에서 지워진다. 같은 Vault에 대한 동시 호출은 순서대로 실행된다. publisher 결과가 `published`·`rejected`·`error`로 그대로 옮겨진다. vault-graph 자신은 Vault 루트 아래에 파일을 만들지 않는다.
- A-14 (Vault 도구가 있을 때만 도는 선택 테스트) 임시 디렉터리에 복사한 Vault에서 remember가 `wiki/decisions/` 아래 파일 하나를 기록하고 publish-draft lint가 통과한다. 필수 필드를 뺀 draft는 `rejected`이고 복사본의 바이트가 바뀌지 않는다. 실제 사용자 Vault로는 실행하지 않는다.
- A-15 MCP 도구 목록이 기존 11개와 `remember`다. 기존 11개 도구의 이름과 입력·출력 스키마가 `28f1c96`과 같다. 기존 read-only 경계 테스트(`tests/test_mcp_tool_read_only_boundary.py` 등)를 호출되면 실패하는 publisher 대역과 함께 실행해도 통과한다. `vg index`, `vg watch` 한 번 실행에서도 publisher가 불리지 않는다. 이 기준의 "쓰지 않음"은 MCP 도구에 대한 것이다. MCP 페이지 리소스 읽기가 Graph Home `usage/`에 덧붙여 기록하는 것은 A-10d가 따로 다루며, `usage/` 밖의 Graph Home과 Vault 바이트는 바뀌지 않아야 한다.
- A-16 README 정의와 경계 문단이 remember를 반영하도록 1차-4 커밋에서 바뀌고, `tests/test_readme_onboarding_contract.py`가 바꾸지 않은 채로 통과한다.

한국어 조사 (1차-5)

- A-17 `strip_korean_particle` 단위 테스트: "결정을"은 "결정", "결정"은 "결정", "책을"은 "책을"(어간 1글자), "GraphRAG"는 그대로다. 본문에 "결정을"만 있는 fixture 문서가 질의 "결정"과 "결정은"으로 검색되고, 본문에 "결정론"만 있는 문서는 질의 "결정"으로 검색되지 않는다.
- A-18 한글이 없는 기존 fixture 질의의 키워드 결과(문서, 점수, 순서)가 `28f1c96`과 같다. 색인 세대 버전이 올라가 있고, 옛 형식 Graph Home에서 `vg status`가 `vg index --full` 필요 경고를 내며 검색은 기존 열로 동작한다. `vg index --full` 뒤에는 A-17의 한글 검색이 동작한다.

전체

- A-19 (수동, 1차-6, 사람이 정한 성공 기준) 측정1을 질문 20개로 조건A(지금 Vault)와 조건B(손으로 옮긴 세션 Vault)에서 다시 실행했을 때 실행 실패가 없고, 두 조건 모두에서 `vg search`의 상위 5개 적중률이 Vault 검색보다 높다. 그리고 1차-5 이후 vg 적중률이 1차-1 기준선보다 낮지 않다.
- A-20 각 단계 커밋에서 전체 `pytest`, `ruff`, `mypy`(`ci.yml` verify 작업 명령)가 통과한다. 기존 CLI 명령과 HTTP 회귀 테스트는 바꾸지 않은 채로 통과한다.
- A-21 `src`에 LLM 클라이언트(`openai`, `anthropic` 등) 가져오기가 없고, `pyproject.toml`에 그런 의존성이 추가되지 않는다.
- A-22 범위: 이 작업은 Vault와 vault-builder 저장소의 파일을 바꾸지 않는다. 1차에서 `project-bindings.json` 관련 코드와 `vg vault add`는 지워지지 않는다.

## 9. Open decisions

spec gate에서 정한다. 승인된 답만 `docs/DECISIONS.md`로 옮긴다.

### 질문1 측정1의 조건B와, 조건A에서 성공 기준을 못 넘을 때의 처리

- 배경: 조건B(`raw/sessions/` 포함)는 Vault 수집기(의존2)가 있어야 한다. 그리고 조건A에서는 Vault 검색이 wiki 126쪽 규모에서 강할 수 있다(7절 14번).
- 옵션1 조건B는 의존2가 생긴 뒤 n차-9로 미루고, 1차 성공 판정은 조건A로만 한다. 조건A에서 기준을 못 넘으면 1차-6 보고서에 질문별 원인을 적고, 1차 완료 판정을 사람이 다시 정한다.
- 옵션2 1차에서 Claude Code 대화 몇 개를 사람이 손으로 Markdown으로 옮긴 임시 Vault 복사본을 만들어 조건B를 잰다.
- 옵션3 조건B가 잴 수 있게 될 때까지 측정1 전체를 미룬다.
- 장단점: 옵션1은 지금 바로 잴 수 있지만 가치1(대량 원문 검색)은 아직 확인되지 않는다. 옵션2는 가치1을 일찍 보지만 손으로 옮긴 형식이 실제 수집기 결과와 다를 수 있다. 옵션3은 1차-5의 효과를 확인할 기준선이 없어진다.
- 추천: 옵션1. 1차-5(조사 처리)의 효과를 재려면 조건A 기준선이 지금 필요하고, 조건B는 실제 수집기 형식으로 재야 의미가 있다.
- **답 (2026-10-30, 사용자):** 옵션2 "수동으로 세션 Vault를 만들어 둘 다 측정". 4.2.1, n차-9, A-19에 반영했다.

### 질문2 모듈화 보완4·보완6을 1차의 선행 조건으로 둘 것인가

- 배경: 설계 페이지 단계표는 선행에 보완1·4·6을 넣었다. 보완 계획은 아직 사용자 검토 전 초안이다. 1차 작업이 직접 건드리는 경계는 보완1(방향 테스트)과 보완5(M12↔M17 binding)다.
- 옵션1 보완1·보완5만 선행하고 보완4·6은 1차와 나란히 진행한다.
- 옵션2 설계 페이지대로 보완1·4·6을 모두 끝낸 뒤 1차를 시작한다(보완5도 1차-2 전에).
- 장단점: 옵션1은 1차가 빨리 시작되고, 보완1의 예외 목록이 새 위반을 막으므로 구조가 나빠지지 않는다. 옵션2는 1차-3(회상)이 M10을 쓰기 전에 M10→M15 의존(보완6)이 정리되지만 시작이 늦어진다.
- 추천: 옵션1. 단, 1차-3이 M10에 새 조회를 더해야 하는 경우(7절 7번)에는 그 전에 보완6을 한다.
- **답 (2026-10-30, 사용자):** "모든 보완사항은 합리적이므로 우선순위와 난이도를 참고해서 구현하면 되겠다." 보완1~9를 모두 한다. 순서는 1차 작업에 막히는 것부터, 같은 우선순위에서는 쉬운 것부터 둔다.

| 순서 | 보완 | 1차와의 관계 | 난이도 | 시점 |
|---|---|---|---|---|
| 1 | 보완1 기능 간 가져오기 방향 테스트 | 새 모듈 검사 | 중간 | 1차-0 직후, 1차-2 전 |
| 2 | 보완5 M12↔M17 순환 | 1차-2가 직접 건드림 | 중간 | 1차-2 전 |
| 3 | 보완6 M10→M15 타입 의존 | 1차-3이 M10 사용 | 낮음 | 1차-3 전 |
| 4 | 보완3 색인 서비스의 상태 조회기 주입 | 없음 | 낮음 | 1차와 나란히 |
| 5 | 보완2 준비 상태 판정의 벡터 색인기 주입 | 없음 | 낮음~중간 | 1차와 나란히 |
| 6 | 보완7 남은 순환 3종 | 없음 | 낮음~중간 | 1차와 나란히 |
| 7 | 보완4 저장소 구체 클래스를 Protocol과 주입으로 | 새 모듈이 따를 형태 | 중간~높음 | 1차와 나란히, 1차-4 전 권장 |
| 8 | 보완8 호환 파일 176개와 테스트 169개 파일 경로 정리 | 없음 | 높음(분량) | 1차 뒤 |
| 9 | 보완9 `ARCHITECTURE.md`·VG-MOD 기록 | 없음 | 낮음 | 마지막 |

보완 계획의 결정1(호환 파일 정리 방식)과 결정2(예외 목록 비우기)는 그 계획의 추천안(옵션1, 비움)을 따른다. [가정: 사용자가 "모든 보완사항은 합리적"이라고 했으므로 추천안을 채택한 것으로 본다]

### 질문3 VG-MOD 문서의 INV-01·INV-04 "Vault 내용 기록은 허용하지 않는다"를 어떻게 다룰 것인가

- 배경: brief의 대상 목록에는 없지만 같은 원칙을 담은 승인된 계약이다(1절 문제2). 그대로 두면 remember와 충돌하는 문서가 하나 남는다.
- 옵션1 1차-0에서 INV-01·INV-04에 "remember가 Vault 도구의 publish-draft를 실행하는 경로는 예외, 이 spec 참조" 한 줄을 추가한다.
- 옵션2 VG-MOD는 완료된 과거 계약으로 두고 고치지 않는다. 새 `docs/SPEC.md`와 `docs/ARCHITECTURE.md`가 우선한다고 SPEC에 적는다.
- 장단점: 옵션1은 모든 활성 문서가 같은 말을 하지만 완료 기록 문서를 고친다. 옵션2는 과거 문서를 보존하지만 읽는 사람이 어느 쪽이 맞는지 따져야 한다.
- 추천: 옵션1. VG-MOD는 `docs/ARCHITECTURE.md`가 부모 계약으로 링크하는 활성 문서이고, 고치는 범위가 한 줄이다.
- **답 (2026-10-30, 사용자):** "vault-graph의 읽기 전용은 시장에 영향을 주지 않는다. 이 프로젝트의 규칙을 다시 정의해 쓰기를 허용하고, 그에 맞춰 개선하라." 예외 한 줄이 아니라 INV-01·INV-04를 다시 정의한다(4.1절 6번, S10). 직접 파일 쓰기와 `raw/` 쓰기 금지는 결정8의 "Vault 쓰기는 검증을 거친다" 원칙에 따라 유지한다.

### 질문4 remember 세부(발견25)를 S5대로 정할 것인가

- 배경: 설계 페이지는 draft 생성 주체·위치, 대상 Vault, lint 실패 시 응답을 spec에서 정하라고 남겼다.
- S5의 내용: draft는 vault-graph가 에이전트 필드로 결정적으로 만들어 운영체제 임시 디렉터리에 두고 실행 후 지운다. 대상 Vault는 `vault` 인자 또는 연결 Vault가 하나일 때만 정한다. publish-draft가 실패하면 `rejected`와 이유만 돌려주고 다른 쓰기 경로로 옮기지 않는다.
- 대안1 draft를 Graph Home 아래(`run/remember/`)에 남겨 실패 시 사람이 다시 실행할 수 있게 한다. 장점: 실패한 기록을 잃지 않는다. 단점: Graph Home에 지워야 할 파일이 쌓이고, 내용이 비밀값을 담으면 Vault 밖에 사본이 남는다.
- 대안2 lint 실패 시 Vault 검토 대기열(`wiki_review_create`)로 보낸다. 장점: 기록이 남는다. 단점: vault-graph가 두 번째 쓰기 경로를 갖게 되어 결정8의 "길은 하나" 원칙과 어긋난다.
- 추천: S5 그대로. 실패한 내용은 에이전트 대화에 남아 있으므로 다시 보낼 수 있다.
- **답 (2026-10-30, 사용자):** S5 그대로(임시 파일, 추측 없음, 실패는 보고만).

### 질문5 한국어 조사 처리 방식

- 옵션1 (S7) 질의 쪽에서 조사를 떼고 FTS5 접두 검색어로 찾는다. 장점: 테이블과 색인이 그대로이고 다시 색인할 필요가 없다. Vault 검색과 같은 조사 목록을 쓴다. 단점: "결정론"처럼 어간으로 시작하는 다른 단어도 맞는다. 조사 목록을 두 저장소가 따로 관리한다.
- 옵션2 FTS5 `trigram` 토크나이저로 바꾼다. 장점: 조사 목록 없이 부분 문자열로 맞는다. 단점: 테이블을 다시 만들고 전체 다시 색인이 필요하며 색인이 커진다. 3글자 미만 질의어("결정")는 trigram으로 맞지 않아 별도 처리가 필요하다. 영어 질의의 점수도 바뀌어 INV-05 예외 범위가 넓어진다.
- 옵션3 색인할 때 본문 토큰에서 조사를 뗀 별도 열을 만든다. 장점: 정밀도가 높다. 단점: 스키마와 색인 경로를 바꾸고 다시 색인해야 한다.
- 추천: 옵션1. 1차 범위에서 가장 작고, 측정1 재측정으로 정밀도 손실을 확인할 수 있다. 손실이 크면 n차에서 옵션3을 검토한다.
- **답 (2026-10-30, 사용자):** 옵션3 "색인 때 조사를 떼어 별도 저장". 4.2.5, S7, A-17·A-18에 반영했다.

### 질문6 세션 시작 회상의 내용과 예산(S3)

- 배경: SessionStart 입력에는 질문이 없다. `recall.sh`는 Open Work, Current Decisions, Corrections and Rules 세 섹션을 1,500토큰으로 낸다. vault-graph는 기억 스키마(의존5) 없이는 "Corrections and Rules"를 가려낼 수 없다.
- 옵션1 (S3) 열린 질문, 최근 결정, 최근 변경을 1,500토큰 안에 담는다.
- 옵션2 같은 세 섹션에 예산을 context pack 기본값 8,000토큰으로 둔다.
- 장단점: 옵션1은 `recall.sh`와 문맥 크기가 같아 넘김 전후 차이가 작다. 옵션2는 더 많이 담지만 모든 세션의 시작 비용이 커지고 오래된 기억이 들어갈 위험(위험2)도 커진다.
- 추천: 옵션1. `--max-tokens`로 바꿀 수 있다.
- **답 (2026-10-30, 사용자):** 보류. "시장에서 이런 기능을 하는 프로젝트를 리서치해서 제안하라. vault-graph에 가장 최적화된 경험을 정하라. 토큰 효율, 사용자에게 전달되는 기억의 활용 관리, 기억의 히스토리 등." 조사 결과는 `research/session-start-recall.md`에 두고, 그 결과로 4.2.3·S3·A-10을 다시 쓴다.
- **답 (2026-10-30, 사용자, 조사 뒤):** research 옵션1 "고정 핵심 + 목록 + 변경 알림". 구획 A(고정 핵심 전문, `pin` 필드 전까지 비어 있음), B(한 줄 기억 목록), C(지난 주입 이후 변경 알림), D(기존 MCP 리소스 `vault://{vault_id}/pages/{path}`로 본문 여는 방법 한 줄). 예산은 1,500토큰과 9,000자. 4.2.3, S3, 6절, A-10~A-12에 반영했다.

### 질문9 세션 시작 회상과 리소스 읽기가 Graph Home에 사용 기록을 쓰는 것을 허용할 것인가

- 배경: research 옵션1은 어떤 기억이 들어갔고 실제로 열렸는지 기록해 순서와 정리에 쓴다. 이 기록은 VG-MOD INV-02("정상 조회는 파일을 만들지 않는다")와 충돌한다(research 4.2).
- 옵션1 허용한다. Graph Home `usage/`에만 덧붙여 쓰고, 기록 실패는 회상을 막지 않는다. INV-02를 다시 정의한다.
- 옵션2 허용하지 않는다(research "옵션1-읽기전용"). 구획C는 "최근 14일 안에 대체된 항목"으로만 만들고 순서 조정은 없다.
- 장단점: 옵션1은 예산·선택 기준을 측정으로 고칠 수 있고 구획C가 "지난 주입 이후"를 정확히 안다. 대신 조회가 파일을 쓰게 된다. 옵션2는 조회가 계속 읽기만 하지만 무엇이 쓰였는지 알 수 없다.
- 추천: 옵션1.
- **답 (2026-10-30, 사용자):** 옵션1. 세션 시작 회상과 리소스 읽기는 `usage/`에만 덧붙여 쓰고, 기록 실패는 회상을 막지 않는다. 사용 기록은 1차에서 구획B의 작은 순서 조정과 구획C에만 쓴다. 정리 후보를 보여 주는 `vg memory review`는 1차를 최소로 두기 위해 n차-10으로 미룬다. 4.1절 6번(INV-02 재정의), 4.2.3, S11, A-10d·A-10i에 반영했다.

### 질문10 Vault 기억 frontmatter에 고정 표시와 기억 유형 필드를 요청할 것인가

- 배경: 구획A는 사람이 고정한 문서를 전문으로 넣는다. Vault에는 고정 표시와 기억 유형 필드가 없다. 대체 관계 필드 `supersedes`·`superseded_by`는 이미 있다(Vault `tools/wiki/lib/lint.py:46`).
- 옵션1 의존5(`vault-memory/v1`)에 `pin: true`와 `memory_kind: rule|correction|decision|preference`를 요청한다.
- 옵션2 요청하지 않는다. 구획A는 계속 비고 유형은 `type`만 쓴다.
- 추천: 옵션1. vault-graph가 내용으로 규칙을 추측하지 않고 사람이 정하게 한다.
- **답 (2026-10-30, 사용자):** 옵션1. 의존5 설명에 두 필드를 더했다. 필드가 생기기 전까지 구획A는 비어 있고, 유형은 frontmatter `type`을 쓴다(S12).

### 질문11 `resume` 세션에서 어떻게 동작할 것인가

- 배경: `resume`·`fork`에서는 이전 주입이 대화 기록에 남아 있어 다시 넣으면 중복이다(research 발견6). 원래 설계는 이 경우를 종료 코드 3으로 끝내자고 했는데, 그러면 훅이 `recall.sh`를 써서 오히려 중복이 생긴다.
- 옵션1 vg가 `source`를 읽는다. `resume`·`fork`에서는 구획C만 내고, 알릴 것이 없으면 빈 출력과 종료 코드 0("처리함, 더할 것 없음")으로 끝낸다. 종료 코드 3은 "회상할 수 없음"만 뜻한다.
- 옵션2 훅 스크립트(의존1)가 `source`를 보고 `resume`이면 vg도 `recall.sh`도 부르지 않는다.
- 장단점: 옵션1은 훅이 종료 코드만 보면 되고 규칙이 vg 한 곳에 있다. 옵션2는 vg가 단순해지지만 vault-builder 훅이 규칙을 알아야 하고, `resume` 때 변경 알림을 낼 수 없다.
- 추천: 옵션1.
- **답 (2026-10-30, 사용자):** 옵션1. 4.2.3(`source`별 동작, 종료 코드), 의존1 설명, S4·S13, 6절, A-10e·A-11에 반영했다.

### 질문7 결정7(vault-graph는 LLM을 부르지 않음)을 채택으로 확정할 것인가

- 배경: 이전 대화에서 반대가 없었을 뿐 명시적 채택 기록이 없다(brief §2). 이 spec의 remember 설계와 A-21이 이 결정에 기댄다.
- 옵션1 채택한다. 옵션2 질의 답변 생성에 한해 선택 기능으로 허용한다.
- 장단점: 옵션1은 Local 원칙(키·비용 없음)과 재현성을 지킨다. 옵션2는 Honcho처럼 답을 직접 주지만 모델과 키가 필요하다. `docs/TODO.md`의 "LLM-Backed Answer Composer" 후보도 옵션2 쪽이다.
- 추천: 옵션1. 사람이 정한 방향 이름 Local의 뜻과 같다.
- **답 (2026-10-30, 사용자):** 확정한다.

### 질문8 결정6(자동 기억 확정 규칙)을 이 spec에서 정할 것인가

- 배경: 에피소드와 stated 사실은 검증 통과 시 확정하고 inferred 사실은 검토 대기열을 거치게 하자는 권장안이 있다. 이 규칙을 실행하는 쪽은 Vault 정리 스킬(의존4)이다. vault-graph에 미치는 영향은 "검토 대기열(`scratch/review/`)은 색인하지 않는다"뿐이다.
- 옵션1 이 spec에서는 열어 두고 Vault·vault-builder 쪽 결정으로 넘긴다. vault-graph는 `scratch/review/`를 색인 대상에 넣지 않는다는 점만 SPEC에 적는다.
- 옵션2 권장안을 지금 채택해 DECISIONS에 기록한다.
- 장단점: 옵션1은 규칙을 실행할 쪽이 정하게 한다. 옵션2는 방향이 일찍 정해지지만 vault-graph 저장소가 Vault 정책을 기록하게 된다.
- 추천: 옵션1. 지금 색인 범위 `DEFAULT_CONTENT_SCOPES`(`src/vault_graph/operation/scope/vault_catalog.py:12`)에 `scratch/review`가 없으므로 vault-graph 쪽 변경은 필요 없다.
- **답 (2026-10-30, 사용자):** 옵션2 "지금 권장안을 채택". 결정6: 에피소드와 사용자가 직접 말한 사실(stated)은 검증을 통과하면 확정하고, LLM이 추론한 사실(inferred)은 검토 대기열을 거친다. 실행 주체는 Vault 정리 스킬(의존4)이므로 DECISIONS에는 "Vault 쪽이 실행하는 정책"으로 적고, vault-builder 요청7을 결정된 정책으로 갱신한다. vault-graph 쪽 영향은 `scratch/review/`를 색인하지 않는 것과, 1차 remember가 stated만 다루는 것(S6)이다.
