# v1 세션 part를 v2로 다시 수집한다 (memory-intent 3a)

<!-- bake: index -->
| ID | title | status | relations | covered by | area | hash | tasks |
|---|---|---|---|---|---|---|---|
| I1 | vg는 Vault 파일을 직접 쓰지 않는다 |  | basis X8, X10 | A4 | global | ec01e1fb | 3-session-migrate-command.md |
| I2 | 고르기는 part 머리와 교환 시각만 보는 순수 함수다 |  | basis X7 | A1 | 고르기 | bd09e467 | 1-v1-coverage-pure-module.md |
| I3 | 덮인 세션은 다시 쓰지 않는다 |  | basis X1, X8 | A5 | 고르기, 수집 | 66b9f336 | 3-session-migrate-command.md |
| I4 | 결과 Vault가 다르면 멈춘다 |  | basis X10 | A6 | 수집 | a2c878cb | 3-session-migrate-command.md |
| D1 | 끝 조건을 "덮이지 않은 v1 part 0개"로 바꾼다 | decided | basis X8, X12, X14 | A11 | global | cdbae3d3 | 4-docs-and-real-run-handoff.md |
| D2 | 덮음은 같은 세션 v2 part 하나의 교환 시간 범위가 v1 part 범위를 포함하는 것이다 | decided | basis X5, X8, X11, X13, X20 | A1 | 고르기 | 0fefafb4 | 1-v1-coverage-pure-module.md |
| D3 | 새 명령 `vg session migrate`가 대상 세션을 골라 다시 수집한다 | decided | basis X1, X2; depends D2 | A3 | CLI | 4a17bcee | 3-session-migrate-command.md |
| D4 | 고르기는 M19 순수 파일에, 파일 읽기와 실행은 adapter에 둔다 | proposed | basis I2, X3, X7 | A9 | 배치 | 74ec882f | 2-capture-runner-options.md |
| D5 | 세션을 끝난 것으로 정규화하고, 최근 1시간 안에 바뀐 원본은 건너뛴다 | proposed | basis X4, X9, X18 | A4 | 정규화 | 94851a91 | 3-session-migrate-command.md |
| D6 | 세션 cwd가 지금 없으면 가장 가까운 존재하는 상위 폴더를 훅 JSON에 넣는다 | decided | basis I4, X2, X10, X17, X19 | A6 | 수집 | 3c411df9 | 3-session-migrate-command.md |
| D7 | 교환 수는 Vault `exchange_count`와 "턴이 하나 이상인 교환 수"로 맞춘다 | proposed | basis X3, X8, X9, X16; depends D5 | A2 | 수집, 확인 | 3c0bf2a4 | 3-session-migrate-command.md |
| D8 | 같은 첫·끝 교환 id의 v2 part가 이미 있으면 쓰지 않는다 | proposed | basis I3, X8; depends D2 | A5 | 고르기, 수집 | 72bc1b07 | 3-session-migrate-command.md |
| D9 | 원본 없음과 최근 세션은 보고만 하고, 나머지 문제는 실패로 끝낸다 | proposed | basis X4, X14; depends D1, D5 | A7 | CLI, 확인 | 9f0b55fd | 3-session-migrate-command.md |
| D10 | 다시 수집한 part를 사실 대기열에 넣지 않는다 | proposed | basis X6 | A8 | 사실 추출 | 02f1656d | 3-session-migrate-command.md |
| D11 | SPEC, 정규화 계약, ARCHITECTURE에 새 명령과 파일을 적는다 | proposed | basis X7; depends D3, D4 | A10 | 문서 | 8ee78e5d | 4-docs-and-real-run-handoff.md |
| D12 | 실제 Vault 이전은 구현·검증 뒤 이 세션에서 한 번 돌리고 모든 등록 Vault를 보고한다 | proposed | basis X12, X15; depends D1, D9 | A11, A12 | 실행 | ea066214 | 4-docs-and-real-run-handoff.md |
| F1 | 세션 원본 jsonl이 없다 |  | basis D9, X14 | A7 |  | c2d00274 | 3-session-migrate-command.md |
| F2 | 원본이 최근 1시간 안에 바뀌었다 |  | basis D5, D9 | A4 |  | 46670ed9 | 3-session-migrate-command.md |
| F3 | 세션 cwd 폴더가 지금 없다 |  | basis D6, X17 | A6 |  | 28144ffe | 3-session-migrate-command.md |
| F4 | 실행기가 다른 Vault에 썼다 |  | basis D6, I4 | A6 |  | 4ba51d97 | 3-session-migrate-command.md |
| F5 | 실행기가 끝나지 못했거나 Vault가 쓰지 않았다 |  | basis D9, X8 | A7 |  | b66bd35a | 3-session-migrate-command.md |
| F6 | 교환 수가 다르다 |  | basis D7, D8 | A2 |  | a8f38780 | 3-session-migrate-command.md |
| F7 | 다시 수집했는데도 v1 part가 덮이지 않는다 |  | basis D2, D8, X11 | A5 |  | 39372daa | 3-session-migrate-command.md |
| F8 | 같은 세션 id가 두 프로젝트 폴더에 있다 |  | basis D9, X4 | A7 |  | 96d31bc4 | 3-session-migrate-command.md |
| F9 | v1 part frontmatter를 읽지 못한다 |  | basis D2, D9 | A1 |  | b88fc754 | 3-session-migrate-command.md |
| F10 | `vault-map.json`이 없거나 깨졌거나 `--vault` 이름이 없다 |  | basis D3, X10 | A7 |  | 8981e7cf | 3-session-migrate-command.md |
| F11 | Vault에 `raw/sessions/claude-code/`가 없다 |  | basis D9, X12 | A3 |  | 303f46e9 | 3-session-migrate-command.md |
| R1 | 원본 일부가 실제 실행 전에 지워질 수 있다 |  | basis X15 |  |  | d851e284 |  |
| R2 | 교환 시간 범위로 본 덮음이 v1 part 끝의 턴을 놓칠 수 있다 |  | basis X9, X11, X20 |  |  | 57854dfd |  |
| R3 | 상위 폴더로 적힌 `cwd`가 색인이나 회상에 영향을 줄 수 있다 |  | basis X10, X17 |  |  | adbe9d97 |  |
| R4 | 큰 세션은 120초 안에 끝나지 않을 수 있다 |  | basis X2, X18 |  |  | a6509d2f |  |
| R5 | 실제 Vault는 복사본과 다를 수 있다 |  | basis X12, X19 |  |  | 8e74b0b3 |  |
| R6 | 실행기 결과의 Vault 이름과 `vault-map.json`의 이름이 같다고 보았다 |  | basis X8, X10, X19 |  |  | 7512999e |  |
| A1 | 덮음 규칙이 part 머리와 교환 시각으로 맞게 나뉜다 |  | covers D2, I2, F9 |  |  | a37c3e68 | 1-v1-coverage-pure-module.md |
| A2 | 교환 수가 다르거나 빠지면 실패로 끝난다 |  | covers D7, F6 |  |  | 6a21c147 | 3-session-migrate-command.md |
| A3 | `--dry-run`은 대상 목록만 내고 아무것도 쓰거나 돌리지 않는다 |  | covers D3, F11 |  |  | e9d5b770 | 3-session-migrate-command.md |
| A4 | 실행기만 Vault에 쓰고, 정규화는 끝난 세션으로 한다 |  | covers I1, D5, F2 |  |  | d68966d5 | 3-session-migrate-command.md |
| A5 | 두 번 돌려도 새 part가 생기지 않는다 |  | covers I3, D8, F7 |  |  | e511f7de | 3-session-migrate-command.md |
| A6 | cwd가 없으면 상위 폴더를 넘기고, 다른 Vault에 쓰면 멈춘다 |  | covers D6, I4, F3, F4 |  |  | 573bd374 | 3-session-migrate-command.md |
| A7 | 원본 없음은 보고만 하고, 고칠 수 없는 문제는 실패로 끝난다 |  | covers D9, F1, F5, F8, F10 |  |  | 97f8fc9a | 3-session-migrate-command.md |
| A8 | 사실 대기열이 바뀌지 않는다 |  | covers D10 |  |  | 0d36f862 | 3-session-migrate-command.md |
| A9 | 배치 규칙을 지키고 `vg session export --recapture`는 그대로다 |  | covers D4 |  |  | 8ad551ff | 3-session-migrate-command.md |
| A10 | SPEC, 정규화 계약, ARCHITECTURE가 새 명령과 파일을 적는다 |  | covers D11 |  |  | 97419e0b | 4-docs-and-real-run-handoff.md |
| A11 | 실제 실행 뒤 등록 Vault마다 원본 있는 세션의 덮이지 않은 v1 part가 0개다 |  | covers D1, D12 |  |  | b40cc7fb | 4-docs-and-real-run-handoff.md |
| A12 | 실제 이전은 상위 spec의 다른 구현보다 먼저 끝난다 |  | covers D12 |  |  | 4159ff06 | 4-docs-and-real-run-handoff.md |
| O1 | 끝 조건을 "v2가 덮지 않은 v1 part 0개"로 바꿔도 될까? |  | decides D1, D2 |  |  | c4f79a47 |  |
| O2 | 지금 없는 worktree에서 돈 세션은 상위 폴더 기준으로 수집할까? |  | decides D6 |  |  | 6d45e6f0 |  |
| O3 | 새 명령 이름을 `vg session migrate`로 할까? |  | decides D3 |  |  | 1d71ab3f |  |
| X1 | `vg session export --recapture`는 v1 part가 있는 세션만 고르지 못한다 |  |  |  |  | 4dd5bc3f |  |
| X2 | `recapture_session`은 정규화 파일 첫 줄의 `cwd`와 `newest`로 훅 JSON을 만든다 |  |  |  |  | 01d82296 |  |
| X3 | 실행기 결과에서 vg는 `status`, `vault`, `path`만 읽는다 |  |  |  |  | 8a296538 |  |
| X4 | 정규화는 프로젝트 폴더의 가장 최근 세션만 끝나지 않은 것으로 본다 |  |  |  |  | ca231208 |  |
| X5 | 색인은 겹친 v1 교환과 중복 v2 교환을 빼고 Vault 파일은 건드리지 않는다 |  |  |  |  | 3f2c0e94 |  |
| X6 | 사실 작업자는 `vg:exchange` 메타 줄이 있는 교환만 처리한다 |  |  |  |  | 76213c55 |  |
| X7 | 모듈 배치 규칙: 세션 순수 코드는 M19, 파일과 실행기는 adapter |  |  |  |  | 7fc5903a |  |
| X8 | `--rerender`는 가장 높은 part 다음 번호로 새 파일만 쓴다 |  |  |  |  | 072c39da |  |
| X9 | Vault는 턴 없는 교환을 건너뛰고 처음 열린 교환에서 멈춘다 |  |  |  |  | 21068c6b |  |
| X10 | 새 part의 `cwd`와 Vault 선택은 훅 JSON `cwd`를 먼저 따른다 |  |  |  |  | 02f05f45 |  |
| X11 | v1 part는 frontmatter `schema: vault-session/v1`과 턴 시각 범위를 가진다 |  |  |  |  | 41a13b15 |  |
| X12 | 등록 Vault 다섯 곳에 v1 part가 89개 있다 |  | basis X11 |  |  | 163e280c |  |
| X13 | v1 part 뒤에 v2 part가 이어진 세션이 있다 |  |  |  |  | be525a19 |  |
| X14 | bake Vault의 두 세션은 원본 jsonl이 없다 |  |  |  |  | 30828449 |  |
| X15 | 가장 오래된 원본 jsonl의 수정 시각은 2026-10-22다 |  |  |  |  | 7dee37c3 |  |
| X16 | Vault 복사본 시험에서 15세션은 교환 수가 맞게 써졌다 |  |  |  |  | 0dca6862 |  |
| X17 | cwd가 지금 없는 worktree인 7세션은 Vault가 쓰지 않았다 |  |  |  |  | dd749ec8 |  |
| X18 | 프로젝트 폴더의 가장 최근 세션은 교환이 열린 채 정규화되어 일부만 써졌다 |  | basis X4, X9 |  |  | a287e0cf |  |
| X19 | 끝난 세션 정규화와 상위 폴더 cwd로 Vault 다섯 곳 복사본에 시험하면 원본 있는 53세션이 모두 맞게 써진다 |  | basis X4, X9, X17, X18 |  |  | cb3a4aad |  |
| X20 | v2 frontmatter `last_turn_at`은 가장 늦은 시각이 아니다. 교환 메타의 `started`·`ended` 범위로 보면 모든 v1 part가 덮인다 |  | basis X11, X19 |  |  | 81a05922 |  |
<!-- bake: index end -->

## 1. Problem

v1 세션 part에서는 사실을 뽑을 수 없고, 지금 있는 명령으로는 v1 part만 골라 다시 수집할 수 없다. 2026-11-25에 커밋 `fd21e3f`의 코드, Vault 도구와 실행기, 등록 Vault 다섯 곳을 확인한 내용은 `research/code-paths.md`와 `research/vault-measurements.md`에 사실로 적었다. 상위 spec은 `2026-11-25-memory-intent-layers`의 §4.3 3a다.

- 사실 작업자는 교환 메타 줄이 있는 교환만 처리한다(X6). v1 part에는 그 줄이 없다(X11). 등록 Vault 다섯 곳에 v1 part가 89개 있다(X12).
- `vg session export --recapture`는 세션을 `--session`, `--since`, `--all`로만 고른다(X1). `--all`은 이미 v2인 세션도 다시 써서 같은 교환이 담긴 part가 하나 더 생긴다. 세션 id를 하나씩 주는 방법은 섞인 세션(X13)과 원본 없는 세션(X14)을 사람이 직접 가려야 한다.
- Vault 도구는 기존 파일을 바꾸거나 지우지 않는다(X8). 그래서 다시 수집해도 v1 파일은 그대로 남고, "v1 part가 0개"라는 끝 조건은 지킬 수 없다.
- Vault 복사본 시험(X16)에서 23세션 중 8세션이 제대로 써지지 않았다. 7세션은 cwd가 지금 없는 worktree라 Vault가 쓰지 않았고(X17), 프로젝트 폴더의 가장 최근 세션은 교환이 열린 채 정규화되어 일부만 써졌다(X18).
- vg는 실행기 결과에서 `exchange_count`를 읽지 않는다(X3). 교환 수가 원본과 같은지 확인할 길이 없다.
- 원본 jsonl은 2026-10-22 것부터 남아 있고 Claude Code가 기본 30일 뒤 지운다(X15).

## 2. Intent

사용자는 Vault의 v1 세션 part를 모두 v2 part로 다시 수집해, 사실 작업자가 모든 세션을 처리할 수 있기를 원한다. 상위 세션이 사용자 승인 뒤 맡긴 끝 조건은 네 가지다. v1 part가 남지 않는다. 다시 수집한 part의 교환 수가 원본 jsonl과 같다. Vault 도구 밖에서 Vault 파일을 쓰지 않는다. 테스트가 있다. 다른 등록 Vault의 v1 part도 확인해 보고하고, 원본이 지워지기 전에 가장 먼저 한다.

[가정] 첫 끝 조건은 "v2 part가 덮지 않는 v1 part가 0개"로 읽는다. Vault 도구는 기존 파일을 지우지 않고 vg는 `raw/`를 쓰지 않으므로 v1 파일 자체는 남는다. 원본이 없는 part는 0개 셈에서 빼고 따로 보고한다. spec gate에서 확인한다(O1).

[가정] 이 change는 명령과 테스트를 만들고, 승인과 검증 뒤 실제 Vault에 한 번 돌려 결과를 보고하는 데까지다.

## 3. Non-goals

- v1 파일을 지우거나 고치지 않는다. 색인은 이미 v2와 겹친 v1 교환을 뺀다(X5).
- 다시 수집한 part를 사실 대기열에 넣지 않는다. 기존 part를 대기열에 넣는 일은 3b `vg facts backfill`이 한다.
- Vault 도구, 실행기(vault-builder), Vault 선택 규칙을 바꾸지 않는다.
- Codex 세션은 다루지 않는다. Codex adapter는 backlog B-1이다.
- `vg session export --recapture`의 동작과 출력은 바꾸지 않는다.
- 섞인 세션에서 새 part와 기존 v2 part에 같은 교환이 두 번 담기는 것은 막지 않는다. 색인은 하나만 쓴다(X5).
- AGENTS.md는 고치지 않는다. 새 명령은 쓰기 경로 3(수집 실행기)을 그대로 쓴다.

## 4. Design

**4.1 명령**

```
vg session migrate [--vault NAME]... [--dry-run] [--graph-home PATH] [--vault-map PATH]
```

에이전트는 `claude-code` 하나다. `--vault`가 없으면 `vault-map.json`의 모든 Vault를 본다. 이름은 spec gate에서 정한다(O3).

**4.2 흐름**

1. 단계1 part 읽기: Vault마다 `raw/sessions/claude-code/*.md`(`.facts.md` 제외)의 frontmatter만 읽어 part 머리(Vault 이름, 경로, `schema`, `session_id`, `part`, `first_turn_at`, `last_turn_at`, `first_exchange_id`, `last_exchange_id`)를 만든다. 본문은 읽지 않는다.
2. 단계2 고르기: 같은 Vault, 같은 세션의 v2 part 하나가 v1 part의 시간 범위를 포함하면 그 v1 part는 덮였다. 덮이지 않은 v1 part가 하나라도 있는 세션이 대상이다.
3. 단계3 원본 찾기: `~/.claude/projects/`에서 세션 원본을 찾는다. 없거나, 두 폴더에 있거나, 최근 1시간 안에 바뀌었으면 쓰지 않고 이유를 적는다. `--dry-run`은 여기까지 하고 목록만 낸다.
4. 단계4 정규화: 세션을 끝난 것으로 보고 OS 임시 폴더에 정규화 파일을 쓴다. 턴이 하나 이상인 교환 수와 첫·끝 교환 id를 센다.
5. 단계5 중복 막기: 같은 세션의 v2 part 중 첫·끝 교환 id가 정규화 파일과 같은 것이 이미 있으면 쓰지 않는다.
6. 단계6 수집: 기존 `recapture_session`으로 실행기를 `--normalized <파일> --rerender`, `SessionEnd`로 돌린다. 세션 cwd가 지금 없으면 훅 JSON `cwd`에 가장 가까운 존재하는 상위 폴더를 넣는다.
7. 단계7 확인: 결과가 `written`이고, 결과 Vault가 v1 part의 Vault와 같고, `exchange_count`가 단계4의 수와 같아야 한다. 그 세션의 part를 다시 읽어 v1 part가 모두 덮였는지 본다. Vault가 다르면 다음 세션으로 가지 않고 멈춘다.

출력은 세션마다 한 줄(`<vault> <session_id> <결과> v1_parts=N exchanges=N`)과 Vault마다 요약 한 줄(`v1_parts`, `covered`, `uncovered`, `source_missing`)이다. 실패가 하나라도 있으면 종료 코드 1이다.

**4.3 파일과 심볼**

코드 경로는 `src/vault_graph/` 기준이다. 원본 폴더는 export와 같이 `$CLAUDE_CONFIG_DIR/projects/`(없으면 `~/.claude/projects/`)다.

| 위치 | 바뀌는 것 |
|---|---|
| `operation/sessions/v1_coverage.py`(새 파일, M19) | part 머리 DTO, `uncovered_v1_parts(parts)`, 정규화 줄에서 교환 수와 첫·끝 id를 세는 `exchange_summary(lines)`. 파일과 프로세스를 다루지 않는다 |
| `interface/composition/adapters/session_migration.py`(새 파일) | Vault part frontmatter 읽기(M01 `parse_vault_frontmatter`), 원본 찾기, 임시 폴더 정규화, cwd 대체, 실행기 호출, 결과 확인 |
| `interface/composition/adapters/session_capture_runner.py` | `recapture_session(..., hook_cwd: str \| None = None)` 선택 인자 |
| `interface/composition/adapters/vault_capture_cli.py` | `CaptureOutcome.exchange_count: int \| None`과 결과 JSON에서 읽기 |
| `interface/cli/session_commands.py` | `migrate` 명령 |
| `docs/SPEC.md`, `docs/contracts/vg-session-jsonl-v1.md` §4, `docs/ARCHITECTURE.md` §1 표 | 새 명령과 파일 |

### I1. vg는 Vault 파일을 직접 쓰지 않는다
- by: 사람 (brief 요청, 끝 조건 "Vault 도구 밖에서 Vault 파일을 쓰지 않는다")
- area: global
- basis: X8, X10

Vault에 생기는 파일은 실행기와 Vault `sessions capture`가 `--rerender`로 쓴 새 part뿐이다. vg는 Vault 안에서 frontmatter를 읽기만 하고, 정규화 파일은 Vault 밖 OS 임시 폴더에 쓴 뒤 지운다. 기존 v1·v2 파일은 바뀌지 않는다.

### I2. 고르기는 part 머리와 교환 시각만 보는 순수 함수다
- by: 가정 (ARCHITECTURE 배치 규칙을 따름)
- area: 고르기
- basis: X7

`uncovered_v1_parts`와 `exchange_summary`는 받은 값(part 머리, v2 교환 메타의 시각, 정규화 줄)만 보고 같은 입력에 같은 결과를 낸다. 파일을 읽거나 프로세스를 띄우지 않고, M01 밖의 기능 영역을 가져오지 않는다.

### I3. 덮인 세션은 다시 쓰지 않는다
- by: 가정 (brief 가정 "두 번 돌려도 이미 덮인 세션은 다시 쓰지 않는다"에 첫·끝 교환 id 검사를 더함)
- area: 고르기, 수집
- basis: X1, X8

v1 part가 모두 덮인 세션은 대상이 아니다. 덮지 못했더라도 같은 첫·끝 교환 id의 v2 part가 이미 있으면 쓰지 않는다. 그래서 같은 Vault 상태에서 명령을 두 번 돌리면 두 번째에는 새 part가 0개다.

### I4. 결과 Vault가 다르면 멈춘다
- by: 가정 (brief 가정: cwd 대체)
- area: 수집
- basis: X10

Vault는 실행기와 Vault 도구가 고른다. 결과의 `vault`가 v1 part가 있던 Vault 이름과 다르면 그 세션을 실패로 적고 남은 세션을 돌리지 않는다. 잘못된 Vault에 part가 더 쌓이는 것을 막는다.

## 5. Decisions

사용자가 직접 정한 것은 요청 원문의 끝 조건뿐이다. 나머지는 brief의 가정이거나 이 spec이 더한 것이라 `proposed`다.

### D1. 끝 조건을 "덮이지 않은 v1 part 0개"로 바꾼다
- by: 사람 (2026-11-25 spec gate 승인. 사람은 v1 파일까지 모두 v2로 옮기는 방안을 물었고, v1 파일 정리는 vault-builder 쪽 후속 일로 남김)
- status: decided
- area: global
- basis: X8, X12, X14

요청의 "v1 part가 남지 않는다"는 지킬 수 없다. Vault 도구는 기존 파일을 바꾸지 않고(X8) vg는 `raw/`를 쓰지 않는다. 그래서 끝 조건을 "등록 Vault마다, 원본이 있는 세션의 v1 part 중 v2 part가 덮지 않은 것이 0개"로 바꾼다. 원본이 없는 part(X14)는 0개 셈에서 빼고 Vault별로 따로 보고한다. 89개(X12) 중 몇 개가 덮였는지는 실행 보고에 적는다. 사람은 v1 파일도 남지 않는 완전한 이전을 원한다. 그 일은 Vault 도구(vault-builder)에 v2가 덮은 v1 파일을 보관하거나 치우는 명령이 있어야 하므로 이 change 밖의 후속 일이다. 그 명령도 덮는 v2 part가 먼저 있어야 하므로 이 change가 첫 단계다.

### D2. 덮음은 같은 세션 v2 part 하나의 교환 시간 범위가 v1 part 범위를 포함하는 것이다
- by: 사람 (2026-11-25 spec gate 승인)
- status: decided
- area: 고르기
- basis: X5, X8, X11, X13, X20

v1 part P가 덮였다는 것은, 같은 Vault의 같은 `agent`와 `session_id`를 가진 v2 part 하나가 있고 그 part 본문의 `vg:exchange` 메타 줄 중 가장 이른 `started`가 P의 `first_turn_at`보다 늦지 않으며 가장 늦은 `ended`가 P의 `last_turn_at`보다 이르지 않다는 뜻이다. v2 frontmatter의 `last_turn_at`은 파일 순서상 마지막 턴이라 가장 늦은 시각이 아니므로 쓰지 않는다(X20). v1 쪽은 frontmatter 시각을 쓴다. 시각은 문자열이 아니라 시각 값으로 비교한다. 여러 v2 part를 이어 붙여 덮는 것은 인정하지 않는다. 섞인 세션(X13)의 뒤 v2 part는 앞 v1 범위를 담지 않으므로 그 세션은 대상이 된다. 색인이 겹친 v1 교환을 빼는 규칙(X5)과 같은 생각이지만, 교환 단위가 아니라 part 단위로 본다. v2 본문은 메타 줄만 읽는다. 복사본 시험 뒤 이 규칙으로 재면 원본 있는 세션의 v1 part가 모두 덮였다(X20).

### D3. 새 명령 `vg session migrate`가 대상 세션을 골라 다시 수집한다
- by: 사람 (2026-11-25 spec gate: "vg session migrate (Recommended)" 선택)
- status: decided
- area: CLI
- basis: X1, X2
- depends: D2

`vg session export --recapture`에 선택지를 더하지 않고 새 명령을 둔다. export는 사람이 고른 폴더에 원본 사본을 남기는 명령이고(X1), 이 일은 Vault part를 읽어 대상을 스스로 고른다. 옵션은 §4.1대로 `--vault NAME`(여러 번), `--dry-run`, `--graph-home`, `--vault-map`이다. `--out`이 없고 원본 사본을 만들지 않는다. 실행기 호출은 export와 같은 `recapture_session`(X2)을 쓴다.

### D4. 고르기는 M19 순수 파일에, 파일 읽기와 실행은 adapter에 둔다
- by: 가정 (dispatch가 ARCHITECTURE 배치 규칙을 따르라고 함)
- status: proposed
- area: 배치
- basis: I2, X3, X7

덮음 판단과 교환 수 세기는 `operation/sessions/v1_coverage.py`에 둔다. M19는 세션 형식을 다루는 순수 코드 영역이고 M01만 가져오며, 기능 영역 누구도 가져오지 않는다(X7). Vault frontmatter 읽기, 원본 찾기, 임시 폴더, 실행기 호출은 `interface/composition/adapters/session_migration.py`가 한다. `CaptureOutcome`에 `exchange_count`를 더하고(X3) `recapture_session`에 `hook_cwd` 선택 인자를 더한다. 둘 다 기본값이면 지금 동작과 같다. ARCHITECTURE §1의 M19 행과 2026-11-05 파일 표에 두 파일을 적는다.

### D5. 세션을 끝난 것으로 정규화하고, 최근 1시간 안에 바뀐 원본은 건너뛴다
- by: 가정 (brief 가정)
- status: proposed
- area: 정규화
- basis: X4, X9, X18

지금 규칙대로면 프로젝트 폴더의 가장 최근 세션은 마지막 교환이 열린 채 정규화되고(X4), Vault는 처음 열린 교환에서 멈춘다(X9). 시험에서 세 세션이 이 때문에 일부만 써졌다(X18). 이 명령은 모든 대상 세션을 `newest=False`로 보고 `session_ended=True`로 정규화하고 훅 이벤트는 `SessionEnd`로 넘긴다. 다만 main 원본이나 `subagents/` 파일 중 하나라도 수정 시각이 실행 시각 1시간 안이면 아직 돌고 있을 수 있으니 쓰지 않고 `recent`로 보고한다. v1 part는 10월 말~11월 초 세션이라 대부분 이 조건에 걸리지 않는다.

### D6. 세션 cwd가 지금 없으면 가장 가까운 존재하는 상위 폴더를 훅 JSON에 넣는다
- by: 사람 (2026-11-25 spec gate: "상위 폴더로 (Recommended)". 지운 worktree 세션도 반드시 수집되기를 원함)
- status: decided
- area: 수집
- basis: I4, X2, X10, X17, X19

시험에서 7세션은 cwd가 지운 worktree라 Vault가 쓰지 않았다(X17). 정규화 파일의 세션 `cwd`가 지금 폴더로 없으면, 그 경로에서 위로 올라가 처음 있는 폴더를 `hook_cwd`로 넘긴다(X2). 정규화 파일 속 `cwd`는 바꾸지 않는다. Vault를 고르는 일은 여전히 실행기와 Vault 도구가 한다(X10). 고른 Vault가 v1 part의 Vault와 다르면 I4대로 멈춘다. 대가는 새 part frontmatter의 `cwd`가 원래 worktree가 아니라 상위 폴더로 적히는 것이다(X10). Vault 다섯 곳 복사본 시험에서 cwd가 없는 30세션을 이렇게 넘겼고 모두 원래 Vault에 써졌다(X19). 상위 폴더가 어느 등록 프로젝트에도 속하지 않으면 Vault가 쓰지 않으므로 그 세션은 `failed`로 남는다. 지금 대상 세션 중에는 그런 세션이 없다.

### D7. 교환 수는 Vault `exchange_count`와 "턴이 하나 이상인 교환 수"로 맞춘다
- by: 사람 (brief 요청, 끝 조건 "다시 수집한 part의 교환 수가 원본 jsonl과 같다"), 가정 (비교할 두 값)
- status: proposed
- area: 수집, 확인
- basis: X3, X8, X9, X16
- depends: D5

원본 jsonl의 교환 수는 정규화 파일에서 센다. Vault는 턴 없는 교환을 건너뛰므로(X9) 비교 값은 "턴이 하나 이상인 교환 수"다. D5로 모든 교환이 닫혀 있으니 이 수가 Vault가 써야 할 수다. 결과 JSON의 `exchange_count`(X8)를 `CaptureOutcome`에서 읽고(X3) 두 수가 다르면 그 세션은 실패, 종료 코드 1이다. 시험의 15세션은 두 수가 같았다(X16). 결과에 `exchange_count`가 없어도 실패다.

### D8. 같은 첫·끝 교환 id의 v2 part가 이미 있으면 쓰지 않는다
- by: 가정 (I3을 지키려고 더함)
- status: proposed
- area: 고르기, 수집
- basis: I3, X8
- depends: D2

D2의 시간 범위 검사만 쓰면, 다시 수집한 part가 어떤 이유로 v1 범위를 덮지 못할 때 실행할 때마다 같은 내용의 part가 하나씩 더 생긴다. 그래서 쓰기 전에 그 세션의 v2 part 중 `first_exchange_id`와 `last_exchange_id`(X8)가 정규화 파일의 첫·끝 교환 id와 같은 것이 있는지 본다. 있으면 쓰지 않고 그 세션을 `already_recaptured_uncovered` 실패로 보고한다. 사람이 원인을 본 뒤 정할 일이다.

### D9. 원본 없음과 최근 세션은 보고만 하고, 나머지 문제는 실패로 끝낸다
- by: 가정 (brief 가정 "원본이 없는 part는 따로 보고"를 종료 코드로 정함)
- status: proposed
- area: CLI, 확인
- basis: X4, X14
- depends: D1, D5

세션 결과는 `written`, `covered`(대상 아님), `source_missing`, `recent`, `failed:<이유>` 중 하나다. `source_missing`(X14)은 할 수 있는 일이 없고, `recent`는 나중에 다시 돌리면 되므로 종료 코드를 바꾸지 않는다. 같은 세션 id가 두 프로젝트 폴더에 있는 경우(X4), 실행기 실패, Vault의 `skipped`·`no-new-turns`, 교환 수 불일치, Vault 불일치, 다시 읽은 뒤 덮이지 않음, frontmatter를 읽지 못한 v1 part는 실패이고 종료 코드 1이다. 실패한 세션이 있어도 Vault 불일치가 아니면 다음 세션을 계속 돈다.

### D10. 다시 수집한 part를 사실 대기열에 넣지 않는다
- by: 가정 (brief 가정, 3b 범위)
- status: proposed
- area: 사실 추출
- basis: X6

이 명령은 Graph Home `facts/queue/`에 작업 파일을 두지 않고 사실 작업자를 띄우지 않는다. 새 v2 part는 교환 메타 줄이 있어 사실 작업자가 처리할 수 있는 상태가 되고(X6), 실제로 대기열에 넣는 일은 3b `vg facts backfill`이 한다. 섞인 세션은 같은 교환이 두 part에 있으므로 3b가 교환별 캐시로 다시 뽑지 않아야 한다.

### D11. SPEC, 정규화 계약, ARCHITECTURE에 새 명령과 파일을 적는다
- by: 가정 (brief 규칙: SPEC session export 줄과 계약 §4에 적어야 함)
- status: proposed
- area: 문서
- basis: X7
- depends: D3, D4

`docs/SPEC.md`의 `vg session export` 설명 줄 옆에 `vg session migrate`를 한 줄로 더한다. `docs/contracts/vg-session-jsonl-v1.md` §4 아래에 명령 형식, 덮음 규칙, 정규화 규칙, 출력, 종료 코드를 적는다. `docs/ARCHITECTURE.md`는 §1 파일 표와 §4 세션 수집 행에 새 파일과 명령을 더한다. AGENTS.md는 고치지 않는다.

### D12. 실제 Vault 이전은 구현·검증 뒤 이 세션에서 한 번 돌리고 모든 등록 Vault를 보고한다
- by: 사람 (brief 요청: 다른 등록 Vault도 확인해 보고, 가장 먼저 함), 가정 (실행 시점과 순서)
- status: proposed
- area: 실행
- basis: X12, X15
- depends: D1, D9

구현 테스트가 통과한 뒤 먼저 `--dry-run`으로 Vault 다섯 곳의 대상 목록을 보고, 그다음 옵션 없이 한 번 돌린다. 원본이 지워지기 전에 해야 하므로(X15) 상위 spec의 다른 일보다 먼저 한다. 보고에는 Vault마다 v1 part 수, 덮인 수, 덮이지 않은 수, 원본 없음 수, 실패 세션과 이유를 적는다(X12와 비교). Vault 파일은 Vault 저장소의 commit 대상이므로, 이 change는 vg 저장소에 Vault 파일을 넣지 않는다.

## 6. Failure and boundary behavior

세션 하나의 문제는 그 세션 줄에 적고 다음 세션으로 간다. 명령 전체가 멈추는 경우는 Vault 불일치와 Vault 목록을 읽지 못하는 경우뿐이다.

### F1. 세션 원본 jsonl이 없다
- basis: D9, X14

그 세션은 `source_missing`으로 적고 실행기를 돌리지 않는다. Vault 요약 줄의 `source_missing`에 그 세션의 v1 part 수를 더한다. 종료 코드는 바뀌지 않는다. bake Vault의 두 세션이 여기에 해당한다(X14).

### F2. 원본이 최근 1시간 안에 바뀌었다
- basis: D5, D9

main 원본이나 `subagents/` 파일 하나라도 실행 시각 1시간 안에 바뀌었으면 `recent`로 적고 정규화하지 않는다. 종료 코드는 바뀌지 않는다. 지금 이 명령을 돌리는 세션 자신도 여기에 걸린다.

### F3. 세션 cwd 폴더가 지금 없다
- basis: D6, X17

`hook_cwd`에 가장 가까운 존재하는 상위 폴더를 넣고 세션 줄에 `cwd_fallback=<폴더>`를 붙인다. 실행기가 그 폴더로 Vault를 고르지 못하면 Vault 결과가 `skipped`이고, 그 세션은 실행기 실패와 같이 `failed:<이유>`로 적는다.

### F4. 실행기가 다른 Vault에 썼다
- basis: D6, I4

결과 `vault`가 v1 part의 Vault 이름과 다르면 `failed:vault_mismatch`와 쓴 Vault, 경로를 적고 남은 세션을 돌리지 않은 채 종료 코드 1로 끝난다. 잘못 쓴 part는 vg가 지우지 못하므로 사람이 그 Vault에서 정리한다고 출력에 적는다.

### F5. 실행기가 끝나지 못했거나 Vault가 쓰지 않았다
- basis: D9, X8

실행기가 없음, 시간 초과(120초), 0이 아닌 종료, `--normalized`를 모름(v1로 돌아가지 않음), Vault 상태 `skipped`나 `no-new-turns`는 모두 `failed:<이유>`다. Vault의 메시지를 표준 오류에 그대로 옮긴다. 종료 코드는 1이고 다음 세션은 계속 돈다.

### F6. 교환 수가 다르다
- basis: D7, D8

`exchange_count`가 정규화 파일의 턴 있는 교환 수와 다르거나 결과에 없으면 `failed:exchange_count expected=N got=M`으로 적는다. part는 이미 써졌으므로 경로도 적는다. 다음 실행에서는 D8 때문에 다시 쓰지 않는다.

### F7. 다시 수집했는데도 v1 part가 덮이지 않는다
- basis: D2, D8, X11

쓴 뒤 그 세션의 part 머리를 다시 읽어 D2로 본다. 덮이지 않은 v1 part가 남으면 `failed:uncovered` 뒤에 그 part 경로와 v1·v2 시간 범위를 적는다. v1 렌더러가 정규화에 없는 턴을 담았거나 시각 표기가 다를 때 생길 수 있다. 다음 실행은 D8로 같은 part를 다시 쓰지 않고 `already_recaptured_uncovered`로 적는다.

### F8. 같은 세션 id가 두 프로젝트 폴더에 있다
- basis: D9, X4

어느 원본이 맞는지 고를 수 없으므로 쓰지 않고 `failed:duplicate_source`로 적는다. 종료 코드는 1이다.

### F9. v1 part frontmatter를 읽지 못한다
- basis: D2, D9

`session_id`, `first_turn_at`, `last_turn_at` 중 하나라도 없거나 시각으로 읽히지 않는 v1 part는 덮음을 판단할 수 없다. 그 part는 `failed:unreadable_part <경로>`로 적고, 그 세션은 다시 수집하지 않는다. 시각을 읽지 못하는 v2 part는 덮는 part로 쓰지 않는다.

### F10. `vault-map.json`이 없거나 깨졌거나 `--vault` 이름이 없다
- basis: D3, X10

Vault 목록을 알 수 없으므로 아무 세션도 보지 않고 `vault_map_invalid` 또는 `unknown_vault: <이름>`을 내고 종료 코드 1로 끝난다. 실행기도 같은 파일로 Vault를 고르므로(X10) 이 상태에서 돌리면 쓰기도 실패한다.

### F11. Vault에 `raw/sessions/claude-code/`가 없다
- basis: D9, X12

personal Vault처럼 세션 폴더가 없는 Vault(X12)는 요약 줄에 `v1_parts=0`으로 적고 넘어간다. 오류가 아니다.

## 7. What could be wrong

### R1. 원본 일부가 실제 실행 전에 지워질 수 있다
- basis: X15

가장 오래된 원본은 2026-10-22에 바뀐 것이다. Claude Code가 30일을 어떤 시각으로 세고 언제 지우는지 확인하지 않았다. 구현과 리뷰가 길어지면 10월 세션 원본이 사라져 그 part가 `source_missing`으로 바뀔 수 있다.

### R2. 교환 시간 범위로 본 덮음이 v1 part 끝의 턴을 놓칠 수 있다
- basis: X9, X11, X20

v1 렌더러는 원본 턴을 그대로 썼고 v2는 정규화된 교환에서 턴 있는 것만 쓴다. v1 part의 끝 턴이 정규화에서 빠지는 종류라면 내용은 다 담겼는데도 v2 범위가 v1 범위를 포함하지 못할 수 있다. 지금 Vault 다섯 곳 복사본에서는 그런 part가 없었다(X20). 생기면 그 세션은 `failed:uncovered`로 남는다.

### R3. 상위 폴더로 적힌 `cwd`가 색인이나 회상에 영향을 줄 수 있다
- basis: X10, X17

새 part frontmatter의 `cwd`는 지운 worktree 대신 상위 폴더가 된다. vg 색인, 회상의 프로젝트 범위, 사실 작업자가 part `cwd`를 쓰는지는 확인하지 않았다. `project`는 실행기가 고른 프로젝트라 같을 것으로 본다.

### R4. 큰 세션은 120초 안에 끝나지 않을 수 있다
- basis: X2, X18

시간 제한은 export와 같은 120초다. `3613510c`처럼 subagent 교환이 70개를 넘는 세션의 렌더 시간은 재지 않았다. 시간 초과면 그 세션은 실패로 남는다.

### R5. 실제 Vault는 복사본과 다를 수 있다
- basis: X12, X19

시험은 Vault 다섯 곳의 복사본에서 했다(X19). 복사본을 만든 뒤 실제 Vault에 새 part가 생기거나 Vault 도구가 바뀌면 결과가 다를 수 있다. 실제 실행 전에 `--dry-run`으로 대상을 다시 본다.

### R6. 실행기 결과의 Vault 이름과 `vault-map.json`의 이름이 같다고 보았다
- basis: X8, X10, X19

Vault 결과 `vault`는 Vault 도구가 고른 이름이고, v1 part의 Vault 이름은 vg가 `vault-map.json` 키에서 얻는다. 복사본 시험에서는 53세션 모두 두 이름이 같았지만(X19) 코드로 같은 출처인지 확인하지는 않았다. 다르면 첫 세션에서 Vault 불일치로 멈춘다.

## 8. Acceptance criteria

명령의 동작은 가짜 실행기와 임시 Vault 폴더로 테스트하고, 실제 Vault 결과는 한 번 돌린 뒤 사람이 본다. 가짜 실행기는 기존 `tests/test_cli_session_recapture.py`처럼 받은 인자와 훅 JSON을 기록하고, 받은 정규화 파일로 v2 part 파일 하나를 임시 Vault에 쓴다.

### A1. 덮음 규칙이 part 머리와 교환 시각으로 맞게 나뉜다
- covers: D2, I2, F9
- check: tests/test_session_v1_coverage.py
- evidence: tests/test_session_v1_coverage.py: test_v2_exchange_range_containing_v1_range_covers_it, test_v2_frontmatter_last_turn_at_is_ignored, test_mixed_session_later_v2_part_does_not_cover_earlier_v1, test_other_vault_or_other_session_v2_part_is_not_counted, test_two_v2_parts_are_not_joined, test_same_instant_with_and_without_milliseconds_is_equal, test_unreadable_v1_parts_come_back_separately, test_same_input_gives_same_result (uv run pytest 결과 172 passed in 4.84s)

다음 경우를 확인한다. 교환 메타 범위가 포함하면 덮임. v2 frontmatter `last_turn_at`이 v1 끝보다 이르더라도 교환 메타의 가장 늦은 `ended`가 포함하면 덮임. 같은 세션의 뒤 v2 part만 있으면(섞인 세션) 덮이지 않음. 다른 Vault나 다른 세션의 v2 part는 세지 않음. 두 v2 part를 이어야 포함되면 덮이지 않음. 시각 표기가 달라도(밀리초 유무) 같은 시각이면 같게 봄. 시각을 읽지 못하는 v1 part는 판단 불가로 따로 나옴. 같은 입력이면 같은 결과다.

### A2. 교환 수가 다르거나 빠지면 실패로 끝난다
- covers: D7, F6
- check: tests/test_session_v1_coverage.py, tests/test_cli_session_migrate.py
- evidence: tests/test_session_v1_coverage.py test_exchange_summary_counts_exchanges_with_turns_and_takes_first_and_last_ids, tests/test_cli_session_migrate.py test_exchange_count_mismatch_fails와 test_run_recaptures_through_the_launcher_as_ended_sessions, tests/test_session_capture_runner_options.py test_exchange_count_is_none_without_a_result_line (172 passed)

`exchange_summary`는 턴 없는 교환을 세지 않는다. 가짜 실행기가 `exchange_count`를 정규화 파일의 턴 있는 교환 수와 같게 내면 세션은 `written`이고 종료 코드 0이다. 하나 적게 내거나 빼면 세션은 `failed:exchange_count`이고 종료 코드는 1이다.

### A3. `--dry-run`은 대상 목록만 내고 아무것도 쓰거나 돌리지 않는다
- covers: D3, F11
- check: tests/test_cli_session_migrate.py
- evidence: tests/test_cli_session_migrate.py: test_dry_run_lists_targets_and_writes_and_runs_nothing (172 passed)

v1 part가 있는 세션, 덮인 세션, 원본 없는 세션, 세션 폴더 없는 Vault가 섞인 임시 Vault 두 개로 돌린다. 출력에 세션마다 한 줄과 Vault 요약 줄이 있고, 세션 폴더 없는 Vault는 `v1_parts=0`이다. 가짜 실행기 기록은 비어 있고 Vault 폴더와 OS 임시 폴더에 새 파일이 없다.

### A4. 실행기만 Vault에 쓰고, 정규화는 끝난 세션으로 한다
- covers: I1, D5, F2
- check: tests/test_cli_session_migrate.py
- evidence: tests/test_cli_session_migrate.py: test_run_recaptures_through_the_launcher_as_ended_sessions, test_recent_source_is_skipped_without_failing (172 passed)

대상 세션마다 가짜 실행기가 `capture --direct --normalized <파일> --rerender`를 받고, 훅 JSON 이벤트는 `SessionEnd`다. 프로젝트 폴더의 가장 최근 세션도 정규화 파일의 모든 교환이 `closed: true`다. 정규화 파일은 Vault 밖에 있었고 명령이 끝나면 없다. 실행 앞뒤로 Vault 폴더를 비교하면 가짜 실행기가 쓴 part 말고 바뀐 파일이 없다. 원본 수정 시각이 1시간 안인 세션은 `recent`이고 실행기 기록에 없으며 종료 코드는 0이다.

### A5. 두 번 돌려도 새 part가 생기지 않는다
- covers: I3, D8, F7
- check: tests/test_cli_session_migrate.py
- evidence: tests/test_cli_session_migrate.py: test_second_run_writes_nothing, test_uncovered_after_write_fails_and_is_not_written_again (172 passed)

첫 실행 뒤 같은 상태로 다시 돌리면 실행기 기록이 늘지 않고 Vault part 수가 같다. 가짜 실행기가 v1 범위를 덮지 못하는 part를 쓰게 하면 첫 실행은 `failed:uncovered`, 두 번째 실행은 `already_recaptured_uncovered`이고 실행기를 다시 부르지 않는다.

### A6. cwd가 없으면 상위 폴더를 넘기고, 다른 Vault에 쓰면 멈춘다
- covers: D6, I4, F3, F4
- check: tests/test_cli_session_migrate.py
- evidence: tests/test_cli_session_migrate.py: test_missing_cwd_falls_back_to_the_nearest_existing_parent, test_existing_cwd_is_passed_as_is, test_written_to_another_vault_stops_the_run (172 passed)

세션 cwd가 없는 폴더면 훅 JSON `cwd`는 가장 가까운 존재하는 상위 폴더이고, 정규화 파일의 세션 `cwd`는 원래 값이다. 출력에 `cwd_fallback=`이 있다. 가짜 실행기가 다른 Vault 이름을 내면 그 세션은 `failed:vault_mismatch`이고, 뒤의 세션은 실행기 기록에 없으며 종료 코드는 1이다.

### A7. 원본 없음은 보고만 하고, 고칠 수 없는 문제는 실패로 끝난다
- covers: D9, F1, F5, F8, F10
- check: tests/test_cli_session_migrate.py
- evidence: tests/test_cli_session_migrate.py: test_launcher_problems_fail_and_the_run_continues, test_missing_launcher_fails, test_duplicate_source_fails_without_running, test_unknown_vault_or_broken_map_runs_nothing, test_unreadable_v1_part_is_reported_and_its_session_is_not_recaptured, test_dry_run_lists_targets_and_writes_and_runs_nothing (source_missing, exit 0) (172 passed)

원본 없는 세션만 있으면 `source_missing`이 Vault 요약에 세어지고 종료 코드는 0이다. 같은 세션 id가 두 프로젝트 폴더에 있으면 `failed:duplicate_source`, 가짜 실행기가 `skipped`를 내거나 0이 아닌 코드로 끝나거나 실행기가 없으면 `failed:<이유>`이고, 다음 세션은 계속 돈 뒤 종료 코드 1이다. `vault-map.json`이 깨졌거나 `--vault` 이름이 없으면 실행기를 부르지 않고 종료 코드 1이다.

### A8. 사실 대기열이 바뀌지 않는다
- covers: D10
- check: tests/test_cli_session_migrate.py
- evidence: tests/test_cli_session_migrate.py: test_run_recaptures_through_the_launcher_as_ended_sessions, Graph Home facts/queue가 비어 있는지 확인함 (172 passed)

`written` 세션이 있는 실행 뒤에도 Graph Home `facts/queue/`에 작업 파일이 없고 사실 작업자를 띄우지 않는다.

### A9. 배치 규칙을 지키고 `vg session export --recapture`는 그대로다
- covers: D4
- check: tests/test_feature_import_direction.py, tests/test_functional_module_boundaries.py, tests/test_module_import_cycles.py, tests/test_grouped_module_layout.py, tests/test_cli_session_recapture.py, tests/test_cli_session_export.py
- evidence: uv run pytest -q tests/test_feature_import_direction.py tests/test_functional_module_boundaries.py tests/test_module_import_cycles.py tests/test_grouped_module_layout.py tests/test_cli_session_recapture.py tests/test_cli_session_export.py (A1·A2 테스트와 같이 실행): 172 passed in 4.84s. export·recapture 테스트 파일은 diff에 없음

`operation/sessions/v1_coverage.py`는 M01 밖의 기능 영역과 `interface/`를 가져오지 않는다. 기존 export와 `--recapture` 테스트는 고치지 않고 통과한다. 호환 범위 제한이다.

### A10. SPEC, 정규화 계약, ARCHITECTURE가 새 명령과 파일을 적는다
- covers: D11
- check: 수동: `docs/SPEC.md`의 `vg session export` 줄 근처, `docs/contracts/vg-session-jsonl-v1.md` §4, `docs/ARCHITECTURE.md` §1 파일 표와 §4 세션 수집 행에서 `vg session migrate`, `v1_coverage.py`, `session_migration.py`를 찾는다
- evidence: git diff HEAD~2 HEAD -- docs/SPEC.md docs/contracts/vg-session-jsonl-v1.md docs/ARCHITECTURE.md AGENTS.md: SPEC.md에 migrate 줄이 있음. 계약 §4.1에 형식, 덮음, 1시간 규칙, unreadable_part, 출력, 종료 코드가 있음. ARCHITECTURE §1 M19 행, 파일 표, §4 세션 수집 행에 명령과 두 파일이 있음. AGENTS.md diff는 없음

계약 §4에는 명령 형식, 덮음 규칙, 끝난 세션 정규화와 1시간 규칙, 출력, 종료 코드가 있다. AGENTS.md는 바뀌지 않았다.

### A11. 실제 실행 뒤 등록 Vault마다 원본 있는 세션의 덮이지 않은 v1 part가 0개다
- covers: D1, D12
- check: 수동: 구현 검증 뒤 `vg session migrate --dry-run`, `vg session migrate`, 다시 `vg session migrate --dry-run`을 차례로 돌리고 마지막 출력의 Vault 요약 줄을 본다
- evidence: 수동: main session이 실제 Vault에 돌린 결과를 인용함. `vg session migrate --dry-run`은 exit 0이고 target 53, source_missing 2였다. `vg session migrate`는 exit 0이고 53 written, 요약은 vault-graph 36/36/0, sgp-981-app 30/30/0, vault-builder 13/13/0, 981park-flutter-app 1/1/0, bake v1_parts=9 covered=7 uncovered=2 source_missing=2였다. 두 번째 `--dry-run`은 exit 0이고 bake의 source_missing 2세션만 남았다. 기존 세션 파일 388개는 실행 전 복사본과 바이트가 같았고 53개 파일이 새로 생겼다. 새 part 53개 모두 교환 수가 맞았다. 리뷰어가 실제 Vault에서 직접 재현하지는 않았다

마지막 dry-run에서 Vault 다섯 곳 모두 `uncovered`가 0이고, 남은 v1 part는 `source_missing`뿐이다(bake의 두 세션). 실제 실행에서 `written`인 세션은 모두 교환 수가 맞았다. 보고에는 Vault별 v1 part 수, 덮인 수, 원본 없음 수, 실패 세션과 이유를 조사 값(89개)과 함께 적는다. 실패가 남으면 그 세션과 이유를 적고 끝 조건을 채우지 못했다고 보고한다.

### A12. 실제 이전은 상위 spec의 다른 구현보다 먼저 끝난다
- covers: D12
- check: 수동: 이 change의 실제 실행 보고 시각이 3b~3e 구현 commit보다 앞서는지 git log와 보고로 확인한다
- evidence: 수동: git log --oneline main..HEAD 결과 c785d8b, dcf189d, fd21e3f, 6091e59만 있고 3b~3e 구현 commit은 없음. A11 실제 실행이 3b보다 먼저 끝났다는 main session 보고와 맞음

원본 보관 기한 때문에 사용자가 정한 시간 제한이다. 실행 보고가 나오기 전에 3b 이후 작업을 이 branch에 commit하지 않는다.

## 9. Open decisions

### O1. 끝 조건을 "v2가 덮지 않은 v1 part 0개"로 바꿔도 될까?
- decides: D1, D2

배경: 요청한 끝 조건은 "v1 part가 남지 않는다"였다. 그런데 Vault 도구는 이미 있는 세션 파일을 고치거나 지우지 않고, vg는 Vault `raw/`에 직접 쓰지 않는다. 그래서 다시 수집해도 옛 v1 파일은 그대로 남고 새 v2 파일이 옆에 생긴다. 색인은 이미 v2와 시간이 겹치는 v1 내용을 빼고 검색한다.

추천: 끝 조건을 "Vault마다, 원본이 있는 세션의 v1 part 중 같은 세션의 v2 part 하나가 시간 범위를 포함하지 않는 것이 0개"로 바꾼다. 원본이 없는 bake Vault의 두 세션은 셈에서 빼고 따로 보고한다. 파일을 지우지 않고도 사실 작업과 검색이 모든 세션을 v2로 보게 되기 때문이다.

답에 따라 바뀌는 것: "바꾼다"면 지금 spec대로다. "v1 파일도 없어야 한다"면 Vault 도구(vault-builder)에 v1 파일을 보관 폴더로 옮기거나 지우는 명령이 먼저 있어야 하고, 이 change는 그 명령이 생길 때까지 끝나지 않는다. "범위가 아니라 교환 단위로 덮음을 보라"면 v1 본문을 읽는 규칙이 더해져 구현이 커진다.

### O2. 지금 없는 worktree에서 돈 세션은 상위 폴더 기준으로 수집할까?
- decides: D6

배경: vault-graph Vault의 v1 세션 23개 중 7개는 지금은 지운 worktree 폴더(`.worktrees/feat-jh-local-graph` 등)에서 돌았다. Vault 도구는 세션 폴더로 저장할 Vault를 고르는데, 폴더가 없으면 "git 저장소 안이 아님"이라며 쓰지 않는다.

추천: 그 폴더에서 위로 올라가 처음 있는 폴더(보통 저장소 루트나 `.worktrees`)를 넘겨 Vault가 고르게 한다. 고른 Vault가 원래 v1 part의 Vault와 다르면 바로 멈춘다. 이 7세션을 빼면 vault-graph Vault만 해도 v1 part 상당수가 v2로 바뀌지 않는다.

답에 따라 바뀌는 것: "상위 폴더로"면 새 part의 `cwd` 칸에 원래 worktree가 아니라 상위 폴더가 적힌다. "건너뛴다"면 그 세션들은 `failed`로 남고 끝 조건을 채우지 못한다. "Vault를 직접 지정"이면 실행기와 Vault 도구에 Vault 지정 인자를 더하는 vault-builder 변경이 먼저 있어야 한다.

### O3. 새 명령 이름을 `vg session migrate`로 할까?
- decides: D3

배경: 지금 있는 `vg session export --recapture`는 사람이 고른 폴더에 세션 사본을 남기면서 다시 수집하고, 세션을 id나 날짜로만 고른다. 이번 일은 Vault의 옛 part를 읽어 대상 세션을 스스로 고른다.

추천: 새 하위 명령 `vg session migrate`로 둔다. 사본 폴더(`--out`)가 필요 없고, 목적이 "옛 형식을 새 형식으로 옮김"이라 이름이 그대로 드러난다.

답에 따라 바뀌는 것: 다른 이름이면 명령 이름과 문서만 바뀐다. "export에 `--only-v1` 같은 옵션으로"면 `--out` 폴더가 필수로 남아 실행할 때마다 원본 사본이 쌓이고, export의 기존 테스트와 출력에 손이 간다.

