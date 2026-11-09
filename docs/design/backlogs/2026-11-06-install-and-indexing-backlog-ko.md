---
type: design-backlog
id: INSTALL
status: proposed
priority: 일반
created: 2026-11-06
reviewed: 2026-11-09
base: main@3cd9baf
---

# 설치와 첫 색인 backlog

## 1. 목표

설치 명령이 색인하지 않도록 바꾼 작업(PR #27, v0.4.2)에서 남은 후속 과제를 정리한다. 첫 색인을 빠르게 만드는 일과,
색인하지 않은 상태에서 사용자가 보는 안내를 정확하게 만드는 일이 목표다.

범위는 `scripts/install.sh`, `vg setup`, `vg index`, 세션 시작 hook, MCP 도구의 복구 안내, 문서 청크 분할이다.
vault-builder 쪽 설치(`vault-builder setup`)와 MCP 서버의 검색 품질은 범위 밖이다.

## 2. 한눈에 보기

| ID | 제목 | 우선순위 | 상태 | 선행 |
| --- | --- | --- | --- | --- |
| INSTALL-03 | 이미 색인된 상태에서 다시 설치하면 `indexed: False`가 나온다 | 일반 | proposed | |
| INSTALL-04 | `--no-index` 안내가 MCP 설정 경로 안내를 가린다 | 일반 | proposed | |
| INSTALL-05 | MCP 도구와 상태 화면의 복구 안내가 색인 대상을 말하지 않는다 | 일반 | proposed | Open Decision 2 |
| INSTALL-07 | 부분 색인 상태의 hook 테스트가 변경 전에도 통과한다 | 권장 | proposed | |
| INSTALL-08 | spec에 조건이 맞지 않는 47분 측정이 남아 있다 | 권장 | proposed | |

## 3. 점검 이력

| 날짜 | base | 범위 | 결과 | 실행하지 못한 것 |
| --- | --- | --- | --- | --- |
| 2026-11-06 | main@9cf5e4d | PR #27 리뷰의 참고 발견 4건, 설치 e2e(Vault 사본 6개), 색인 속도 측정, 복구 안내 문구 검색 | 테스트 2,277개 통과. 설치 13초. Vault 하나 색인 25초 | 세션 원문을 뺀 상태의 색인 시간 측정 |
| 2026-11-09 | main@3cd9baf | 세션 기억 색인 작업(PR #29, v0.5.0) 뒤 열린 항목 7개를 코드와 보고서로 대조 | INSTALL-02 done, INSTALL-06 retired. INSTALL-03·04·05·08은 코드와 spec에 그대로 남아 있다 | INSTALL-07 재현(PR #27 이전 commit에서 테스트 실행) |

## 4. 일반

### INSTALL-03 이미 색인된 상태에서 다시 설치하면 `indexed: False`가 나온다
- [ ] proposed · 안내 · setup · 확인 2026-11-09
- 문제: [확인] `operation/runtime/setup_service.py`의 `SetupService.setup`은 `indexed=index_report is not None`으로
  보고한다. `--no-index`이면 기존 색인이 있어도 항상 `False`다.
- 영향: 다시 설치한 사용자가 색인이 지워졌다고 읽고, 필요 없는 전체 색인을 다시 돌릴 수 있다.
- 방향: 출력을 "이번 실행에서 색인했는가"와 "색인이 있는가"로 나누거나, `--no-index`일 때 `indexed: skipped`처럼
  다른 값을 쓴다.
- 완료: 색인된 Data Home에서 `vg setup --no-index`를 실행하는 테스트가 기존 색인이 있다는 출력을 확인한다.
- 출처: PR #27 리뷰 참고 발견

### INSTALL-04 `--no-index` 안내가 MCP 설정 경로 안내를 가린다
- [ ] proposed · 안내 · setup · 확인 2026-11-09
- 문제: [확인] `_setup_recovery_hint`는 `--no-index` 안내를 MCP 등록 실패 안내보다 먼저 반환한다. 두 조건이 함께
  맞으면 MCP 안내가 나오지 않는다.
- 영향: `--no-index`로 설치했는데 MCP 등록이 안 된 사용자가 MCP를 고치라는 안내를 보지 못한다.
- 방향: 해당하는 안내를 모두 반환하거나, MCP 등록 실패를 먼저 보여 준다.
- 완료: `register_mcp`가 켜져 있고 등록이 안 된 `--no-index` 실행에서 두 안내가 모두 나오는 테스트가 통과한다.
- 출처: PR #27 리뷰 참고 발견

### INSTALL-05 MCP 도구와 상태 화면의 복구 안내가 색인 대상을 말하지 않는다
- [ ] proposed · 안내 · mcp · 확인 2026-11-09
- 문제: [확인] 아래 위치는 아직 `Run vg index`만 안내한다. 인자 없는 `vg index`는 기본 Vault 하나만 색인한다.
  `operation/diagnostics/health_explorer.py`, `interface/mcp/mcp_resources.py`,
  `interface/mcp/metadata_resource_reader.py`, `interface/mcp/mcp_tools.py`의 `metadata_unavailable` 처리.
  [결정] PR #27에서는 이 안내를 바꾸지 않기로 했다.
- 영향: 설치 직후 MCP 도구를 쓴 사용자가 안내대로 `vg index`를 실행해도 다른 Vault는 계속 색인되지 않는다.
- 방향: Open Decision 2에서 고른 문구로 통일한다.
- 완료: 위 위치의 문구가 모두 바뀌고 관련 테스트가 새 문구를 확인한다.
- 선행: Open Decision 2
- 출처: PR #27 spec 범위 결정

## 5. 권장

### INSTALL-07 부분 색인 상태의 hook 테스트가 변경 전에도 통과한다
- [ ] proposed · 테스트 · hook
- 문제: [외부] PR #27 리뷰어가 수용 기준 A-7의 catch-up 테스트(`tests/test_cli_hook_session_start.py`)가 변경 전 코드에서도
  통과한다고 지적했다. 직접 재현하지 않았다.
- 영향: 부분 색인 상태의 hook 동작이 나중에 바뀌어도 테스트가 잡지 못할 수 있다.
- 방향: 변경 전 동작과 구분되는 단언을 더한다. 예를 들어 색인되지 않은 Vault 이름이 안내에 나오는지 확인한다.
- 완료: 테스트가 PR #27 이전 commit에서 실패하고 현재 commit에서 통과한다.
- 출처: PR #27 리뷰 참고 발견

### INSTALL-08 spec에 조건이 맞지 않는 47분 측정이 남아 있다
- [ ] proposed · 문서 · docs · 확인 2026-11-09
- 문제: [확인] `docs/specs/2026-11-05-install-without-index/spec.md`가 47분 측정을 근거로 쓴다. 이 값은 설치 두 개를
  동시에 돌린 측정이라 단독 실행 시간이 아니다. README는 이 값을 쓰지 않는다.
- 영향: 나중에 spec을 읽는 사람이 첫 색인 시간을 실제보다 길게 판단한다.
- 방향: spec의 해당 문장에 측정 조건을 적거나, INSTALL-02의 새 측정으로 바꾼다.
- 완료: spec의 시간 수치마다 측정 조건이 붙어 있다.
- 출처: PR #27 리뷰 참고 발견

## 6. 닫힌 항목

| ID | 제목 | 상태 | 날짜 | 근거 |
| --- | --- | --- | --- | --- |
| INSTALL-01 | 설치 명령이 모든 Vault를 색인해 수십 분 걸린다 | done | 2026-11-06 | PR #27, v0.4.2. 설치는 `vg setup --no-index`로 등록만 하고 마지막 줄에 `vg index --all-vaults`를 안내한다 |
| INSTALL-02 | 세션 원문 때문에 첫 색인이 수십 분 걸린다 | done | 2026-11-09 | PR #29, v0.5.0. Open Decision 1은 "세션 원문만 다른 청크 규칙"으로 정해졌다(spec 2026-11-05-session-memory-indexing). 세션 파일은 교환 단위 청크(`session-exchange-v1`, `session-exchange-v2`)로 나뉜다. 모든 Vault의 세션 청크가 28,330개에서 8,763개로 69% 줄었고, Graph Home 사본 전체 재색인이 463초에서 326초로 줄었다(보고서 2026-11-session-recall, 2026-11-embedding-memory). session-start recall 테스트가 통과한다 |
| INSTALL-06 | 색인 전 `remember`가 Vault 전체 색인을 시작한다 | retired | 2026-11-09 | 이 항목의 방향대로, INSTALL-02로 전체 색인이 약 5분 반으로 줄어 그대로 둔다. 백그라운드 색인은 결과를 기다리지 않고 실패해도 쓰기가 성공으로 남는다(`mcp_memory_tools.py`의 `_index_after_publish`). 시간이 다시 길어지면 같은 ID로 다시 연다 |

## 7. Open Decisions

| # | 질문 | 선택지 | 권장 |
| --- | --- | --- | --- |
| 2 | 복구 안내를 어떤 명령으로 통일할 것인가 | `vg index --all-vaults` / 문제가 된 Vault만 `vg index --vault-id <id>` | 문제가 된 Vault를 아는 곳은 `--vault-id`, 모르는 곳은 `--all-vaults`를 쓴다. 필요한 Vault만 색인해 시간이 짧다 |
