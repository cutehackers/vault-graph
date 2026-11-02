## id

23

## title

[두 저장소, 수동] G9. 실제 Claude Code 세션 하나로 수동 확인한다

## goal

사용자 컴퓨터의 실제 세션에서 고정 회상, 기억 쓰기, 제안 대기, 원문 수집, 검색 표시가 동작함을 확인한다. spec Intent 1~6, 결정7을 다룬다.

## files

저장소 파일은 쓰지 않는다. 사용자 컴퓨터에서 바뀌는 곳은 다음과 같다.

- `$HOME/.claude/settings.json` (훅 항목)
- `$HOME/.claude/vault-builder/` (`vault_hooks.py`, `vault-hooks.json`)
- project Vault `$HOME/vaults/vault-graph` (`wiki/`, `scratch/review/`, `raw/sessions/`)

## blockers

9, 11, 21, 22

## acceptance

A-7, 위험2, 위험3, 위험10

## checks

수동 작업이다.

- 사용자 확인을 받은 뒤 `$HOME/workspace/vault-builder`에서 `install --with-hooks`를 실행한다
- 실제 Claude Code 세션 하나에서 A-7의 다섯 항목을 확인한다
- 긴 세션을 끝낸 뒤 `$HOME/vaults/vault-graph/raw/sessions/`의 part 파일 수를 센다(위험2)

## done-when

- [x] `$HOME/.claude/settings.json` 훅 설치 직전에 사용자 확인을 한 번 더 받았다(2026-11-02 spec 승인 조건)
- [x] 세션 시작 문맥에 `## 고정 기억`이 있다(위험3)
- [x] 사실 하나를 기억하라고 말하면 Vault에 페이지가 생긴다
- [x] 추론 사실 하나가 `scratch/review/`에 대기한다
- [x] 세션을 끝내면 `raw/sessions/`에 원문 파일이 생긴다
- [x] 검색 결과에 Vault 이름·종류가 붙는다
- [x] 비밀값을 뺀 결과 요약을 vault-graph PR 설명용으로 사용자에게 전달했다

멈춤: 사용자 확인이 없으면 설치하지 않는다. 다섯 항목 중 하나라도 실패하면 고치지 않고 보고한다.

기록 (2026-11-02, 실제 세션 확인):
- 사용자 확인: 작업 23 진행, project Vault 계약 4 마이그레이션, 잘못 생긴 map 항목 "v" 삭제를 각각 확인받았다.
- 준비: `$HOME/vaults/vault-graph`를 audit → apply로 계약 4로 올렸다(교체 15, 생성 8, 검토 필요 0, lint 통과). `install --with-hooks`를 python 3.12로 실행해 훅 세 개만 더했다(llm-wiki MCP 항목은 그대로). vg 경로는 이 worktree의 `.venv/bin/vg`다. Graph Home은 `vg vault add vault-graph` 뒤 `vg index`로 만들었다.
- 세션1(`claude -p`, 프로젝트 루트, vault-graph MCP는 `--mcp-config`로만 전달): stated 고정 규칙이 `wiki/systems/live-checks-run-from-the-project-root.md`로 발행됐다(`pin: true`, `memory_schema: vault-memory/v1`). inferred 선호는 `scratch/review/2026-11-02-memory-d7ae10a8.md`에 `proposed`로 대기했다. 범위 없는 검색 결과마다 `vault_name: vault-graph`, `vault_role: project`가 붙었다. 세션이 끝나자 `raw/sessions/claude-code/2026-11-02-b7b7a3c6-...-part1.md`가 생겼다(짧은 세션이라 part 1개, 위험2).
- 세션2: `vg index` 뒤 새 세션 시작 문맥 첫 절이 `## 고정 기억`이고 위 규칙이 들어 있었다. 대기 중인 inferred 사실은 회상에 없었다.
- 발견: (1) `remember`의 `kind`는 decision/system만 받는데 도구 스키마가 허용 값을 보여 주지 않아 첫 호출이 거부됐다. (2) 발행한 기억은 `vg index` 전에는 검색·회상에 없다. (3) `vg setup`이 personal Vault의 frontmatter YAML 오류 파일 하나(`raw/imports/claude-memory/sgp-981-app--hub-screen-term--de6d0dcb.md`) 때문에 전체가 멈춰 personal Vault는 색인하지 못했다. (4) 작업 10 구현 중 테스트가 실제 `vault-map.json`에 항목 "v"를 남겼고, 백업 뒤 지웠다.
