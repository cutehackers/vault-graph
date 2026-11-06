# `vg-session-jsonl/1` 정규화 세션 형식과 export 계약

근거: `docs/specs/2026-11-05-session-memory-indexing/spec.md` §4.2.2, §4.2.3, §4.2.4, §6.
구현: `src/vault_graph/operation/sessions/`(M19, 순수 코드), `src/vault_graph/interface/composition/adapters/session_export_files.py`(파일 읽기·쓰기), `src/vault_graph/interface/cli/session_commands.py`(`vg session export`).

## 1. 파일 구조

- 파일 한 개에 세션 하나가 들어간다. UTF-8, 줄마다 JSON 객체 하나, 줄 끝은 `\n`이다.
- 첫 줄은 `session`이다. 이어서 `exchange` 줄과 그 교환의 `turn` 줄들이 순서대로 온다.
- 모든 줄의 첫 두 키는 `schema`(`"vg-session-jsonl/1"`)와 `kind`(`session`, `exchange`, `turn`)다.
- 결정성: 같은 원본 바이트와 같은 adapter 버전이면 같은 바이트가 나온다. 줄 안 키 순서는 아래 표의 순서로 고정이고, 맵 키는 이름순, 시각은 원본 값을 그대로 쓴다. 비 ASCII 문자는 이스케이프하지 않는다.

## 2. 줄 종류별 필드 (spec §4.2.2)

| kind | 필드 |
|---|---|
| session | `session_id`, `agent`(`claude-code`, `codex`), `agent_version`, `adapter`, `project`, `cwd`, `git_branch`, `git_commit`, `parent_session_id`, `title`(`{text, source}`. 에이전트가 만든 제목이고 `source`가 원본 레코드 종류다), `started_at`, `ended_at`, `source_paths`, `source_sha256` |
| exchange | `exchange_id`, `seq`, `agent_scope`(`main` 또는 `subagent:<agent_id>`), `subagent_type`, `parent_tool_use_id`, `started_at`, `ended_at`, `closed`, `prompt_source`, `tools`(이름 → 횟수), `files_touched`(이름순), `commands`(앞 160자, 가림 뒤), `errors`(개수), `outcome` |
| turn | `turn_id`, `parent_id`, `exchange_id`, `role`, `turn_kind`(`human`, `assistant_text`, `tool_only`, `notification`, `meta`, `compact_summary`), `at`, `agent_id`, `sidechain`, `text`(가림 뒤), `actions`: [{`tool`, `call_id`, `target`, `ok`, `error_head`(오류 첫 줄 200자, 가림 뒤)}] |

- `outcome`은 `answered`, `tool_error_unresolved`, `interrupted`, `open` 중 하나다. LLM 판단을 넣지 않는다.
- 넣지 않는 것: 도구 결과 본문, thinking·reasoning, attachment, api-request, 토큰 기록.
- 가림 규칙은 `vg-redact/1`(`operation/sessions/redact.py`)이다. 원본 사본(`raw/`)은 가리지 않는다.

### 2.1 `source_paths`와 `source_sha256`

- `source_paths`는 Claude Code 프로젝트 폴더(`<config>/projects/<key>/`) 기준 상대 경로다. 예: `<session_id>.jsonl`, `<session_id>/subagents/agent-<id>.jsonl`, `<session_id>/subagents/agent-<id>.meta.json`.
- export 폴더 안 위치는 이 경로에서 정해진다. `<session_id>.jsonl`은 `raw/claude-code/<session_id>/<session_id>.jsonl`, `<session_id>/subagents/<file>`은 `raw/claude-code/<session_id>/subagents/<file>`이다.
- 이 기준을 고른 이유: export와 `vg hook capture`가 같은 원본에서 같은 정규화 바이트를 내야 한다. export 폴더 경로를 넣으면 `--no-raw`나 export 설정 없는 수집에서 값이 달라진다.
- `source_sha256`은 원본 줄을 `(경로, 줄 번호)` 순으로 정렬해 `경로\0줄번호\0본문\n`을 이어 붙인 sha256이다. 원본이 자라면 값이 바뀐다.

## 3. Claude Code adapter `claude-code/1`

규칙은 spec §4.2.2와 `claude_code_adapter.py` 모듈 설명을 따른다. 원본 형식은 공개 계약이 아니므로(위험A2) 원본이 바뀌면 adapter 버전만 올린다.

### 3.1 세션 끝 판단 (`session_ended`)

spec은 export 때 세션이 끝났는지 정하지 않았다. 이 구현은 다음처럼 정한다.

- 프로젝트 폴더마다 수정 시각이 가장 늦은 `<session_id>.jsonl` 하나는 아직 실행 중일 수 있다고 보고 `session_ended=False`로 정규화한다. 마지막 main 교환이 `closed: false`로 남는다.
- 같은 폴더의 나머지 세션은 `session_ended=True`로 정규화한다. 모든 교환이 닫힌다.
- 나중에 더 새 세션이 생기면 이전 세션은 `session_ended=True`가 되어 정규화 바이트가 바뀌고, 다음 export에서 정규화 파일을 다시 쓴다.

## 4. `vg session export` (spec §4.2.4)

```
vg session export --agent {claude-code,codex} --out PATH (--session ID | --since DATE | --all) [--raw/--no-raw]
                  [--graph-home PATH] [--vault-map PATH]
```

- 원본 위치: `$CLAUDE_CONFIG_DIR/projects/` (`CLAUDE_CONFIG_DIR`가 없거나 비면 `~/.claude/projects/`).
- `--session`, `--since`, `--all` 중 정확히 하나를 준다. `--since`는 ISO 날짜나 시각이고, 시간대가 없으면 로컬 시각이다. main 원본 파일의 수정 시각이 그 이후인 세션을 고른다.
- 같은 세션 id가 두 프로젝트 폴더에 있으면 그 세션은 건너뛰고 경고 한 줄을 낸다.
- 쓰는 곳
  - `--raw`(기본): `PATH/raw/claude-code/<session_id>/` 아래에 원본 jsonl과 `subagents/`의 `.jsonl`, `.meta.json`을 바이트 그대로 복사한다.
  - 늘: `PATH/normalized/claude-code/<session_id>.jsonl`.
- 지키는 것
  - `PATH`가 Graph Home `configs/vaults.yaml`의 Vault나 `vault-map.json`의 Vault 안이면 아무것도 쓰지 않고 종료 코드 1로 끝난다. `vault-map.json`이 깨져 있으면 검사할 수 없으므로 같은 방식으로 끝난다.
  - `PATH`가 git 작업 트리 안이거나 동기화 폴더(iCloud Drive, `~/Library/CloudStorage/` 아래 Dropbox·Google Drive·OneDrive, `~/Dropbox`, `~/Google Drive`, `~/OneDrive`) 안이면 표준 오류에 `warning:` 줄을 하나 내고 쓴다.
  - 새로 만드는 폴더는 0700, 파일은 0600이다. 이미 있던 폴더의 권한은 바꾸지 않는다.
  - 파일마다 쓸 바이트가 기존 파일과 같으면 다시 쓰지 않는다. 그래서 같은 세션을 다시 export하면 mtime이 그대로다. 원본이 자랐으면 정규화 파일을 새로 쓰고 원본 사본을 덮어쓴다. 쓰기는 임시 파일과 `os.replace`로 한다.
  - `--agent codex`는 Codex adapter가 없다는 오류(`codex_adapter_missing`)로 끝난다(backlog B-1).
- 출력: 세션마다 한 줄. `normalized=written|unchanged`, 복사한 원본 파일 수, 건너뛴 원본 수, JSON이 아닌 줄 수, 모르는 레코드 종류별 수(spec §6).
- `--recapture`: export한 각 세션의 정규화 파일로 훅 실행기 `capture --direct --normalized <파일> --rerender`를 실행한다. 실행기에 주는 훅 JSON은 `session_id`, `transcript_path`, 정규화 파일 첫 줄의 `cwd`, `hook_event_name`(끝난 세션은 `SessionEnd`, 가장 최근 세션은 `PreCompact`)이다. 세션마다 시간 제한은 120초다. 실행기가 `--normalized`를 모르면(종료 코드 2) v1로 돌아가지 않고 종료 코드 1로 끝난다.
- 수집 훅(`vg hook capture`)은 SessionEnd에서 `session_ended=True`, 그 밖의 이벤트에서 `False`로 정규화한다. export 설정은 `$HOME/.vault-graph/configs/session-export.json`에서만 읽는다.

## 5. export 설정 `configs/session-export.json`

- 위치: Graph Home `configs/session-export.json`. 읽기·쓰기와 형식 확인은 `operation/scope/session_export_settings.py`가 한다.
- 키: `path`(절대 경로 문자열, 필수), `agents`(`claude-code`, `codex` 중 겹치지 않는 목록, 필수), `raw`(참·거짓, 없으면 참). 다른 키가 있으면 오류다.
- 파일이 없으면 export하지 않는다. 이 설정을 읽어 수집 때마다 export하는 일은 `vg hook capture`(S6)가 한다.

## 6. Codex adapter 계약 `codex/1` (구현은 backlog B-1, spec §4.2.3)

- 입력: `$HOME/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl`.
- 필드 대응

| 공통 필드 | Codex 원본 |
|---|---|
| session | `session_meta`(`id`, `cwd`, `git.branch`, `git.commit_hash`, `cli_version`, `parent_thread_id`) |
| 사람 턴 | `event_msg:item_completed`의 `UserMessage`. 없으면 `response_item:message` role `user`(`developer` 제외) |
| assistant 텍스트 | `AgentMessage` |
| 행동 | `CommandExecution.command`(`exit_code`, `status`), `FileChange.changes`의 경로 키, `McpToolCall.server/tool` |
| 교환 id | `turn_id`. 경계는 `task_started`, `task_complete`, `turn_aborted` |
| 서브에이전트 | `SubAgentActivity.agent_thread_id` |
| 압축 요약 | `compacted.message` |
| 순서 | `ordinal` |

- `reasoning`은 암호화되어 있어 넣지 않는다.
- B-1 완료 조건: Codex 고정 파일 세 개(서로 다른 `cli_version`)로 A-1과 같은 검사가 통과하고, `vg session export --agent codex`가 동작한다. 수집 훅은 Codex 쪽 훅 연결 방법을 확인한 뒤 정한다(위험A7).

## 7. 버전

- 필드를 더하면 `vg-session-jsonl/1` 그대로, 필드 뜻을 바꾸면 `/2`로 올린다.
- 원본 형식이 바뀌면 adapter 버전(`claude-code/N`, `codex/N`)만 올린다.
