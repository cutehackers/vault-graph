## id

11

## title

[vault-builder] B7. vault-builder 설계 문서를 구현에 맞춘다

## goal

vault-builder 문서가 구현된 계약1~7을 같은 내용으로 설명한다. spec Intent 8을 다룬다.

## files

저장소: vault-builder (`$HOME/workspace/vault-builder`, 브랜치 `feat/jh/vault-graph-requests`)

- `docs/html/project-memory-structure.html`
- `docs/html/vault-roadmap.html`
- `docs/html/vault-structure-map.html`
- `docs/superpowers/specs/2026-10-29-vault-graph-requests-ko.md`

## blockers

2, 3, 4, 5, 6, 7, 8, 9, 10

## acceptance

A-26, A-21 (건너뛴 방향 규칙 0건), A-24

## checks

`$HOME/workspace/vault-builder`에서 실행한다.

- `python3 -m unittest tests.test_wiki_lib_import_direction` (건너뛴 규칙 출력이 없어야 함)
- `WIKI_GATE_FULL=1 bash scripts/release_gate.sh`
- `python3 -m unittest builder_tests.test_llm_wiki_router`

## done-when

- [ ] `project-memory-structure.html`의 SessionStart 훅 "새로" 표시가 `--with-hooks` 선택 항목 설명으로 바뀌고, PreCompact·SessionEnd 수집 흐름과 추론 제안 → 승인 흐름이 있다
- [ ] `vault-roadmap.html`에서 요청3~6과 계약3·계약4가 구현됨이고, `retired` 상태가 있고, 결정2("vault-graph는 vault-map을 읽기만 한다")가 유지된다고 적혀 있다
- [ ] `vault-structure-map.html`에 `default_write_vault`, role 값(personal, project, team, 그 밖), `set-role`, `set-default-write`가 있다
- [ ] 요청 문서의 각 요청 상태 열이 갱신되어 있다
- [ ] 방향 검사가 건너뛰는 규칙이 없다

멈춤: 문서에 적을 동작이 구현과 다르면 문서를 구현에 맞추지 말고 보고한다.
