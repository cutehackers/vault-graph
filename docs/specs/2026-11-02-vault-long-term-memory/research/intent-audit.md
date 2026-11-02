# 최초 의도 기준 검수 (2026-11-02)

작업 1~23을 마친 뒤, 사용자 요청으로 독립 에이전트가 spec이 아니라 최초 의도(§0 규칙1~5)를 기준으로 구현을 다시 검수했다. 임시 HOME에 vault-builder로 만든 Vault, 실제 `vg`와 `vg serve --mcp`로 확인했다.

## 반드시 고칠 것

| 번호 | 저장소 | 어긋난 의도 | 문제 | 처리 |
|---|---|---|---|---|
| F1 | vault-graph | 규칙4 | 저장한 기억이 `vg index`를 돌리기 전까지 회상·검색에 없다. 어떤 훅도 색인하지 않는다. E2E는 쓰기마다 `vg_index()`를 불러 이 문제를 가렸다. | 세션 시작 훅이 연결 Vault의 바뀐 파일 메타데이터를 갱신하고, 발행 직후 그 Vault를 백그라운드로 색인한다. 고침: `99324d1`(발행 뒤 색인), `d2565d1`(세션 시작 갱신) |
| F2 | vault-graph | 규칙1·4 | frontmatter YAML이 깨진 파일 하나가 `vg setup`·`vg index` 전체를 멈춘다. Vault 파서는 그 파일을 받아들인다. | 파일 하나는 경고로 넘기고 다음 Vault로 계속한다. 고침: `12a7a15` |
| F3 | vault-graph | 규칙4 | `## 기억 목록`이 index·log·map·overview 페이지로 채워진다. | 구획B에서 이 type 페이지를 뺀다(종류 이름이 아니라 페이지 type 기준). 고침: `d2565d1` |
| F4 | vault-graph | 규칙1·4 | `find_related` 등 다섯 도구가 활성 Vault만 읽는다. 이 컴퓨터에서는 다른 프로젝트 Vault다. | 선택 입력 `cwd`와 검색과 같은 범위 규칙. 고침: `99324d1` |
| F5 | vault-graph | 규칙2·4 | Claude Code에 vault-graph MCP를 등록하는 길이 없다(`--agent codex`만). | `--agent claude` 등록과 README 안내. 고침: `44e23ca` |
| F6 | vault-builder | 규칙1·3 | `install`이 항상 role `personal`로 넣어, project Vault가 없으면 원문 수집이 조용히 건너뛴다. | `install --role`, 설치 안내, project Vault가 없을 때 `link` 경고. 고침: vault-builder `e8a05d7` |
| F7 | vault-graph | 규칙1 | 쓰기 도구가 `cwd`를 안 받으면 프로젝트를 무시해, 다른 프로젝트 Vault에 쓸 수 있다. | 검색 도구처럼 서버 작업 폴더를 기본값으로 쓴다. 고침: `99324d1` |

## 다음 작업으로 넘길 것

| 번호 | 저장소 | 문제 | 처리 |
|---|---|---|---|
| F8 | vault-graph | 쓰기 도구 스키마에 허용 값과 설명이 없다(실제 세션에서 첫 호출이 거부됨). | 이번에 함께 고친다(Literal enum, 도구 설명). 고침: `99324d1` |
| F9 | vault-builder | personal+project를 연결한 프로젝트는 기본 저장 Vault가 없어 첫 쓰기가 `vault_required`다. | 다음 작업 |
| F10 | vault-graph | 고정 기억의 summary가 제목과 같아 내용이 회상에 안 들어간다. | 다음 작업 |
| F11 | vault-graph | 대기 중인 추론 제안 수를 어디서도 보여 주지 않는다. | 다음 작업 |
| F12 | vault-graph | Vault 이름표가 검색에만 붙고 `ask_vault` 등에는 없다. | 다음 작업 |
| F13 | 설치 | 훅의 vg 경로가 worktree의 `.venv`를 가리킨다. | 병합 뒤 고정 경로의 vg로 다시 설치 |

## 의도대로 확인된 것

- 기억은 Vault에만 있고 vault-graph는 Vault 파일을 직접 쓰지 않는다(draft는 OS 임시 폴더, E2E A-6 해시 비교).
- 말한 사실은 Vault 검사를 거쳐 발행되고, 추론한 사실은 검토 대기열에서 기다린다(E2E A-2, A-3).
- 원문 저장은 Vault `sessions capture`가 하고 vault-graph는 실행 시점만 정한다(E2E A-4).
- 정해진 예산 안의 회상, 고정 기억 먼저(E2E A-1).
- Graph Home을 지우고 다시 만들어도 회상·검색이 같다(E2E A-6). 사용 기록은 순서에 영향을 주지 않는다.
- 가져오기 방향 예외 0, 순환 0.
