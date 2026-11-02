## id

6

## title

[vault-builder] B3. 계약4. 검토 유형 `memory-proposal`, `review propose`, 승인 시 발행을 만든다

## goal

에이전트가 추론한 사실이 사람이 승인할 때까지 `scratch/review/`에 대기하고, 승인하면 계약1로 발행된다. spec Intent 3을 다룬다.

## files

저장소: vault-builder (`$HOME/workspace/vault-builder`, 브랜치 `feat/jh/vault-graph-requests`)

- `tools/wiki/lib/memory_proposal.py` (새 파일, `propose(...)`, `accept(...)`)
- `tools/wiki/lib/review.py` (`ALLOWED_REVIEW_TYPES`, `validate_review_queue`)
- `tools/wiki/cli.py` (`review propose`, `review resolve`의 `memory-proposal` 분기)
- `tests/test_memory_proposal.py` (새 파일)

## blockers

3, 4, 5

## acceptance

A-14, A-21

## checks

`$HOME/workspace/vault-builder`에서 실행한다.

- `python3 -m unittest tests.test_memory_proposal tests.test_wiki_tools tests.test_wiki_lib_import_direction`
- `WIKI_GATE_FULL=1 bash scripts/release_gate.sh`
- `python3 -m unittest builder_tests.test_llm_wiki_router`

## done-when

- [x] `review_id`가 `<날짜>-memory-<draft sha256 앞 8자>`이고, 요약만 다른 한국어 제안 두 개가 서로 다른 id를 받는다
- [x] 검토 항목에 `draft`, `target_path`, `target_hash`가 있고, `--json` 출력이 `vault-review-result/v1` 형식이다
- [x] 다섯 경우를 각각 테스트한다: 검증 실패 시 파일 0개, 승인 성공, `target_hash` 불일치로 거부, 발행 거부 시 `pending` 유지, `rejected` 시 wiki 무변경
- [x] lint가 `memory-proposal` 항목의 `draft` 파일이 `scratch/review/` 아래에 있는지 확인한다
- [x] 다른 검토 유형의 `resolve` 동작과 기존 테스트가 그대로다
- [x] `review.py`는 `memory_proposal`을 가져오지 않는다

멈춤: `apply_draft(dry_run=True)`가 파일을 쓰면 보고한다.

기록 (2026-11-02, vault-builder `git log --grep "B3"`): `tests.test_memory_proposal` 16개 통과, 방향 테스트의 memory_proposal 규칙이 이제 실행된다. `rejected`는 기존 resolve처럼 `wiki/log.md`에 한 줄을 남긴다(spec 159행 "지금처럼"). 같은 날 같은 draft 재제안은 거부한다. `review resolve --json`의 필드는 spec에 없어 `status`/`review_status`/`reason`으로 정했다.
