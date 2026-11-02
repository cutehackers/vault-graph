## id

8

## title

[vault-builder] B5a. 계약6의 훅 실행기 asset `vault_hooks.py`(`session-start`, `capture`, `capture --direct`)를 만든다

## goal

vg가 있으면 vg가 세션 시작 회상과 수집을 맡고, vg가 없거나 실패해도 Claude Code 세션을 막지 않고 대화 원문이 저장된다. spec Intent 5를 다룬다.

## files

저장소: vault-builder (`$HOME/workspace/vault-builder`, 브랜치 `feat/jh/vault-graph-requests`)

- `tools/vault_migration/assets/vault-hooks/vault_hooks.py` (새 파일)
- `builder_tests/test_vault_hooks_launcher.py` (새 파일)

## blockers

없음

## acceptance

A-16 (실행기 항목: vg 없음, 실패, 시간 초과에서 종료 코드 0)

## checks

`$HOME/workspace/vault-builder`에서 실행한다.

- `python3 -m unittest builder_tests.test_vault_hooks_launcher`
- `WIKI_GATE_FULL=1 bash scripts/release_gate.sh`
- `python3 -m unittest builder_tests.test_llm_wiki_router`

## done-when

- [ ] 시작 전에 Claude Code 훅 문서와 실제 PreCompact·SessionEnd 훅 입력을 파일로 떠서 `transcript_path`, `cwd`, `session_id`, `hook_event_name`을 확인했다(위험1)
- [ ] vg를 `VAULT_GRAPH_BIN`, `$HOME/.claude/vault-builder/vault-hooks.json`의 `vg`, `PATH` 순으로 찾는다
- [ ] `session-start`는 vg가 0으로 끝나면 그 출력을, 아니면 `recall.sh` 출력을 내보낸다
- [ ] `capture`는 vg가 0이 아니거나 없으면 `capture --direct`를 한다
- [ ] vg 없음, vg 실패, vg 시간 초과에서 모두 종료 코드 0이다
- [ ] `capture --direct`의 Vault 선택이 `tools/wiki/lib/session_capture.py:431-479`와 같다는 것을 같은 표 테스트로 묶었다(위험7)

멈춤: 실제 훅 입력에 `transcript_path`나 `cwd`가 없으면 보고한다.
