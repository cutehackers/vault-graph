# `explore_project`가 등록 없이 cwd의 git 저장소를 읽는다

<!-- bake: index -->
| ID | title | status | relations | covered by | area | hash | tasks |
|---|---|---|---|---|---|---|---|
| I1 | 저장소와 Graph Home에 아무것도 쓰지 않는다 |  | basis X6, X7 | A4 | global | 6f757f79 | 1-live-repository-reader.md |
| I2 | `repository_id`를 주면 지금과 같은 등록 저장소 경로를 쓴다 |  | basis X1 | A3 | explore_project | ca547f7f | 2-service-live-repository.md |
| I3 | 등록 저장소 안의 경로는 등록 저장소로 간다 |  | basis X1, X4 | A3 | explore_project | 8c8d5b03 | 2-service-live-repository.md |
| I4 | 등록되지 않은 저장소에 대해 Vault를 추측하지 않는다 |  | basis X5 | A7 | explore_project | df906fd1 | 2-service-live-repository.md |
| I5 | 응답과 오류에 절대 경로가 나오지 않는다 |  | basis X8, X10 | A2 | explore_project | feae3e3e | 2-service-live-repository.md |
| I6 | 설정된 binding의 검증은 약해지지 않는다 |  | basis X3 | A7 | explore_project | c7864f37 | 2-service-live-repository.md |
| I7 | 호출 한 번의 일에 상한이 있다 |  | basis X11 | A6, A12 | explore_project | 091bf82f | 1-live-repository-reader.md |
| D1 | 등록 저장소가 없어도 cwd의 git 저장소에서 코드 결과를 낸다 | decided | basis X1, 2026-11-25-memory-intent-layers:D9, I1, I2 | A1, A12 | explore_project | 63338677 | 2-service-live-repository.md |
| D2 | 저장소는 `repository_id`, 대상 경로의 등록 저장소, 대상 경로의 git 뿌리 순서로 고른다 | proposed | basis I2, I3, X1, X2; depends D8, D11 | A8 | explore_project | 6637e3a2 | 2-service-live-repository.md |
| D3 | 코드 결과는 호출마다 git 저장소를 직접 읽어 만든다(옵션1) | decided | basis X7, X11, X12, I1, I7 | A1, A11, A12 | explore_project, 코드 읽기 | 5a509518 | 1-live-repository-reader.md |
| D4 | 파일 목록은 git에서 얻고 symlink와 submodule은 읽지 않는다 | proposed | basis X12, I1; depends D3 | A5 | 코드 읽기 | 13b2b13f | 1-live-repository-reader.md |
| D5 | 작업 설명의 낱말로 후보 파일을 고르고, 이름이 맞는 심볼을 돌려준다 | proposed | basis X7, I7; depends D3, D4 | A1, A6 | 코드 읽기 | 3b602cc8 | 1-live-repository-reader.md |
| D6 | git 저장소 증거는 이름표 `git:<폴더 이름>`과 HEAD revision을 단다 | proposed | basis X6, X8, I5; depends D3, D5 | A1 | explore_project, 코드 읽기 | 379a3644 | 2-service-live-repository.md |
| D7 | git 저장소의 Vault는 vault-map과 binding으로 정하고, 없으면 `binding`을 비운다 | proposed | basis X3, X5, I4, I6 | A7 | explore_project | 9c941460 | 2-service-live-repository.md |
| D8 | `explore_project`가 `cwd`를 받는다 | proposed | basis X2 | A8 | explore_project, MCP | 878c1d87 | 3-mcp-cwd-docs.md |
| D9 | git 저장소 밖이면 `not_a_git_repository` 오류를 낸다 | decided | basis X1, I5, 2026-11-25-memory-intent-layers:F9 | A2 | explore_project, MCP | 7153521b | 3-mcp-cwd-docs.md |
| D10 | MCP 안내문, FEATURES, TODO를 새 동작에 맞춘다 | proposed | basis X9, X12; depends D1, D8 | A10, A11 | MCP, 문서 | 02754141 | 3-mcp-cwd-docs.md |
| D11 | 대상 경로가 없으면 binding이 있는 유일한 등록 저장소, 그다음 서버 작업 폴더를 본다 | decided | basis X1, X2, X10; depends D2 | A9 | explore_project | adea5be2 | 2-service-live-repository.md |
| F1 | 대상 경로가 git 저장소 밖이거나, 없거나, git을 실행할 수 없다 |  | basis D2, D9, X6 | A2 |  | 39319224 | 2-service-live-repository.md |
| F2 | 인자 없이 불렀고 서버 작업 폴더가 git 저장소 밖이다 |  | basis D11, D9, X1 | A9 |  | d0c2052b | 2-service-live-repository.md |
| F3 | 등록 저장소 안의 경로인데 그 저장소의 코드 투영이나 binding이 없다 |  | basis D2, I3 | A3 |  | 3c7d3ee3 | 2-service-live-repository.md |
| F4 | git 저장소에 맞는 Vault가 하나도 없다 |  | basis D7, I4 | A7 |  | 32eb0f58 | 2-service-live-repository.md |
| F5 | 작업 설명에서 낱말이 나오지 않거나 어떤 파일에도 맞지 않는다 |  | basis D5 | A6 |  | f818c53a | 1-live-repository-reader.md |
| F6 | git 명령이 시간을 넘기거나 후보가 상한을 넘는다 |  | basis D5, I7 | A6 |  | de68321f | 1-live-repository-reader.md |
| F7 | 후보 파일을 읽거나 파싱하지 못한다 |  | basis D4, D5 | A5 |  | d044bc9f | 1-live-repository-reader.md |
| F8 | working tree에 commit 안 된 변경이 있거나 HEAD가 없다 |  | basis D6, I1 | A4 |  | 60f8d2d6 | 1-live-repository-reader.md |
| F9 | 범위 인자를 여러 개 함께 준다 |  | basis D8, I2 | A3 |  | 6fc5798d | 3-mcp-cwd-docs.md |
| R1 | 큰 저장소에서 git 읽기가 몇 초 안에 끝나지 않을 수 있다 |  | basis X11, D5 |  |  | 6d83b399 |  |
| R2 | MCP 서버의 작업 폴더가 프로젝트 폴더가 아닐 수 있다 |  | basis X2, D10, D11 |  |  | 5e5f1fbe |  |
| R3 | 이름표 `git:<이름>`이 등록 저장소 id나 다른 저장소 이름과 겹칠 수 있다 |  | basis D6 |  |  | cb532e6c |  |
| R4 | `binding`이 null이 되면 응답을 읽는 쪽이나 테스트가 깨질 수 있다 |  | basis X3, D7 |  |  | 1e3f0c8a |  |
| R5 | 안내문 문구를 고정한 테스트가 있을 수 있다 |  | basis X9, D10 |  |  | 36f826dd |  |
| A1 | 등록 저장소가 0개일 때 git 저장소 안의 cwd에서 코드 증거가 나온다 |  | covers D1, D3, D5, D6 |  |  | 8bba97a5 | 2-service-live-repository.md |
| A2 | git 저장소 밖이면 등록 안내 없는 `not_a_git_repository` 오류가 난다 |  | covers D9, F1, I5 |  |  | df9a6c2a | 3-mcp-cwd-docs.md |
| A3 | `repository_id`와 등록 저장소 경로는 지금과 같이 동작한다 |  | covers I2, I3, F3, F9 |  |  | b7845149 | 3-mcp-cwd-docs.md |
| A4 | 호출 뒤 저장소와 Graph Home의 바이트가 그대로다 |  | covers I1, F8 |  |  | cd8b1184 | 2-service-live-repository.md |
| A5 | 파일 목록은 git에서 오고 무시된 폴더와 symlink를 읽지 않는다 |  | covers D4, F7 |  |  | 838c3a60 | 1-live-repository-reader.md |
| A6 | 상한에 걸리면 자른 결과와 경고를 내고, 낱말이 없으면 빈 결과로 성공한다 |  | covers I7, F5, F6, D5 |  |  | b01ed46d | 1-live-repository-reader.md |
| A7 | Vault는 vault-map과 binding으로만 정하고, 없으면 binding이 null이다 |  | covers D7, I4, I6, F4 |  |  | d24a943a | 2-service-live-repository.md |
| A8 | `cwd` 인자를 받고 범위 인자의 우선순위가 D2, D8대로다 |  | covers D2, D8 |  |  | e0b9fff5 | 3-mcp-cwd-docs.md |
| A9 | 인자가 없으면 D11의 순서로 저장소를 고른다 |  | covers D11, F2 |  |  | c2d46268 | 2-service-live-repository.md |
| A10 | 안내문, FEATURES, TODO가 새 동작을 적는다 |  | covers D10 |  |  | 81d43c88 | 3-mcp-cwd-docs.md |
| A11 | 바뀐 파일이 §4.5 목록 안에 있고 push와 PR이 없다 |  | covers D3, D10 |  |  | 03602fb8 | 3-mcp-cwd-docs.md |
| A12 | 이 저장소에서 실제 호출의 git 읽기가 10초 안에 코드 증거를 내고 전체 검증이 통과한다 |  | covers D1, D3, I7 |  |  | 865e9e73 | 3-mcp-cwd-docs.md |
| O1 | 등록되지 않은 저장소의 코드 결과를 어떻게 만들까? |  | decides D3, D5, D6 |  |  | e3a5bef6 |  |
| O2 | 인자 없이 부르고 등록 저장소도 하나뿐일 때 어느 저장소를 볼까? |  | decides D11 |  |  | 6b5f1880 |  |
| X1 | 등록 저장소가 없으면 `explore_project`는 범위 오류로 실패한다 |  |  |  |  | aac4803e |  |
| X2 | `explore_project`는 `cwd`를 받지 않고, 다른 도구는 `cwd`가 없으면 서버 작업 폴더를 쓴다 |  |  |  |  | 85a72d42 |  |
| X3 | `ProjectBinding`은 빈 Vault 목록을 거부하고, `ProjectContext`는 binding을 반드시 가진다 |  |  |  |  | 7c39ebae |  |
| X4 | 코드 증거는 활성 코드 투영의 `CodeQueryService`에서만 나온다 |  |  |  |  | 54a4896e |  |
| X5 | 폴더의 Vault는 `vault-map.json`, 그다음 project binding으로만 정하고 활성 Vault로 넘어가지 않는다 |  |  |  |  | de51cbbc |  |
| X6 | git 실행 도우미는 실패하면 None을 돌려주고, 주 worktree 뿌리를 찾는 함수가 있다 |  |  |  |  | beaaf552 |  |
| X7 | Python·Dart 파서는 파일 하나를 메모리에서 파싱하고, 스캐너에 언어·테스트 판정 규칙이 있다 |  |  |  |  | 79116f05 |  |
| X8 | 응답 직렬화는 `vg-source://` URI와 안전한 상대 경로만 남긴다 |  |  |  |  | 998dbace |  |
| X9 | MCP 안내문, 프롬프트, FEATURES는 등록 저장소를 전제로 적는다 |  |  |  |  | 8544aa80 |  |
| X10 | 기존 테스트는 경로 노출, 어댑터 읽기 전용, import 경계를 본다 |  |  |  |  | c40834ec |  |
| X11 | 이 저장소 전체 코드 투영은 약 25초가 걸리고 97 MB를 쓴다 |  |  |  |  | c5115fc1 |  |
| X12 | 기존 스캐너는 일반 Python checkout에서 `.venv` symlink 때문에 실패한다 |  | basis X7 |  |  | ae50a20a |  |
<!-- bake: index end -->

## 1. Problem

MCP 안내문은 코딩 작업이면 `explore_project`를 먼저 부르라고 하는데, 등록된 코드 저장소가 없는 사용자 Mac에서는 이 도구가 매번 실패한다. 2026-11-25에 커밋 `fd21e3f` 코드를 읽어 확인한 내용은 `research/current-code.md`, 부모 세션의 측정은 `research/measurements.md`에 사실로 적었다.

- 경로를 주면 등록 저장소 안이 아니라서 `unregistered_project_path`가, 아무것도 주지 않으면 `scope_required`가 나온다. 어댑터는 두 오류에 "등록하고 bind하라"는 안내를 붙인다(X1). 사용자 Mac의 `vg code status`에는 등록 저장소가 하나도 없다(brief).
- 다른 도구는 `cwd`를 받거나 서버 작업 폴더를 쓰는데, `explore_project`만 `cwd`를 받지 않는다(X2).
- 코드 증거는 미리 만든 코드 투영에서만 나온다(X4). 이 저장소를 투영하면 약 25초와 97 MB가 든다(X11). 등록 경로의 스캐너는 `.venv` symlink 때문에 일반 Python checkout에서 멈춘다(X12). 그래서 "등록하면 된다"는 안내를 따라도 이 저장소에서는 결과가 나오지 않는다.
- 결과에 Vault 근거를 붙이려면 binding이 있어야 하고, binding은 빈 Vault 목록을 받지 않는다(X3). Vault를 정하는 다른 길(`vault-map.json`, binding)은 이미 있다(X5).
- 나중 일(코드 앵커, `git log <commit>..HEAD -- <path>` 신선도, 방향 4e)도 이 저장소 뿌리가 있어야 한다(`2026-11-25-memory-intent-layers` spec §4.3 결정5).

## 2. Intent

사용자는 등록 단계 없이 `explore_project`가 바로 쓸모 있기를 원한다. 2026-11-25에 사용자가 승인한 결정5(`docs/DECISIONS.md` "2026-11-25 - Let explore_project Read The Git Repository Of cwd Without Registration", `2026-11-25-memory-intent-layers` spec D9, F9)의 내용은 이렇다.

- 등록 저장소가 0개여도 git 저장소 안의 cwd에서 `explore_project`가 코드 결과를 낸다.
- cwd가 어떤 git 저장소에도 속하지 않으면 등록 안내가 아니라 "git 저장소가 아님" 오류를 낸다.
- `repository_id`를 주면 지금처럼 등록 저장소를 쓴다.
- 저장소는 읽기만 한다.

이유: 에이전트에게 먼저 부르라고 하는 도구라면, 대부분의 사용자가 하지 않는 설정 단계 없이 동작해야 한다. 코드 앵커와 그 신선도 확인도 이 저장소 뿌리를 쓴다.

[가정] "코드 결과"는 호출 한 번이 몇 초 안에 끝나는 정도의 결과다. 첫 호출에 수십 초를 기다리게 하는 방식은 사용자 의도에 맞지 않는다고 보았다(X11).

## 3. Non-goals

- 등록 경로의 스캐너와 등록 검증이 추적되지 않는 symlink(`.venv`)에서 멈추는 문제(X12)는 고치지 않는다. 후속 일로 TODO에만 적는다.
- 등록되지 않은 저장소에 영향(impact)과 관련 테스트 추적을 주지 않는다. 그 기능은 등록·색인된 저장소에만 있다.
- Graph Home에 코드 투영, 캐시, 세대 파일을 만들지 않는다. 호출 사이에 서버 메모리에 결과를 남기지도 않는다.
- 코드 앵커, 신선도 표시(4e), 프롬프트 주입은 이번에 하지 않는다. 이번 change는 그 일이 쓸 저장소 뿌리를 찾는 데서 멈춘다.
- 사실 추출기와 vault-builder 코드는 건드리지 않는다. 다른 세션이 같은 시간에 고치고 있다.
- `vg code` CLI 명령과 등록 저장소의 동작은 바꾸지 않는다.
- push와 PR은 사용자에게 묻기 전에는 하지 않는다.

## 4. Design

**4.1 저장소를 고르는 순서**

`ProjectContextService._resolve_repository`가 아래 순서로 저장소 하나를 고른다(D2). 결과는 "등록 저장소"이거나 "git 저장소(등록 안 됨)" 둘 중 하나다.

1. `repository_id`가 있으면 등록 카탈로그에서 찾는다. 지금과 같다.
2. 대상 경로를 정한다. `project_path`, 없으면 새 `cwd` 인자다.
3. 대상 경로가 있으면: 그 경로를 품은 등록 저장소가 하나면 그것을 쓴다(지금과 같다). 아니면 경로의 git 뿌리를 찾아 git 저장소로 쓴다. git 뿌리가 없으면 `not_a_git_repository` 오류다.
4. 대상 경로가 없으면 D11의 규칙을 따른다. 추천안은 binding이 있는 등록 저장소가 정확히 하나면 그것(지금과 같다), 아니면 서버 작업 폴더로 3을 하는 것이다.

**4.2 git 저장소 읽기(옵션1, live read)**

새 모듈 `src/vault_graph/project/code/live_repository_reader.py`가 맡는다(D3). 서명은 이 정도다.

- `LiveRepositoryReader.find_repository(path: Path) -> LiveRepository | None`
- `LiveRepositoryReader.search(repository: LiveRepository, task: str, *, limit: int) -> LiveCodeSearch`

`find_repository`는 `git rev-parse --show-toplevel`로 읽을 뿌리를, `main_worktree_root`로 이름표에 쓸 주 worktree를, `git rev-parse HEAD`로 revision을 얻는다(D6). `search`는 작업 설명에서 낱말을 뽑고, `git grep`으로 후보 파일을 고르고, 후보 중 `.py`, `.dart` 파일만 기존 파서로 메모리에서 파싱한다(D4, D5). 이름이 낱말에 맞는 심볼을 코드 증거로, 다른 언어 파일의 일치는 줄 위치 증거로 돌려준다. 영향과 테스트 추적은 하지 않고 경고로 알린다. 파일 목록은 git에서만 얻고 rglob을 쓰지 않는다(X12).

서비스는 이 모듈을 직접 import하지 않고 `project_context_service.py`의 새 Protocol `ProjectLiveCodeReader`로만 본다. 구현체는 `code_index_factory.py`의 `open_project_context_service`가 넣는다.

**4.3 Vault 범위**

git 저장소의 Vault는 새 Protocol `ProjectVaultResolver.resolve(path: Path) -> tuple[str, ...]`로 정한다(D7). 구현체는 composition에서 `resolve_project_vaults`(vault-map, 그다음 binding)를 감싼다. Vault가 하나 이상이면 그 Vault로 `ProjectBinding`을 만들어 지금과 같은 Vault 근거를 붙인다. 하나도 없으면 `ProjectContext.binding`을 None으로 두고 Vault 근거 없이 코드 증거만 돌려준다. 활성 Vault로 넘어가지 않는다.

**4.4 MCP 입력과 오류**

`explore_project`에 `cwd: str | None = None`을 더한다(D8). `ExploreProjectInput`, `parse_explore_project_input`, `ProjectContextRequest`에 같은 필드가 생긴다. 새 오류 코드 `not_a_git_repository`는 `invalid_parameter`로 나가고, 메시지와 안내에 등록 이야기도 절대 경로도 없다(D9).

**4.5 바꾸는 파일**

- `src/vault_graph/project/code/live_repository_reader.py`(새 파일)
- `src/vault_graph/project/context/project_context_service.py`, `project_context_models.py`
- `src/vault_graph/interface/composition/code_index_factory.py`
- `src/vault_graph/interface/mcp/mcp_tools.py`, `mcp_server.py`, `mcp_prompts.py`, 필요하면 `mcp_tool_serialization.py`
- `docs/FEATURES.md`의 `explore_project` 세 곳, `docs/TODO.md` 결정5 항목(D10)
- 테스트: 새 `tests/test_live_repository_reader.py`, 새 `tests/test_project_context_live_repository.py`, 기존 `tests/test_mcp_explore_project.py`에 사례 추가

### I1. 저장소와 Graph Home에 아무것도 쓰지 않는다
- by: 사람 (DECISIONS 2026-11-25 결정5, "It only reads the repository"), 가정 (Graph Home도 쓰지 않는다)
- area: global
- basis: X6, X7

git 저장소 읽기는 `rev-parse`, `ls-files`, `grep`만 실행하고 `GIT_OPTIONAL_LOCKS=0`을 준다. `git status`처럼 index를 새로 쓸 수 있는 명령은 실행하지 않는다. 파일은 읽기만 하고, 파싱 결과는 호출이 끝나면 버린다. Graph Home에는 세대, 캐시, 로그 파일을 만들지 않는다.

### I2. `repository_id`를 주면 지금과 같은 등록 저장소 경로를 쓴다
- by: 사람 (DECISIONS 2026-11-25 결정5, "A repository_id still selects a registered repository")
- area: explore_project
- basis: X1

`repository_id`가 있으면 `cwd`와 git 읽기는 쓰지 않는다. 카탈로그에 없으면 지금과 같은 오류가 난다. 코드 투영, 영향, 관련 테스트, binding, 관계 조회가 지금처럼 동작한다.

### I3. 등록 저장소 안의 경로는 등록 저장소로 간다
- by: 가정 (색인된 코드와 영향 추적을 잃지 않으려고)
- area: explore_project
- basis: X1, X4

대상 경로가 등록 저장소 하나에 들어 있으면 git 읽기를 하지 않고 지금 경로를 쓴다. 그 저장소의 코드 투영이 없거나 binding이 없을 때의 경고와 오류도 지금과 같다.

### I4. 등록되지 않은 저장소에 대해 Vault를 추측하지 않는다
- by: 가정 (FEATURES의 "never guesses an active Vault"를 이어받는다)
- area: explore_project
- basis: X5

git 저장소의 Vault는 `vault-map.json`과 project binding으로만 정한다. 둘 다 없으면 Vault 근거를 비우고 경고를 낸다. 활성 Vault나 모든 Vault로 넘어가지 않는다.

### I5. 응답과 오류에 절대 경로가 나오지 않는다
- by: 가정 (기존 경로 노출 테스트와 직렬화 규칙을 이어받는다)
- area: explore_project
- basis: X8, X10

git 저장소의 이름표는 주 worktree 폴더 이름만 쓴다. 코드 증거의 경로는 저장소 뿌리 기준 상대 경로다. `not_a_git_repository`를 포함한 오류 메시지와 경고에는 받은 경로나 찾은 뿌리 경로를 넣지 않는다.

### I6. 설정된 binding의 검증은 약해지지 않는다
- by: 가정 (brief의 "without weakening validation for configured bindings")
- area: explore_project
- basis: X3

`ProjectBinding`은 지금처럼 빈 `vault_ids`를 거부한다. Vault가 없는 경우는 binding을 만들지 않고 `ProjectContext.binding`을 None으로 두어 처리한다.

### I7. 호출 한 번의 일에 상한이 있다
- by: 가정 (brief의 "Bounds" 항목)
- area: explore_project
- basis: X11

git 명령 하나는 5초, 호출 한 번의 git 실행 시간 합은 10초, 낱말은 8개, 파싱하는 파일은 50개, 파일 하나는 512 KiB를 넘지 않는다. 결과 수는 `limit`과 지금의 `_bounded_symbol_work`를, 출력 크기는 `max_tokens`를 따른다. 상한에 걸리면 결과를 자르고 경고를 낸다.

## 5. Decisions

D1과 D9의 오류 동작은 사용자가 결정5에서, D3과 D11은 2026-11-25 spec gate(O1 옵션1, O2 옵션A)에서 정했다. 나머지는 이 spec이 제안하고 사용자가 spec 승인으로 받아들인 설계다.

### D1. 등록 저장소가 없어도 cwd의 git 저장소에서 코드 결과를 낸다
- by: 사람 (DECISIONS 2026-11-25 결정5, `2026-11-25-memory-intent-layers` spec 결정5)
- status: decided
- area: explore_project
- basis: X1, 2026-11-25-memory-intent-layers:D9, I1, I2

등록 저장소가 0개이고 cwd가 git 저장소 안이면 `explore_project`는 범위 오류 대신 그 저장소의 코드 증거를 돌려준다. 저장소는 읽기만 하고(I1), `repository_id`를 준 호출은 지금과 같다(I2). 지금은 X1의 두 오류로 끝난다.

### D2. 저장소는 `repository_id`, 대상 경로의 등록 저장소, 대상 경로의 git 뿌리 순서로 고른다
- by: 사람 (결정5: `repository_id` 우선, git 밖이면 오류), 가정 (`project_path`와 `cwd`의 순서, 등록 저장소를 git 읽기보다 먼저 보는 것)
- status: proposed
- area: explore_project
- basis: I2, I3, X1, X2
- depends: D8, D11

순서는 §4.1이다. 대상 경로는 `project_path`, 없으면 `cwd`다. 등록 저장소를 먼저 보는 것은 색인과 영향 추적이 있는 쪽을 버리지 않으려는 것이다(I3). 지금 `unregistered_project_path`가 나던 경우(X1)는 경로가 git 안이면 git 저장소 읽기로, 밖이면 `not_a_git_repository`로 바뀐다. `unregistered_project_path` 오류 코드는 더 나오지 않는다. 대상 경로가 없을 때는 D11을 따른다.

### D3. 코드 결과는 호출마다 git 저장소를 직접 읽어 만든다(옵션1)
- by: 사람 (2026-11-25 spec gate O1, "옵션1 직접 읽기")
- status: decided
- area: explore_project, 코드 읽기
- basis: X7, X11, X12, I1, I7

§4.2의 방식이다. 기존 파서(X7)를 그대로 쓰고 결과를 어디에도 저장하지 않는다. 투영을 만드는 옵션2는 첫 호출이 약 25초이고 MCP 호출이 Graph Home에 97 MB를 쓴다(X11). 그 스캐너는 이 저장소에서 멈춰서(X12) 새 스캐너도 따로 필요하다. 줄 일치만 내는 옵션3은 가장 빠르지만 심볼 이름과 줄 범위가 없어 나중 코드 앵커가 쓸 수 없다. 옵션1은 영향과 테스트 추적을 포기하는 대신 몇 초 안에 심볼 단위 결과를 낸다.

### D4. 파일 목록은 git에서 얻고 symlink와 submodule은 읽지 않는다
- by: 가정 (brief의 "must list files from git")
- status: proposed
- area: 코드 읽기
- basis: X12, I1
- depends: D3

목록은 `git ls-files -s --cached --others --exclude-standard`로 얻는다. 추적 파일과 무시되지 않은 새 파일을 보고, `.gitignore`에 걸린 `.venv` 같은 폴더는 보지 않는다(X12). 모드가 symlink(120000)나 submodule(160000)인 항목은 건너뛴다. 파일을 열 때도 symlink를 따라가지 않는다. 스캐너의 기본 제외 폴더(`node_modules`, `build` 등)에 든 경로도 건너뛴다. rglob은 쓰지 않는다.

### D5. 작업 설명의 낱말로 후보 파일을 고르고, 이름이 맞는 심볼을 돌려준다
- by: 가정 (brief 옵션1의 세부)
- status: proposed
- area: 코드 읽기
- basis: X7, I7
- depends: D3, D4

1. 낱말: 작업 설명을 영문·숫자·`_` 덩어리(3자 이상)와 한글 덩어리(2자 이상)로 나누고, 소문자로 바꾸고, 흔한 영어 낱말을 빼고, 나온 순서로 8개까지 쓴다.
2. 후보: 낱말마다 `git grep -l -i -F --untracked`를 돌리고, 경로에 낱말이 든 파일도 더한다. 맞은 낱말 수가 많은 순, 같으면 경로 순으로 50개를 고른다.
3. 맞추기: `.py`, `.dart` 후보는 기존 파서로 파싱하고, 이름에 낱말이 든 심볼을 맞은 낱말 수, 경로, 줄 순으로 고른다. 다른 파일은 처음 맞은 줄 하나를 줄 위치 증거로 낸다. 심볼 증거가 줄 위치 증거보다 앞선다.
4. 결과 수는 지금의 `_bounded_symbol_work(request)`를 넘지 않는다.

### D6. git 저장소 증거는 이름표 `git:<폴더 이름>`과 HEAD revision을 단다
- by: 가정 (brief의 "stable label such as git:<root directory name>")
- status: proposed
- area: explore_project, 코드 읽기
- basis: X6, X8, I5
- depends: D3, D5

- 읽는 뿌리는 `git rev-parse --show-toplevel`(에이전트가 고치는 worktree)이다. 이름표는 `main_worktree_root`의 폴더 이름을 써서 `git:<이름>`으로 하고, 같은 저장소의 worktree들이 같은 이름표를 갖게 한다.
- 심볼 증거: `evidence_id`는 `code:<파서 symbol_id>`, 제목은 `qualified_name`, 요약은 서명이나 종류다. 줄 위치 증거: `evidence_id`는 `code:line:<상대 경로>:<줄>`, 요약은 `line match: <낱말>`이고 소스 본문은 넣지 않는다.
- `revision`은 `git:<HEAD>`, `freshness`는 `fresh`, `reasons`에 `live_symbol_match`나 `live_line_match`와 `working_tree`를 단다. `source_uri`는 직렬화가 받는 `vg-source://` 꼴로 만든다(X8).
- 경고 `code_live_read`를 늘 하나 낸다. "색인 없이 working tree를 읽었고, 영향과 관련 테스트는 색인된 저장소에서만 나온다"는 뜻이다. `impact_evidence`, `test_evidence`는 비어 있다.

### D7. git 저장소의 Vault는 vault-map과 binding으로 정하고, 없으면 `binding`을 비운다
- by: 가정 (brief의 Vault 범위 가정)
- status: proposed
- area: explore_project
- basis: X3, X5, I4, I6

`ProjectVaultResolver`가 `resolve_project_vaults`로 Vault를 정한다(X5). Vault가 있으면 `ProjectBinding(repository_id=<이름표>, vault_ids=...)`을 만들어 지금처럼 Vault 상태, 근거, 관계를 붙인다. 없으면 `ProjectContext.binding`의 타입을 `ProjectBinding | None`으로 넓혀 None을 넣고, Vault 근거와 관계 없이 경고 `project_vault_scope_unresolved`를 낸다. `ProjectBinding` 자체의 검증은 그대로다(I6). 응답 JSON의 `binding`은 이때 null이다.

### D8. `explore_project`가 `cwd`를 받는다
- by: 가정 (다른 도구와 같게, X2)
- status: proposed
- area: explore_project, MCP
- basis: X2

MCP 서명에 `cwd: str | None = None`을 더하고 `ExploreProjectInput`, `ProjectContextRequest`에도 같은 필드를 둔다. `project_path`와 `cwd`를 함께 주면 `project_path`를 쓴다. `repository_id`와 `cwd`를 함께 주면 `repository_id`를 쓰고 `cwd`는 무시한다. 에이전트가 `cwd`를 늘 넘기므로 이 조합을 거절하면 안 된다. `project_path`와 `repository_id`를 함께 주면 지금처럼 거절한다. 빈 문자열 `cwd`는 다른 도구처럼 `invalid_arguments`다.

### D9. git 저장소 밖이면 `not_a_git_repository` 오류를 낸다
- by: 사람 (DECISIONS 2026-11-25 결정5, `2026-11-25-memory-intent-layers` spec 결정5의 실패 규칙), 가정 (오류 메시지와 안내 문구)
- status: decided
- area: explore_project, MCP
- basis: X1, I5, 2026-11-25-memory-intent-layers:F9

서비스는 `not_a_git_repository; ...` 꼴의 `ValueError`를 던지고, 어댑터의 `_is_project_scope_error`와 `_project_scope_error`가 이를 `invalid_parameter`, 코드 `not_a_git_repository`로 바꾼다. 메시지는 "The folder is not inside a git repository."이고 안내는 "Pass cwd set to a folder inside a git repository."다. 등록, `vg project bind`, `repository_id` 이야기는 넣지 않는다. 받은 경로도 넣지 않는다(I5).

### D10. MCP 안내문, FEATURES, TODO를 새 동작에 맞춘다
- by: 가정 (brief의 후속 항목, MCP 파일이라 이번 범위로 보았다)
- status: proposed
- area: MCP, 문서
- basis: X9, X12
- depends: D1, D8

- `mcp_server.py` 안내문의 "registered repositories"를 "registered repositories or the git repository of cwd"로 바꾼다. `mcp_prompts.py:147`의 "for the registered project"를 "for the project in cwd"로 바꾼다.
- `docs/FEATURES.md`의 `explore_project` 표 두 줄과 설명 문단을 새 동작과 `cwd` 인자에 맞춘다. "활성 Vault를 추측하지 않는다"는 남긴다.
- `docs/TODO.md` 결정5 항목에 체크하고, 등록 스캐너의 symlink 문제(X12)를 후속 항목으로 적는다.

### D11. 대상 경로가 없으면 binding이 있는 유일한 등록 저장소, 그다음 서버 작업 폴더를 본다
- by: 사람 (2026-11-25 spec gate O2, "옵션A 등록 먼저")
- status: decided
- area: explore_project
- basis: X1, X2, X10
- depends: D2

`project_path`도 `cwd`도 없으면, binding이 있는 등록 저장소가 정확히 하나일 때 그것을 쓴다(지금과 같다, X1). 아니면 서버 작업 폴더(`Path.cwd()`)를 대상 경로로 삼아 §4.1의 3단계를 한다. 거기서도 git 뿌리가 없으면 `not_a_git_repository`다. 등록 저장소가 0개인 사용자 Mac에서는 곧바로 서버 작업 폴더를 본다. 기존 서비스 테스트(X10)는 바뀌지 않는다.

## 6. Failure and boundary behavior

### F1. 대상 경로가 git 저장소 밖이거나, 없거나, git을 실행할 수 없다
- basis: D2, D9, X6

`not_a_git_repository` 오류를 낸다. 경로가 없을 때, bare 저장소나 `.git` 폴더 안이라 `--show-toplevel`이 실패할 때도 같다. `run_git`은 git이 없는 것과 git 밖인 것을 구별하지 않으므로(X6), None이 오면 `git --version`을 한 번 더 실행한다. 이것도 실패하면 같은 코드에 메시지만 "git could not be run."으로 바꾼다. 어느 경우에도 등록 안내와 경로는 넣지 않는다.

### F2. 인자 없이 불렀고 서버 작업 폴더가 git 저장소 밖이다
- basis: D11, D9, X1

binding이 있는 등록 저장소가 정확히 하나면 그것을 쓴다. 0개나 2개 이상이면 `not_a_git_repository`를 낸다. 지금의 `scope_required`는 이 경우에 더 나오지 않는다. 등록 저장소에 binding이 없을 때 나오는 `scope_required`(X1)는 지금 그대로다.

### F3. 등록 저장소 안의 경로인데 그 저장소의 코드 투영이나 binding이 없다
- basis: D2, I3

git 읽기로 바꾸지 않는다. 투영이 없으면 지금처럼 `code_index_unavailable` 경고와 Vault 근거를 낸다. binding이 없으면 지금처럼 `scope_required` 오류다. 등록한 사람이 고른 설정을 따르는 것이다.

### F4. git 저장소에 맞는 Vault가 하나도 없다
- basis: D7, I4

코드 증거만 돌려주고 `binding`은 null, `vault_evidence`는 비운다. 경고 `project_vault_scope_unresolved`를 내고, `resolve_project_vaults`의 이유 문장에서 경로를 뺀 뜻(vault-map 프로젝트도 binding도 없음)을 메시지로 쓴다. 활성 Vault로 넘어가지 않는다. 호출은 실패하지 않는다.

### F5. 작업 설명에서 낱말이 나오지 않거나 어떤 파일에도 맞지 않는다
- basis: D5

코드 증거 없이 성공으로 돌려준다. 낱말이 0개면 경고 `code_live_no_terms`, 맞는 파일이 0개면 경고 `code_live_no_match`를 낸다. 한국어 낱말만 있으면 심볼 이름에는 거의 맞지 않고 주석이나 문서 줄에만 맞는다. 이것은 오류로 보지 않는다.

### F6. git 명령이 시간을 넘기거나 후보가 상한을 넘는다
- basis: D5, I7

시간을 넘긴 낱말은 건너뛰고, 10초 합계에 닿으면 남은 낱말을 보지 않는다. 후보가 50개를 넘으면 순위대로 자른다. 어느 경우든 그때까지 모은 결과를 돌려주고, 코드 쪽 freshness를 `partial`로 하고 경고 `code_live_read_truncated`를 낸다.

### F7. 후보 파일을 읽거나 파싱하지 못한다
- basis: D4, D5

512 KiB를 넘는 파일, UTF-8로 읽을 수 없는 파일, symlink, 읽기 중 사라진 파일은 건너뛴다. 파서가 예외를 던지거나 진단만 내면 그 파일은 줄 위치 증거로 대신한다. 건너뛴 수를 경고 `code_live_files_skipped` 하나로 알리고, 파일 경로는 상대 경로만 쓴다.

### F8. working tree에 commit 안 된 변경이 있거나 HEAD가 없다
- basis: D6, I1

내용은 working tree에서 읽고 `revision`은 `git:<HEAD>`다. 그래서 줄 번호가 HEAD와 다를 수 있고, 증거의 `working_tree` 이유가 이를 알린다. 변경 여부를 보려고 `git status`를 실행하지는 않는다(I1). commit이 하나도 없는 저장소는 `revision`을 null로 두고 무시되지 않은 새 파일만 읽는다.

### F9. 범위 인자를 여러 개 함께 준다
- basis: D8, I2

`repository_id`와 `cwd`면 `repository_id`만 쓴다. `project_path`와 `cwd`면 `project_path`만 쓴다. `project_path`와 `repository_id`면 지금처럼 `invalid_arguments`로 거절하고, 메시지에 경로를 넣지 않는다.

## 7. What could be wrong

### R1. 큰 저장소에서 git 읽기가 몇 초 안에 끝나지 않을 수 있다
- basis: X11, D5

전체 투영 시간(X11)만 있고 `git grep` 8번과 파일 50개 파싱 시간은 재지 않았다. 이 저장소(추적 `.py`, `.dart` 684개)에서는 짧을 것으로 보지만, 수만 파일 저장소에서는 10초 합계에 자주 닿아 결과가 `partial`이 될 수 있다.

### R2. MCP 서버의 작업 폴더가 프로젝트 폴더가 아닐 수 있다
- basis: X2, D10, D11

Claude Code가 MCP 서버를 프로젝트 폴더에서 띄운다고 보았지만 플러그인 설정은 확인하지 않았다. 서버 작업 폴더가 다르면 `cwd`를 넘기지 않은 호출은 엉뚱한 저장소를 읽거나 `not_a_git_repository`를 낸다. 안내문(D10)이 `cwd`를 넘기라고 말해야 하는 이유다.

### R3. 이름표 `git:<이름>`이 등록 저장소 id나 다른 저장소 이름과 겹칠 수 있다
- basis: D6

등록 저장소 id에 `:`를 쓸 수 있는지 카탈로그 검증을 읽지 않았다. 폴더 이름이 같은 다른 저장소 두 개는 같은 이름표를 갖는다. 이 이름표는 응답 안에서만 쓰여 지금은 문제가 없지만, 나중 코드 앵커가 이름표를 키로 쓰면 충돌한다.

### R4. `binding`이 null이 되면 응답을 읽는 쪽이나 테스트가 깨질 수 있다
- basis: X3, D7

직렬화는 `asdict`로 `binding`을 그대로 내보낸다(X3). 응답 schema 버전을 올려야 하는지, `binding`을 읽는 다른 코드나 테스트가 있는지는 `src/`의 `.binding` 사용 한 곳만 확인했다. `tests/`와 텍스트 미러는 보지 않았다.

### R5. 안내문 문구를 고정한 테스트가 있을 수 있다
- basis: X9, D10

`mcp_server.py` 안내문과 `mcp_prompts.py` 문구를 그대로 비교하는 테스트가 있는지 찾지 않았다. 있으면 D10과 함께 고쳐야 한다.

## 8. Acceptance criteria

A1~A4는 사용자가 정한 성공 기준이고, A11~A12는 사용자가 준 범위 제한이다. 테스트의 git 저장소는 `tmp_path`에 `git init`으로 만들고, 등록 카탈로그는 비운다.

### A1. 등록 저장소가 0개일 때 git 저장소 안의 cwd에서 코드 증거가 나온다
- covers: D1, D3, D5, D6
- check: tests/test_project_context_live_repository.py, tests/test_live_repository_reader.py
- evidence: tests/test_project_context_live_repository.py `test_zero_registered_repositories_return_live_code_evidence`, tests/test_live_repository_reader.py `test_search_returns_symbol_hits_before_line_hits`, `test_linked_worktree_uses_main_worktree_folder_name

`def run_request_flow()`가 든 `.py` 파일과 `.md` 파일 하나가 있는 저장소에서 `task="run request flow"`, `cwd=<저장소 하위 폴더>`로 부르면, 심볼 증거 하나 이상이 줄 위치 증거보다 앞에 온다. 증거는 `repository_id="git:<폴더 이름>"`, 상대 경로, 줄 범위, `revision="git:<HEAD>"`, 이유 `live_symbol_match`와 `working_tree`를 갖고, 경고 `code_live_read`가 있으며 `impact_evidence`, `test_evidence`는 비어 있다. linked worktree에서 불러도 이름표는 주 worktree 폴더 이름이다.

### A2. git 저장소 밖이면 등록 안내 없는 `not_a_git_repository` 오류가 난다
- covers: D9, F1, I5
- check: tests/test_mcp_explore_project.py, tests/test_project_context_live_repository.py
- evidence: tests/test_mcp_explore_project.py `test_explore_project_outside_git_returns_not_a_git_repository`[outside/missing/no-git], tests/test_project_context_live_repository.py `test_outside_git_raises_not_a_git_repository_without_registration_hint`, `test_git_that_cannot_run_raises_not_a_git_repository

git 밖 폴더, 없는 경로, git을 실행할 수 없는 환경(PATH에서 git을 뺌) 세 경우 모두 오류 kind가 `invalid_parameter`, 코드가 `not_a_git_repository`다. 메시지와 안내에 `register`, `bind`, `repository_id`, 받은 경로 문자열이 없다.

### A3. `repository_id`와 등록 저장소 경로는 지금과 같이 동작한다
- covers: I2, I3, F3, F9
- check: tests/test_project_context_service.py, tests/test_mcp_explore_project.py, tests/test_project_context_scope.py
- evidence: tests/test_project_context_live_repository.py `test_repository_id_skips_live_reading`, `test_path_inside_registered_repository_keeps_registered_path`, `test_path_inside_registered_repository_without_binding_keeps_scope_error`. 기존 tests/test_project_context_service.py와 tests/test_project_context_scope.py는 바뀌지 않았고 bake-verify.log "4078 passed, 22 skipped, 1 warning"에서 통과했다.

기존 테스트를 고치지 않고 통과한다. 새 사례: `repository_id`와 `cwd`를 함께 주면 등록 저장소 결과가 나오고 git 읽기는 불리지 않는다. 등록 저장소 안의 경로는 투영이 없을 때 `code_index_unavailable`을, binding이 없을 때 `scope_required`를 지금처럼 낸다. `project_path`와 `repository_id`를 함께 주면 지금처럼 거절된다.

### A4. 호출 뒤 저장소와 Graph Home의 바이트가 그대로다
- covers: I1, F8
- check: tests/test_project_context_live_repository.py
- evidence: tests/test_project_context_live_repository.py `test_live_reading_leaves_repository_and_graph_home_unchanged`, `test_repository_without_commits_has_null_revision`, tests/test_live_repository_reader.py `test_reader_never_runs_writing_git_commands

`.git` 폴더를 포함한 저장소 전체와 Graph Home 폴더의 파일 바이트와 목록이 호출 전후에 같다. commit 안 된 변경이 있는 파일을 읽어도 같고, 그 증거의 `revision`은 `git:<HEAD>`, 이유에 `working_tree`가 있다. commit이 없는 저장소에서는 `revision`이 null이다.

### A5. 파일 목록은 git에서 오고 무시된 폴더와 symlink를 읽지 않는다
- covers: D4, F7
- check: tests/test_live_repository_reader.py
- evidence: tests/test_live_repository_reader.py `test_search_reads_files_from_git_and_skips_ignored_symlinks_and_large_files

`.gitignore`에 든 `.venv` 아래 저장소 밖을 가리키는 symlink, 추적되는 symlink, 512 KiB를 넘는 파일, 문법 오류 `.py`가 있어도 예외 없이 결과가 나온다. symlink와 큰 파일은 결과에 없고 `code_live_files_skipped` 경고가 하나 있다. 문법 오류 파일은 줄 위치 증거로 나온다. 무시되지 않은 새 파일(추적 전)은 결과에 나올 수 있다.

### A6. 상한에 걸리면 자른 결과와 경고를 내고, 낱말이 없으면 빈 결과로 성공한다
- covers: I7, F5, F6, D5
- check: tests/test_live_repository_reader.py
- evidence: tests/test_live_repository_reader.py `test_search_caps_parsed_files_and_reports_truncation`, `test_search_stops_on_git_timeout_and_returns_partial_result`, `test_search_without_terms_or_matches_succeeds_with_warnings`, `test_extract_terms_keeps_first_eight_and_drops_stop_words`, `test_line_match_files_do_not_take_the_parse_budget_of_source_files

후보 파일 60개를 만들면 파싱한 파일이 50개 이하이고 `code_live_read_truncated` 경고와 `partial` freshness가 나온다. git 실행을 시간 초과로 바꾼 가짜 runner에서도 그때까지의 결과와 같은 경고가 나온다. 낱말이 9개 이상이면 앞의 8개만 쓴다. `task="??"`는 `code_live_no_terms`, 어디에도 없는 낱말은 `code_live_no_match` 경고로 성공한다.

### A7. Vault는 vault-map과 binding으로만 정하고, 없으면 binding이 null이다
- covers: D7, I4, I6, F4
- check: tests/test_project_context_live_repository.py, tests/test_project_context_models.py
- evidence: tests/test_project_context_live_repository.py `test_no_vault_leaves_binding_null_and_reads_no_vault`, `test_zero_registered_repositories_return_live_code_evidence`, tests/test_project_context_models.py `test_project_context_allows_no_binding_but_binding_still_needs_vaults

`vault-map.json`에 그 저장소 프로젝트가 있으면 그 Vault 근거가 붙고 `binding.vault_ids`가 그 Vault다. 없으면 `binding`이 null, `vault_evidence`가 비고, `project_vault_scope_unresolved` 경고가 나오며, 활성 Vault를 읽는 가짜 서비스가 한 번도 불리지 않는다. `ProjectBinding(vault_ids=())`은 지금처럼 `ValueError`다.

### A8. `cwd` 인자를 받고 범위 인자의 우선순위가 D2, D8대로다
- covers: D2, D8
- check: tests/test_mcp_explore_project.py, tests/test_project_context_live_repository.py
- evidence: tests/test_mcp_explore_project.py `test_registered_explore_project_tool_takes_cwd`, `test_parse_explore_project_input_rejects_empty_cwd`, `test_parse_explore_project_input_accepts_cwd_with_any_scope`, tests/test_project_context_live_repository.py `test_project_path_wins_over_cwd

MCP 도구 서명에 `cwd`가 있다. `project_path`와 `cwd`가 서로 다른 git 저장소면 `project_path` 쪽 결과가 나온다. 빈 문자열 `cwd`는 `invalid_arguments`다. 등록 저장소 밖의 `project_path`는 더 이상 `unregistered_project_path`를 내지 않는다.

### A9. 인자가 없으면 D11의 순서로 저장소를 고른다
- covers: D11, F2
- check: tests/test_project_context_service.py, tests/test_project_context_live_repository.py
- evidence: tests/test_project_context_live_repository.py `test_no_arguments_prefer_the_single_bound_registered_repository`, `test_no_arguments_without_registered_repository_read_the_working_folder`, `test_no_arguments_outside_git_raise_not_a_git_repository

binding이 있는 등록 저장소가 하나면 서버 작업 폴더와 관계없이 그것을 쓴다(기존 테스트). 0개이고 서버 작업 폴더가 git 안이면 그 저장소를 읽는다. 0개이고 git 밖이면 `not_a_git_repository`다. 서버 작업 폴더는 테스트에서 주입하고 프로세스 cwd를 바꾸지 않는다.

### A10. 안내문, FEATURES, TODO가 새 동작을 적는다
- covers: D10
- check: 수동: `mcp_server.py` 안내문, `mcp_prompts.py`의 Implementation Context 프롬프트, `docs/FEATURES.md`의 `explore_project` 세 곳, `docs/TODO.md` 결정5 항목을 읽어 "등록 필요"라는 문장이 없고 `cwd`와 git 저장소 읽기가 적혀 있으며, 등록 스캐너의 `.venv` symlink 문제가 후속 항목으로 있는지 본다
- evidence: 수동: 사람이 `mcp_server.py` 안내문, `mcp_prompts.py:147`, `docs/FEATURES.md`의 `explore_project` 세 곳, `docs/TODO.md`의 결정5와 Follow-up 항목을 읽는다. 리뷰에서 diff를 읽었을 때 "등록 필요" 문장은 없었고 `cwd`와 git 읽기가 적혀 있었다.

### A11. 바뀐 파일이 §4.5 목록 안에 있고 push와 PR이 없다
- covers: D3, D10
- check: 수동: change 끝에서 base와의 차이 파일 목록을 §4.5와 대조하고, 사실 추출기, vault-builder, `src/vault_graph/project/code/source_scanning.py`, `repository_catalog.py`가 없는지, 원격 branch와 PR이 새로 생기지 않았는지 본다
- evidence: 수동: 사람이 `git diff --stat main...HEAD`를 §4.5와 대조한다. 이 change에서 §4.5 밖 파일은 `mcp_service_factory.py`와 `tests/test_mcp_tools.py`이고, 둘 다 구현에 필요하다. 앞의 commit 두 개는 다른 spec 것이다. 금지 파일 변경은 없고 upstream도 없다.

### A12. 이 저장소에서 실제 호출의 git 읽기가 10초 안에 코드 증거를 내고 전체 검증이 통과한다
- covers: D1, D3, I7
- check: 수동: 등록 저장소가 없는 Graph Home으로 이 저장소 worktree를 `cwd`로 `explore_project(task="resolve repository for explore_project in ProjectContextService")`를 부르고, git 읽기 시간, 전체 호출 시간, 코드 증거를 본 뒤 저장소의 전체 검증 명령을 실행한다
- evidence: 수동: 사람이 등록 저장소가 없는 Graph Home으로 worktree를 `cwd`로 `explore_project(task="resolve repository for explore_project in ProjectContextService")`를 부른다. 리뷰에서 live reader만 실행했을 때 1.06 s가 걸렸고 첫 증거가 `ProjectContextService._resolve_repository`였다. 구현자가 실제 Graph Home으로 잰 값은 git 읽기 1.11 s, 전체 호출 22.2 s(cold, 기록만 한다)다. bake-verify.log는 "4078 passed"이고 `tests/test_project_context_import_boundaries.py`도 통과했다.

`ProjectContextService` 심볼 증거가 나오고 git 읽기가 10초 안에 끝난다. 전체 호출 시간은 기록만 한다. 그 시간은 대부분 기존 Vault context pack이 쓰고, 등록 저장소에서도 같다. 2026-11-25 리뷰 뒤 사람이 이 기준으로 고쳤다(처음 기준: task "explore_project repository resolution", 전체 호출 10초). 전체 검증 명령이 통과한다. `tests/test_project_context_import_boundaries.py`도 통과한다.

## 9. Open decisions

### O1. 등록되지 않은 저장소의 코드 결과를 어떻게 만들까?
- decides: D3, D5, D6

배경: 등록 저장소가 없으면 미리 만든 코드 색인이 없다. 이 저장소 전체를 색인하는 데 약 25초와 97 MB가 들고, 지금 색인 도구는 `.venv`의 symlink 때문에 이 저장소에서 멈춘다. 세 가지 길이 있다.

- 옵션1(추천): 호출마다 git으로 후보 파일을 골라 그 파일만 메모리에서 파싱한다. 함수·클래스 이름, 파일, 줄 범위가 나오고 몇 초 안에 끝난다. 아무것도 저장하지 않는다. 영향 범위와 관련 테스트는 나오지 않는다.
- 옵션2: 첫 호출 때 저장소를 색인해 Graph Home에 두고 지금의 조회와 영향 추적을 쓴다. 첫 호출이 약 25초 걸리고 MCP 호출이 Graph Home에 97 MB를 쓴다. git 목록을 쓰는 새 스캐너도 만들어야 한다.
- 옵션3: `git grep` 줄 일치만 낸다. 가장 빠르고 모든 언어에 되지만 함수 이름과 범위가 없다.

추천 이유: 에이전트가 맨 먼저 부르는 도구라 첫 호출부터 빨라야 하고, 나중 코드 앵커가 쓸 함수 이름과 줄 범위도 있어야 한다. 영향 추적이 필요한 사람은 저장소를 등록하면 지금처럼 받는다.

답에 따라 바뀌는 것: 옵션1이면 지금 spec대로다. 옵션2면 D3이 바뀌고 D5, D6 대신 색인 세대 관리, 첫 호출 대기 안내, Graph Home 쓰기 허용이 들어간다. 옵션3이면 D5의 파싱 단계가 빠지고 D6의 심볼 증거가 줄 위치 증거만 남는다.

### O2. 인자 없이 부르고 등록 저장소도 하나뿐일 때 어느 저장소를 볼까?
- decides: D11

배경: 지금은 `project_path`도 `repository_id`도 없으면 binding이 있는 등록 저장소가 하나일 때 그것을 쓰고, 아니면 실패한다. 이번 change 뒤에는 서버 작업 폴더의 git 저장소도 후보가 된다. 사용자 Mac처럼 등록 저장소가 0개면 어느 답이든 서버 작업 폴더를 본다. 차이는 등록 저장소가 하나 있을 때만 난다.

- 옵션A(추천): 등록 저장소 하나를 먼저 쓰고, 없을 때 서버 작업 폴더를 본다. 지금 동작과 기존 테스트가 그대로다. 대신 등록 저장소가 하나 있는 사람이 다른 저장소에서 작업하면, `cwd`를 넘기지 않은 호출은 등록 저장소 결과를 받는다.
- 옵션B: 서버 작업 폴더를 먼저 보고, git 밖일 때만 등록 저장소 하나로 간다. "cwd의 저장소"라는 결정 문장에 더 가깝지만, 인자 없는 호출의 결과가 지금과 달라지고 기존 서비스 테스트 하나를 고쳐야 한다.
- 옵션C: 서버 작업 폴더만 보고 git 밖이면 오류를 낸다. 결정 원문("cwd가 git 밖이면 오류")을 글자 그대로 따르지만 등록 저장소 하나로 쓰던 사람의 인자 없는 호출이 실패할 수 있다.

추천 이유: MCP 안내문이 `cwd`를 넘기라고 말하게 바꾸면 인자 없는 호출은 드물고, 그 드문 경우에 지금 쓰던 사람의 결과를 바꾸지 않는 편이 안전하다.

답에 따라 바뀌는 것: 옵션A면 지금 spec대로다. 옵션B면 D11의 순서가 뒤집히고 인자 없는 호출의 수용 기준과 기존 서비스 테스트 하나가 바뀐다. 옵션C면 D11에서 등록 저장소 단계가 빠지고, 인자 없이 git 밖에서 부르면 늘 오류가 된다.
