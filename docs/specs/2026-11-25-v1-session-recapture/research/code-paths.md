# 다시 수집 경로의 코드 확인 결과

확인일: 2026-11-25. vg 코드: 커밋 `fd21e3f`. Vault 도구: `~/vaults/vault-graph/tools/wiki/lib/session_capture.py`, 실행기: `~/.claude/vault-builder/vault_hooks.py`(둘 다 이 날 작업 트리에서 읽음).

## vg 쪽

### X1. `vg session export --recapture`는 v1 part가 있는 세션만 고르지 못한다
- source: `src/vault_graph/interface/cli/session_commands.py:81-117@fd21e3f`

세션 고르기는 `--session ID`, `--since DATE`, `--all` 중 하나뿐이다. `--all`은 프로젝트 폴더의 모든 원본 세션을 내보내고 `--recapture`면 세션마다 실행기를 돌린다. 이미 v2 part만 있는 세션도 다시 쓰므로 같은 교환이 담긴 part가 하나 더 생긴다.

### X2. `recapture_session`은 정규화 파일 첫 줄의 `cwd`와 `newest`로 훅 JSON을 만든다
- source: `src/vault_graph/interface/composition/adapters/session_capture_runner.py:106-129,223-233@fd21e3f`

훅 JSON은 `session_id`, `transcript_path`, `hook_event_name`, `cwd`다. `cwd`는 정규화 파일 첫 줄 값 그대로이고, 폴더가 지금 있는지 보지 않는다. `newest`인 세션은 `PreCompact`, 아니면 `SessionEnd`를 넣는다. 실행기 인자는 `--normalized <파일> --rerender`이고 시간 제한은 세션마다 120초(`RECAPTURE_TIMEOUT_S`)다.

### X3. 실행기 결과에서 vg는 `status`, `vault`, `path`만 읽는다
- source: `src/vault_graph/interface/composition/adapters/vault_capture_cli.py:23-39,98-108@fd21e3f`

`CaptureOutcome`에는 `exchange_count` 필드가 없다. `_result`는 stdout 마지막 JSON 줄에서 세 값만 꺼낸다.

### X4. 정규화는 프로젝트 폴더의 가장 최근 세션만 끝나지 않은 것으로 본다
- source: `src/vault_graph/interface/composition/adapters/session_export_files.py:98-121,163-167@fd21e3f`, `docs/contracts/vg-session-jsonl-v1.md` §3.1

`find_claude_code_sessions`는 폴더마다 main 원본 수정 시각이 가장 늦은 세션에 `newest=True`를 단다. `export_claude_code_session`은 `session_ended=not newest`로 정규화한다. `newest`면 마지막 main 교환이 `closed: false`로 남는다. 같은 세션 id가 두 프로젝트 폴더에 있으면 그 세션을 목록에서 뺀다.

### X5. 색인은 겹친 v1 교환과 중복 v2 교환을 빼고 Vault 파일은 건드리지 않는다
- source: `src/vault_graph/indexing/ingestion/session_group.py:1-16@fd21e3f`, `src/vault_graph/indexing/ingestion/session_exchange_v2_chunker.py:412-462@fd21e3f`

같은 (`agent`, `session_id`) 묶음에서 같은 v2 교환이 두 파일에 있으면 통째로 담은 사본 중 part 번호가 낮은 것 하나만 색인한다. v2 교환과 같은 범위(main 또는 같은 subagent)에서 시간이 겹치는 v1 교환은 색인에서 뺀다. 색인 행만 바뀐다.

### X6. 사실 작업자는 `vg:exchange` 메타 줄이 있는 교환만 처리한다
- source: `src/vault_graph/interface/composition/adapters/fact_worker.py:79,363-374@fd21e3f`

`_exchanges`는 교환 제목 바로 아래 줄이 `<!-- vg:exchange ... id=... -->`인 곳만 교환으로 센다. v1 part에는 이 줄이 없어 사실이 0개다.

### X7. 모듈 배치 규칙: 세션 순수 코드는 M19, 파일과 실행기는 adapter
- source: `docs/ARCHITECTURE.md` §1 소유권 표 M19 행, §3.1 M19 행, §4 세션 수집 행

M19 `operation/sessions/`는 파일을 읽거나 쓰지 않는 순수 코드이고 M01만 가져온다. 어떤 기능 영역도 M19를 가져오지 않고 `interface/`만 부른다. 파일 읽기·쓰기와 실행기 호출은 `interface/composition/adapters/`가 한다. 가져오기 방향은 `tests/test_feature_import_direction.py`가 검사한다.

## Vault 도구와 실행기

### X8. `--rerender`는 가장 높은 part 다음 번호로 새 파일만 쓴다
- source: `~/vaults/vault-graph/tools/wiki/lib/session_capture.py:1178-1308`

`capture_normalized`는 `rerender`면 커서를 무시하고 `highest_part + 1`에 닫힌 교환 전부를 쓴다. 기존 파일은 바꾸지 않는다. 결과 JSON의 `vault`는 Vault 이름이고, `written`이면 `schema`, `part`, `exchange_count`가 더해진다. 새 part frontmatter에는 `first_exchange_id`, `last_exchange_id`, `first_turn_at`, `last_turn_at`이 있다. 상태는 `written`, `no-new-turns`, `skipped` 중 하나다.

### X9. Vault는 턴 없는 교환을 건너뛰고 처음 열린 교환에서 멈춘다
- source: `~/vaults/vault-graph/tools/wiki/lib/session_capture.py:978-1033`

`select_part_exchanges`는 쓸 턴이 없는 교환은 넘기고, 턴이 있는데 닫히지 않은 교환을 만나면 거기서 끝낸다. 그래서 `exchange_count`는 "처음 열린 교환 앞까지, 턴이 하나 이상인 교환 수"다.

### X10. 새 part의 `cwd`와 Vault 선택은 훅 JSON `cwd`를 먼저 따른다
- source: `~/vaults/vault-graph/tools/wiki/lib/session_capture.py:1214-1227,1267`, `~/.claude/vault-builder/vault_hooks.py:14-20,243-269`

Vault 도구는 `--cwd` 값, 훅 JSON `cwd`, 정규화 파일의 세션 `cwd` 순으로 하나를 고르고, 그 값으로 Vault를 고르며 frontmatter `cwd`에도 적는다. 실행기는 `vault-map.json`에서 cwd 프로젝트에 연결된 role project Vault 하나를 고른다. 하나가 아니면 쓰지 않는다.

### X11. v1 part는 frontmatter `schema: vault-session/v1`과 턴 시각 범위를 가진다
- source: `~/vaults/vault-graph/raw/sessions/claude-code/2026-11-07-ae647dc5-0913-4815-acd3-87d60f77b9bb-part7.md:1-17`, 같은 폴더에서 `^schema: vault-session/v1` 검색

v1 frontmatter에는 `agent`, `session_id`, `part`, `first_turn_at`, `last_turn_at`, `cwd`가 있고 교환 메타 줄과 `exchange_count`는 없다. vault-graph Vault에서 이 schema 줄이 있는 파일은 36개다.
