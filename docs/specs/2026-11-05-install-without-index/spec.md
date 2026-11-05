# Spec: 설치할 때 인덱싱하지 않기

## 1. Problem

설치 명령이 마지막 단계에서 vault-map.json의 모든 Vault를 색인한다. 색인이 끝나야 설치 명령이 끝나므로, 세션 원문이 많은 Vault가 있으면 설치가 수십 분 걸린다.

근거 (파일 경로는 저장소 루트 기준, 저장소는 `$HOME/workspace/vault-graph.bake-worktrees/install-command`, 브랜치 `feat/jh/install-no-index`, origin/main 0ba6149 / v0.4.1):

1. `scripts/install.sh:370`은 `"${VG}" setup --agent claude --mcp`를 실행한다. 안내 문구(`scripts/install.sh:368`)도 "It indexes every Vault"라고 적는다.
2. `vg setup`은 `--vault`가 없으면 vault-map.json의 Vault마다 `SetupService.setup`을 부른다 (`src/vault_graph/interface/cli/main.py:463-485`).
3. `SetupService.setup`은 dry run이 아니면 항상 `index_service.run_apply`를 실행한다 (`src/vault_graph/operation/runtime/setup_service.py:108-122`). 색인을 건너뛸 방법이 없다.
4. 측정값 (brief, 이번 세션): 사용자 Vault 사본 6개에 대한 첫 `vg setup`이 47분 넘게 걸렸다. sgp-981-app에서는 `raw/sessions/` 세션 원문이 조각 18,506개 중 18,108개(98%)였다. 세션 원문이 없는 Vault는 몇 초에서 몇 분이면 끝난다.
5. README 설치 절(`README.md:31-49`)도 설치 명령이 첫 색인을 실행한다고 적고, 6개 Vault에 약 14분이 걸린다고 적는다. 4번의 측정과 맞지 않는다.

확인 방법: 위 파일을 직접 읽었다. 4번은 brief에 적힌 측정값이고 이번 작성에서 다시 재지 않았다.

## 2. Intent

사용자 요청: "지금 vault-graph 설치명령을 기본으로 인덱싱을 진행하지 않는 걸로 하고, 별도로 쉽게 인덱싱을 하는 과정을 추가하는 걸로 기능을 추가해야겠어."

변경 뒤에 참이어야 하는 것:

1. 설치 명령은 색인을 하지 않고 끝난다. 설치 중에 색인을 켜는 옵션도 두지 않는다 (사용자 선택).
2. 색인은 사용자가 따로 실행한다. 명령은 이미 있는 `vg index --all-vaults`이고, 새 명령은 만들지 않는다 (사용자 선택).
3. 사용자는 설치 출력과 README만 보고 그 명령을 찾아 실행할 수 있다 (사용자 선택).
4. 색인 전에도 설치는 성공한 상태다. MCP 서버는 등록되어 켜지고, 색인이 없다는 안내를 낸다 [가정].
5. 이유: 설치는 빨리 끝나야 하고, 오래 걸리는 첫 색인은 사용자가 시점을 골라 돌려야 한다 [가정: 47분 측정에서 추론].

## 3. Non-goals

1. 색인을 빠르게 만드는 일.
2. `raw/sessions/` 세션 원문을 색인 범위에서 빼는 일.
3. 새 색인 명령이나 설치 명령의 색인 옵션을 만드는 일.
4. 옵션 없는 `vg setup`의 동작을 바꾸는 일. 계속 색인한다.
5. MCP 도구와 리소스가 내는 "Run `vg index`" 안내 문구를 바꾸는 일. 이 문구를 고칠지는 §9 질문2에서 정한다.
6. 색인이 없을 때 MCP `remember`가 시작하는 백그라운드 색인을 막거나 바꾸는 일 (§6 참고).
7. vault-builder 저장소의 훅 실행기(`vault_hooks.py`)를 바꾸는 일.

## 4. Design

### 4.1 바꾸는 것

1. `vg setup` 옵션 `--index/--no-index` (기본 `--index`).
   - 파일: `src/vault_graph/interface/cli/main.py` `setup` (현재 444-499행).
   - `--no-index`를 주면 Vault마다 만드는 `SetupRequest`에 `run_index=False`를 넘긴다. 나머지 흐름(지도 Vault 등록 `_register_map_vault`, MCP 등록, 훅 상태 출력)은 그대로다.
   - 도움말: 색인 없이 Vault 등록, Data Home 초기화, MCP 등록만 하고, 색인은 나중에 `vg index --all-vaults`로 하라고 적는다.
2. `SetupRequest`에 필드 `run_index: bool = True`를 더한다.
   - 파일: `src/vault_graph/operation/runtime/setup_service.py` `SetupRequest`, `SetupService.setup`, `_setup_recovery_hint`.
   - `run_index`가 False이면 `setup_service.py:108-122`의 색인 블록을 건너뛴다. `index_report`는 None으로 남는다.
   - MCP 등록 조건 `index_ready`(`setup_service.py:133`)는 `index_report is None`이면 이미 참이므로 바꾸지 않는다. 그래서 색인 없이도 MCP가 등록된다.
   - `SetupReport`: `indexed=False`, `ready=False`. `recovery_hint`는 색인을 건너뛰었다는 뜻과 `vg index --all-vaults`를 적는다. dry run일 때의 기존 안내가 먼저다.
3. 설치 명령 `scripts/install.sh`.
   - 5단계를 `"${VG}" setup --agent claude --mcp --no-index`로 바꾼다 (현재 370행). 그 앞 안내(368-369행)에서 색인과 모델 내려받기 문장을 지운다.
   - 머리 주석 5번(18행)과 dry run 안내(352행)를 같은 명령으로 고친다.
   - 성공 뒤 마지막 줄들(현재 375-377행 자리): Claude Code 재시작과 `/mcp` 확인 안내 다음에, 색인을 하지 않았다는 문장, 색인 명령 한 줄, 첫 실행은 임베딩 모델(약 135 MB)을 내려받고 세션 원문이 많은 Vault에서는 수십 분 걸릴 수 있다는 문장을 출력한다.
   - 색인 명령 줄: `command -v vg`가 `${VG}`와 같은 파일이면 `vg index --all-vaults`, 아니면 `${VG} index --all-vaults`.
   - `vg setup` 전에 `"${VG}" setup --help` 출력에 `--no-index`가 있는지 본다. 없으면 설치된 `vg` 경로, 이 `vg`가 이 설치 명령보다 옛 버전이라는 것, 최신 태그를 쓰는 방법(`VAULT_GRAPH_REF`를 지우거나 새 태그 지정), 직접 `vg setup --agent claude --mcp`를 돌리면 색인까지 한다는 것을 출력하고 0이 아닌 코드로 멈춘다 (§9 질문1 답).
4. 세션 시작 회상의 안내 문구.
   - 파일: `src/vault_graph/context/pack/recall.py:172`, `:175`.
   - "Run `vg index`."를 "Run `vg index --all-vaults`."로 바꾼다. 옵션 없는 `vg index`는 활성 Vault 하나만 색인하기 때문이다 (`main.py:614-615`, `vault_catalog.py:142-144`).
5. README 설치 절과 Quick Start.
   - `README.md:31-49`: 설치 명령이 색인하지 않는다고 고치고, 설치 뒤 `vg index --all-vaults`를 실행하라는 단락을 더한다. 걸리는 시간 문장(46-48행)은 이 단락으로 옮기고, 세션 원문이 많으면 수십 분 걸린다는 문장과 47분 측정을 더한다.
   - `README.md:88-98`: `--no-index`를 한 줄로 설명한다.
   - `README.md:202`: 모델을 처음 내려받는 명령에 "`vg setup --no-index`는 내려받지 않는다"를 더한다.
6. 테스트: `tests/test_install_script.py`, `tests/test_cli_setup.py`, 회상 문구 테스트, MCP 무색인 테스트 (§8).

### 4.2 바꾸지 않는 것 (코드로 확인함)

brief 가정 2: 색인이 없을 때 MCP 서버.

1. `--no-index` setup이 남기는 상태는 `vg init`과 같다. Data Home 초기화(`setup_service.py:98`)와 카탈로그 저장(`setup_service.py:177`, 지도 Vault 추가는 `main.py:533-548`)만 하고, 메타데이터 SQLite 파일은 만들지 않는다. 그 파일은 색인 팩토리가 `initialize_store=True`로 열 때 만든다 (`setup_service.py:109-114`, `sqlite_metadata_store.py:137-145`).
2. MCP 서버는 시작할 때 저장소를 열기만 하고 읽지 않는다. `create_mcp_server`가 `open_read_only`를 부르고(`mcp_server.py:80-81`), 여기서 만드는 메타데이터 저장소, 키워드 색인, 임베딩 객체는 생성자에서 파일을 읽지 않는다 (`sqlite_metadata_store.py:137-145`, `sqlite_keyword_index.py:60-61`, `text_embeddings.py:136-161`, 기본 lazy load는 `index_service.py:149`). Data Home이 초기화되어 있으면 `_catalog`의 `require_initialized`(`read_only_service_factory.py:431-435`)도 통과한다.
3. 테스트 근거: `tests/test_mcp_current_context_resource.py:65-77`은 `vg init`만 한 Data Home에서 `create_mcp_server`가 성공하고, 리소스 읽기가 `metadata_unavailable` 오류와 "Run vg index" 안내를 돌려주는 것을 확인한다.
4. 도구별 안내: 검색 계열은 `metadata_unavailable` 또는 `keyword_index_unavailable`에 "Run `vg index`."를 붙인다 (`retrieval_service.py:311-316`, `mcp_errors.py:108-114`). 기억 계열은 `recovery_hint`로 "Run vg index, then vg status for the selected Vault."를 준다 (`mcp_tools.py:1279`). 프로젝트 범위 경고는 "is not indexed and returned no results. Run `vg index`."다 (`query_scope_resolution.py:157-163`).
5. 결론: 가정 2는 맞다. 서버는 켜지고, 도구는 실패 대신 색인 안내를 돌려준다. 다만 안내가 `--all-vaults` 없이 `vg index`라고 적는다 (§9 질문2).
6. 확인하지 못한 것: Chroma 벡터 저장소 생성자(`vector_store_adapter.py:34-51`)가 없는 폴더를 read-only로 열 때 예외를 내지 않는지는 외부 패키지 코드라 읽지 않았다. 위 3번 테스트가 같은 조건에서 통과하므로 문제없다고 본다 (§7).

brief 가정 3: 색인이 없을 때 세션 시작 회상.

1. 갱신 단계는 조용히 건너뛴다. `refresh_linked_vaults`는 색인된 연결 Vault만 고르고, 없으면 이유 없이 `skipped`를 돌려준다 (`recall_index_refresh.py:124-126`). 이유가 없으면 경고 줄도 없다 (`recall_index_refresh.py:106-107`). 메타데이터 파일이 없으면 `is_indexed`는 예외 없이 False다 (`read_only_service_factory.py:514-517`). 그래서 백그라운드 색인도 시작하지 않는다.
2. 회상은 넘김(handoff)으로 끝난다. 연결 Vault가 모두 색인되지 않았으면 `recall`이 "No index for Vault <id>. Run `vg index`."로 넘김을 돌려준다 (`recall.py:170-172`). 훅 명령은 이 문장을 stderr에 `vg hook session-start: ` 머리말과 함께 한 줄 쓰고 종료 코드 3으로 끝난다 (`hook_commands.py:143-144`, `:316-318`). 일부 Vault만 색인되지 않았으면 경고 한 줄을 stderr에 쓰고 회상은 계속한다 (`recall.py:174-176`, `hook_commands.py:141-142`).
3. vault-builder 훅 실행기는 vg의 stderr를 그대로 옮기고, 종료 코드가 0이 아니면 "vg hook session-start ended with 3; using recall.sh." 한 줄을 더 쓴 뒤 `recall.sh` 출력을 쓴다. 실행기 자신은 항상 0으로 끝난다 (vault-builder 저장소 `tools/vault_migration/assets/vault-hooks/vault_hooks.py:131-149`, 머리 주석 6-10행).
4. 결론: 세션마다 오류로 멈추지는 않는다. stderr에 두 줄이 남고 회상은 `recall.sh`로 대신한다. 바꿀 것은 안내 명령 하나다 (4.1의 4번).

## 5. Decisions

| 번호 | 결정 | 이유 | 누가 |
| --- | --- | --- | --- |
| 결정1 | 색인 명령은 기존 `vg index --all-vaults`를 쓴다. 새 명령은 없다. | 이미 등록된 모든 Vault를 색인하는 명령이 있다 (`main.py:587`, `:609-610`). | 사용자 |
| 결정2 | 설치 명령에는 색인 옵션을 두지 않는다. 설치 명령은 색인하지 않는다. | 사용자 답변. | 사용자 |
| 결정3 | `vg setup`에 `--index/--no-index`를 더하고 기본은 `--index`다. 설치 명령만 `--no-index`를 넘긴다. | 옵션 없는 `vg setup`을 부르는 README 절차와 다른 호출자가 그대로 동작한다. SPEC §5(`docs/SPEC.md:132`)는 기존 CLI 인자와 응답 형식을 유지하라고 한다. 옵션 추가는 기존 인자를 바꾸지 않는다. | [가정] brief 가정 1 |
| 결정4 | 색인을 건너뛰어도 MCP를 등록한다. | 서버가 색인 없이 켜지고 안내를 돌려주는 것을 확인했다 (§4.2). 색인 뒤에는 서버가 활성 세대를 매번 확인해 다시 열므로 Claude Code를 다시 켤 필요가 없다 (`mcp_service_factory.py:61-69`). | [가정] |
| 결정5 | `--no-index` setup의 출력은 `indexed: False`, `ready: False`와 `recovery_hint` 한 줄이다. 새 출력 필드는 없다. | 기존 필드로 상태를 정확히 말할 수 있다 (`main.py:551-575`). Vault마다 같은 안내가 반복되지만 출력 형식을 바꾸지 않는다. | [가정] |
| 결정6 | 회상 안내를 `vg index --all-vaults`로 바꾼다 (`recall.py:172`, `:175`). | 옵션 없는 `vg index`는 활성 Vault 하나만 색인한다 (`vault_catalog.py:142-144`). 설치 뒤 Vault가 여럿이면 안내대로 해도 회상이 돌아오지 않는다. | [가정] brief 가정 3 |
| 결정7 | 설치 출력의 색인 명령은 `vg`가 PATH에서 설치한 파일을 가리키면 짧게, 아니면 전체 경로로 쓴다. | 사용자가 그대로 복사해 실행할 수 있어야 한다. | [가정] brief 가정 4 |
| 결정8 | 설치 출력 순서는 재시작 안내 다음에 색인 안내다. 색인 안내가 맨 끝이다. | 터미널에서 마지막 줄이 가장 눈에 띈다. 색인은 Claude Code가 켜져 있어도 돌릴 수 있다 (결정4의 근거). | [가정] |
| 결정9 | 색인이 없을 때 MCP `remember`(basis stated)가 그 Vault 전체를 백그라운드로 색인하는 동작은 그대로 둔다. | brief가 받아들일 수 있다고 적었다. 바꾸려면 MCP 쓰기 흐름을 건드려야 해서 범위를 넘는다. | [가정] brief |

## 6. Failure and boundary behavior

| 상황 | 동작 |
| --- | --- |
| 설치 명령, Vault가 처음 설치됨 | `vg setup --agent claude --mcp --no-index`가 Vault 등록, Data Home 초기화, MCP 등록을 하고 0으로 끝난다. 임베딩 모델을 내려받지 않는다. 마지막 줄에 색인 안내가 나온다. |
| 설치 명령을 다시 실행, 이미 색인된 Data Home | 색인을 건드리지 않는다. 기존 색인과 세션 시작 갱신은 그대로 동작한다. 색인 안내는 그래도 출력된다. |
| `vg setup --no-index --dry-run` | 기존 dry run과 같다. 아무것도 쓰지 않고, dry run 안내가 `recovery_hint`로 나온다. |
| `vg setup` (옵션 없음) | 지금과 같다. 색인하고, 색인이 실패하면 MCP 등록을 건너뛰고 0이 아닌 코드로 끝난다. |
| `--no-index`에서 한 Vault 등록이 실패 | 지금과 같다. 그 Vault는 `setup_failed:` 줄로 남고 나머지 Vault는 계속하며 끝 코드는 1이다 (`main.py:481-499`). 설치 명령은 기존 실패 안내를 출력한다. |
| 설치한 `vg`가 `--no-index`를 모름 (이 변경 전 태그를 설치) | 설치 명령이 `vg setup` 전에 도움말로 확인하고, 원인과 해결 방법을 출력한 뒤 0이 아닌 코드로 멈춘다 (§9 질문1 답). |
| 색인 전 MCP 도구 호출 | 서버는 켜져 있다. 검색 계열은 `metadata_unavailable` 또는 `keyword_index_unavailable` 오류와 "Run `vg index`." 문장, 기억 계열은 같은 코드와 `recovery_hint`를 돌려준다 (§4.2). |
| 색인 전 세션 시작 | 갱신은 조용히 건너뛰고 백그라운드 색인은 시작하지 않는다. stderr에 "No index for Vault <id>. Run `vg index --all-vaults`."와 실행기의 "using recall.sh" 줄이 남고, 회상은 `recall.sh` 출력으로 대신한다. |
| 일부 Vault만 색인됨 | 색인된 Vault로 회상하고, 색인되지 않은 Vault마다 "Vault <id> has no index. Run `vg index --all-vaults`." 경고 한 줄을 stderr에 쓴다. |
| 색인 전 MCP `remember` (basis stated, published) | 그 Vault 하나의 증분 색인을 MCP 서버 안 백그라운드 스레드에서 시작한다 (`mcp_memory_tools.py:305`, `mcp_service_factory.py:202-239`, `:249-269`). 이전 색인이 없으므로 그 Vault 전체를 색인한다. 세션 원문이 많으면 수십 분 걸릴 수 있다. 다른 Vault는 색인되지 않은 채 남는다. |
| `vg index --all-vaults`를 Claude Code가 켜진 채 실행 | 허용한다. 끝나면 MCP 도구는 다음 호출에서 새 세대를 읽는다 (`mcp_service_factory.py:61-69`). 회상은 다음 세션부터 나온다. |
| `vg index --all-vaults`가 중간에 실패하거나 중단됨 | 지금과 같다. 성공한 실행만 세대를 발행한다 (`main.py:629-633`). 다시 실행하면 된다. |
| `$HOME/.local/bin`이 PATH에 없음 | 설치 출력이 색인 명령을 `vg`의 전체 경로로 쓴다. |

## 7. What could be wrong

1. Chroma 벡터 저장소를 없는 폴더에서 read-only로 열 때 예외가 나지 않는다는 것은 외부 패키지 코드를 읽지 않고, `vg init` 상태의 테스트(`tests/test_mcp_current_context_resource.py:65-77`)가 통과한다는 사실에서 추론했다. A-4 테스트가 이를 직접 확인한다.
2. Claude Code가 종료 코드 0인 SessionStart 훅의 stderr를 사용자 화면에 보여 주는지 확인하지 않았다. 보여 준다면 색인 전 세션마다 두 줄이 보인다. 내용은 해야 할 명령이므로 문제로 보지 않는다.
3. vault-builder 훅 실행기 근거는 이 작업 폴더에 있는 vault-builder 사본에서 읽었다. 사용자 기계에 설치된 실행기 버전이 다르면 출력 줄이 다를 수 있다.
4. 색인 전 `remember`가 시작하는 백그라운드 색인이 임베딩 모델을 내려받는지는 확인하지 않았다 (`index_one_vault`는 `LocalIndexServiceFactory()`를 기본값으로 연다, `mcp_service_factory.py:255`). 내려받는다면 MCP 서버 프로세스가 약 135 MB를 받고 메모리를 많이 쓸 수 있다.
5. 새 릴리스 태그가 언제 만들어지는지 확인하지 않았다. 설치 명령은 `main`의 스크립트를 내려받고 최신 태그의 `vg`를 설치한다 (`scripts/install.sh:4`, `:168-186`). 이 변경이 `main`에 들어가고 새 태그가 나오기 전에는 스크립트가 `--no-index`를 모르는 `vg`에 그 옵션을 넘긴다 (§9 질문1).
6. 47분 측정은 brief의 값이고 다시 재지 않았다. README에 옮길 때 측정 조건(Vault 6개, 세션 원문 비율)을 같이 적는다.

## 8. Acceptance criteria

- A-1 (범위: 설치 명령은 색인하지 않음). `tests/test_install_script.py`의 설치 테스트에서 가짜 `vg` 호출 기록의 마지막 항목이 `vg setup --agent claude --mcp --no-index`이고, `vg index`로 시작하는 호출이 없다.
- A-2 (범위: 새 명령 없음). 설치 명령의 stdout 마지막 줄들에 색인을 하지 않았다는 문장과 `index --all-vaults`로 끝나는 명령 줄이 있고, 이 명령 줄이 stdout의 마지막 줄들 중 재시작 안내보다 뒤에 있다. `vg`에 새 하위 명령이 생기지 않는다 (`vg --help` 명령 목록이 변경 전과 같다).
- A-3 (PATH). `$HOME/.local/bin`이 PATH에 없을 때 색인 명령 줄은 설치한 `vg`의 전체 경로로 시작한다. PATH에 있을 때는 `vg index --all-vaults`다. 두 경우 모두 테스트한다.
- A-4 (MCP 등록, 색인 없음). vault-map.json에 Vault 둘을 둔 임시 환경에서 `vg setup --agent claude --mcp --no-index --mcp-config-path <임시 파일>`이 0으로 끝난다. 그 뒤: 카탈로그에 두 Vault가 있고, 메타데이터 SQLite 파일이 없고, MCP 설정 파일에 `vault-graph` 항목이 있고, 출력에 `indexed: False`와 `vg index --all-vaults`를 담은 `recovery_hint` 줄이 Vault마다 있다. 같은 Data Home에서 `create_mcp_server`가 예외 없이 끝나고, 검색 도구 호출은 `metadata_unavailable` 또는 `keyword_index_unavailable` 코드를 돌려준다.
- A-5 (호환: 옵션 없는 setup). 기존 `tests/test_cli_setup.py`와 `tests/test_cli_vault_map_setup_status.py`가 수정 없이 통과한다. 옵션 없는 `vg setup`은 계속 색인한다.
- A-6 (dry run). `vg setup --no-index --dry-run`은 Data Home에 아무것도 만들지 않는다. 설치 명령 `--dry-run`의 안내 문장에 `--no-index`가 들어간다.
- A-7 (회상 안내). 색인되지 않은 Vault만 연결된 폴더에서 `vg hook session-start`가 종료 코드 3으로 끝나고, stderr에 `vg index --all-vaults`가 들어 있다. 일부만 색인된 경우의 경고 줄에도 `vg index --all-vaults`가 들어 있다. 색인되지 않은 Vault만 연결된 경우에는 백그라운드 색인 프로세스가 시작되지 않는다 (`logs/session-start-index.pid`가 생기지 않는다). 일부만 색인된 경우에는 색인되지 않은 Vault를 백그라운드에서 색인하지 않는다. 색인된 Vault의 vector 확인은 기존대로 시작한다 (구현 중 수정, 기존 테스트 `test_no_change_still_starts_a_vector_check_so_a_killed_catch_up_is_retried`).
- A-8 (도움말). `vg setup --help` 출력에 `--no-index`와 `vg index --all-vaults`가 나온다.
- A-9 (README). README 설치 절이 설치 명령은 색인하지 않는다고 적고, `vg index --all-vaults` 명령, 첫 실행이 모델을 내려받는다는 것, 세션 원문이 많으면 수십 분 걸릴 수 있다는 것을 적는다. "runs the first index"처럼 설치 명령이 색인한다는 문장이 README에 남지 않는다.
- A-11 (옛 vg). 가짜 `vg`의 `setup --help`에 `--no-index`가 없으면 설치 명령은 `vg setup`을 부르지 않고 0이 아닌 코드로 끝나며, 출력에 설치된 `vg` 경로와 `VAULT_GRAPH_REF` 안내가 있다.
- A-10 (게이트). 저장소 테스트 전체와 린트가 통과한다.

## 9. Open decisions

### 질문1. 설치한 `vg`가 `--no-index`를 모르면 설치 명령은 어떻게 할 것인가?

- 정하는 것: 이 변경이 들어간 설치 스크립트가 이 변경 전 버전의 `vg`를 설치했을 때의 동작.
- 배경: 설치 명령은 `main`의 스크립트를 내려받고, 설치하는 `vg`는 최신 릴리스 태그다. 이 변경이 `main`에 들어간 뒤 새 태그가 나오기 전까지, 그리고 `VAULT_GRAPH_REF`로 옛 태그를 고른 경우에, 스크립트가 모르는 옵션을 넘겨 `vg setup`이 실패한다. 이때 vault-builder 설치는 이미 끝났고 vault-graph MCP 서버는 등록되지 않는다.
- 옵션1: 스크립트가 `vg setup --help`에 `--no-index`가 있는지 먼저 보고, 없으면 멈춘다. 멈출 때 설치된 `vg` 경로, 최신 태그를 쓰라는 안내, 직접 `vg setup --agent claude --mcp`를 돌리면 색인까지 한다는 안내를 출력한다. 잃는 것: 스크립트가 몇 줄 늘어난다.
- 옵션2: 확인하지 않는다. 변경을 합친 직후 새 태그를 만들어 틈을 줄인다. 잃는 것: 틈 동안과 옛 태그 설치에서 사용자는 "vg setup failed"와 알 수 없는 옵션 오류만 보고 원인을 모른다.
- 추천: 옵션1. 실패 원인을 사용자가 바로 알 수 있고, 설치 명령이 색인하지 않는다는 결정2도 지킨다.
- 답 (2026-11-05, 사용자): 옵션1.
- 바뀌는 것: 옵션1이면 §4.1의 3번에 확인 단계 하나와 §8에 테스트 하나(가짜 `vg`의 도움말에 옵션이 없을 때 멈추고 안내가 나옴)가 더해진다.

### 질문2. MCP 도구의 "Run `vg index`" 안내도 `vg index --all-vaults`로 바꿀 것인가?

- 정하는 것: 색인 전 MCP 도구가 에이전트에게 주는 안내 문구의 범위.
- 배경: 이 spec은 세션 시작 회상 문구만 바꾼다 (결정6). MCP 검색, 기억 도구, 프로젝트 범위 경고는 옵션 없는 `vg index`를 안내한다 (`retrieval_service.py:245`, `:313-315`, `mcp_tools.py:1279`, `query_scope_resolution.py:162`, `sqlite_keyword_index.py:66` 등). 옵션 없는 `vg index`는 활성 Vault 하나만 색인한다.
- 옵션1: 이번에는 바꾸지 않는다. 잃는 것: 에이전트가 안내대로 `vg index`를 돌리면 활성 Vault만 색인되고, 다른 Vault는 계속 비어 있다.
- 옵션2: 같은 변경에서 이 문구들을 모두 `vg index --all-vaults`로 바꾼다. 잃는 것: 범위가 검색과 MCP 계층의 오류 문구까지 넓어지고, 같은 문구를 확인하는 기존 테스트도 고쳐야 한다. CLI 검색 오류 문구도 함께 바뀐다.
- 답 (2026-11-05, 사용자): 옵션1. 이번에는 바꾸지 않는다.
- 추천: 옵션1. 이번 작업은 설치 흐름만 바꾸기로 했고, 사용자가 볼 설치 출력과 README에는 올바른 명령이 있다. 옵션 없는 `vg index`도 해롭지 않고 일부만 색인할 뿐이다. 문구 정리는 따로 하는 편이 리뷰하기 쉽다.
- 바뀌는 것: 옵션2이면 §3의 5번을 지우고, §4.1에 문구 변경 목록과 §8에 문구 테스트가 더해진다.
