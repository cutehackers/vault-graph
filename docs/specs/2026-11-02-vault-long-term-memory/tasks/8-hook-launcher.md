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

- [x] 시작 전에 Claude Code 훅 문서와 실제 PreCompact·SessionEnd 훅 입력을 파일로 떠서 `transcript_path`, `cwd`, `session_id`, `hook_event_name`을 확인했다(위험1)
- [x] vg를 `VAULT_GRAPH_BIN`, `$HOME/.claude/vault-builder/vault-hooks.json`의 `vg`, `PATH` 순으로 찾는다
- [x] `session-start`는 vg가 0으로 끝나면 그 출력을, 아니면 `recall.sh` 출력을 내보낸다
- [x] `capture`는 vg가 0이 아니거나 없으면 `capture --direct`를 한다
- [x] vg 없음, vg 실패, vg 시간 초과에서 모두 종료 코드 0이다
- [x] `capture --direct`의 Vault 선택이 `tools/wiki/lib/session_capture.py:431-479`와 같다는 것을 같은 표 테스트로 묶었다(위험7)

멈춤: 실제 훅 입력에 `transcript_path`나 `cwd`가 없으면 보고한다.

기록 (2026-11-02, vault-builder `git log --grep "B5a"`): 실행기 테스트 22개와 router 테스트 70개 통과. done-when 1(위험1): 실제 Claude Code 2.1.316의 SessionEnd·PreCompact 훅 입력을 파일로 떴다. `$HOME/.claude/settings.json`은 건드리지 않고, 임시 설정 파일을 `claude -p --setting-sources project --settings <임시 파일>`로 넘겨 받았다(PreCompact는 같은 세션을 `--resume`한 뒤 `/compact`). 두 입력 모두 `session_id`, `transcript_path`, `cwd`, `hook_event_name`이 있고 `transcript_path` 파일이 실제로 있었다. PreCompact는 `trigger`, `custom_instructions`, SessionEnd는 `reason`이 더 있다. 기록: `research/hook-input-capture.json`. 작업 9가 챙길 것: 설치 때 `llm_wiki_router.py`를 실행기와 같은 폴더에 복사한다(작업 9에서 반영됨).
