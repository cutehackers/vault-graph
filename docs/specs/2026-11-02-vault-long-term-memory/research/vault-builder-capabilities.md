# vault-builder와 Vault 도구가 지금 할 수 있는 일

조사 기준: vault-builder `feat/jh/vault-graph-requests` f562d77. 경로는 vault-builder 저장소 기준이다.

## 1. 페이지 쓰기 (draft 연산)

- 있음: `upsert-page`, `patch-page`, `batch-upsert-pages` (`tools/wiki/lib/draft.py:204-236`).
- 기존 페이지 수정: 있음. upsert-page는 덮어쓴다. 사람이 잠근 페이지나 잠긴 절이 바뀌면 거부한다 (`draft.py:63-70`). claim 행을 `remove_claims` 없이 빼면 거부한다 (`draft.py:302-324`).
- patch 연산: `append-claim`, `supersede-claim`, `set-claim-status`, `replace-section`, `append-to-section` (`tools/wiki/lib/draft_patch.py:26-32`).
- 폐기: 부분. 페이지 status는 `seed|active|stable|contested|deprecated` (`tools/wiki/lib/schema.py:49`). deprecated면 `superseded_by`가 필수 (`tools/wiki/lib/lint.py:433-441`). 대체 없는 폐기 방법이 없다.
- 저장소 전체 lint가 이미 깨져 있으면 publish-draft는 거부하고 종료 코드 1 (`tools/wiki/cli.py:705-714`). 적용 후 lint가 깨지면 원래 파일로 되돌린다 (`cli.py:726-733`).
- 출력은 텍스트뿐이다. JSON 출력과 `--vault` 옵션이 없고, 대상은 그 `cli.py`가 들어 있는 Vault다 (`cli.py:10`).

## 2. 검토 대기열

- CLI: `review create|list|resolve` (`cli.py:126-142`). 저장 위치 `scratch/review/<id>.md` (`tools/wiki/lib/review.py:49`).
- 유형은 `contradiction|merge|contested-claim|human-lock`, 상태는 `pending|accepted|rejected|resolved` (`review.py:15-17`).
- 없음: draft를 붙인 검토 항목, 승인 시 wiki 반영. resolve는 상태만 바꾸고 로그를 남긴다 (`review.py:241-268`).

## 3. sessions capture

- 있음 (`cli.py:189-204`, `tools/wiki/lib/session_capture.py`). 옵션 `--transcript --session-id --cwd --trigger --vault --json`. trigger는 `PreCompact|SessionEnd|manual`.
- 훅 모드는 stdin 훅 JSON을 읽고 항상 종료 코드 0이다 (`session_capture.py:374-375, 401-410`).
- 대상: 프로젝트에 연결된 role=`project` Vault가 정확히 하나여야 하고, contract 3 이상이어야 한다 (`session_capture.py:431-478`).
- 같은 세션을 다시 불러도 새 턴만 새 part 파일로 덧붙인다. 기존 파일은 덮어쓰지 않는다 (`session_capture.py:482-598`).

## 4. vault-map.json

- 위치 `<config>/vault-builder/vault-map.json`. version 2: `vaults{name:{path,role}}`, `projects{id:{root,vaults[],remote?}}`.
- 읽는 곳: router (`tools/vault_migration/assets/llm-wiki-router/llm_wiki_router.py:93-131`), `tools/wiki/lib/memory_scan.py`, recall.sh. 쓰는 곳: `tools/vault_migration/installing.py:352-390`, `tools/vault_migration/linking.py:60-72`.
- role은 아무 문자열이나 허용되고, 문서상 personal/team/project다 (`docs/usage.md:721-731`). install은 항상 personal로 추가한다 (`installing.py:372`). role을 바꾸는 CLI가 없다.
- 없음: 기본 저장 Vault 필드, 외부 계약 문서화.

## 5. 훅 설치

- 없음. install은 스킬, recall.sh, router, map, MCP 항목만 넣는다 (`installing.py:319-397`).
- recall.sh는 `tools/vault_migration/assets/project-memory/scripts/recall.sh`이며, 프로젝트 맵의 세 절을 약 1,500토큰 안에서 출력한다.

## 6. frontmatter

- 필수 필드 `schema.py:8-28`, type 목록 `schema.py:30-47`(decision, system 포함).
- 없음: 스키마 버전, `pin`, `memory_kind`. 세션 파일에만 `vault-session/v1`이 있다 (`tools/wiki/lib/session_archive.py:16`).

## 7. 갱신할 HTML 문서

- `docs/html/project-memory-structure.html`: 작업 중 말한 것이 다음 세션 기억이 되는 흐름. SessionStart 훅 단계가 "새로" 표시로 남아 있다.
- `docs/html/vault-roadmap.html`: 약점과 제안 1~13, 결정. 결정2는 "vault-graph는 vault-map을 읽기만 한다".
- `docs/html/vault-structure-map.html`: Vault 구조와 여러 Vault 규칙. "vault-map.json이 Vault를 잇는 유일한 파일".

## 8. 검증

- `bash scripts/release_gate.sh` (단위 테스트, lint, health, maps check, metrics check, sessions git-check). `WIKI_GATE_FULL=1`이면 캐시 없이 전부 실행한다.
- `builder_tests/test_llm_wiki_router.py`는 gate 밖이라 따로 실행한다: `python3 -m unittest builder_tests.test_llm_wiki_router`.
