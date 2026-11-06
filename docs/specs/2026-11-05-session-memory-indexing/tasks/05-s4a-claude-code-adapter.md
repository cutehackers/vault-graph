## id
5

## title
S4a M19 Claude Code adapter, 정규화 JSONL `vg-session-jsonl/1`, 가림 규칙

## goal
원본 jsonl을 사람 턴, 도구 대상, 성공 여부가 있는 공통 형식으로 결정적으로 바꿀 수 있다. (Intent 1, 2)

## spec
§4.2.2, §6 M19 행, 위험A2, 위험A8

## acceptance
A-1, A-32(M19 `_AREAS`)

## files
- src/vault_graph/operation/sessions/__init__.py (신규)
- src/vault_graph/operation/sessions/models.py (신규)
- src/vault_graph/operation/sessions/claude_code_adapter.py (신규)
- src/vault_graph/operation/sessions/redact.py (신규)
- src/vault_graph/operation/sessions/normalized_jsonl.py (신규)
- tests/test_feature_import_direction.py
- tests/test_session_claude_code_adapter.py (신규)
- tests/test_session_redact.py (신규)
- tests/fixtures/session_adapter/ (신규, 폴더 전체)

## blockers
1 (A-34 커밋 순서)

## checks
pytest tests/test_session_claude_code_adapter.py tests/test_session_redact.py tests/test_feature_import_direction.py tests/test_module_import_cycles.py -q

## wave
2

## done-when
- [ ] 고정 원본 3개(`turnOrigin` 있음·없음, 서브에이전트·압축 포함)의 결과가 기대 파일과 바이트 단위로 같고 두 번 돌려도 같다
- [ ] `task_notification`, `isMeta`, `isCompactSummary`가 사람 턴이 아니고, `Edit`, `Bash`, `WebFetch`의 `target`과 `ok`, `error_head`가 맞다
- [ ] 고정 비밀값이 `text`, `commands`, `error_head`에 남지 않고, Vault 가림 규칙과 같은 표 테스트가 통과한다
- [ ] `_AREAS`와 `_ALLOWED`에 M19 한 줄씩, `_KNOWN_VIOLATIONS`는 빈 집합
- [ ] vault-graph pytest 전체 통과, 독립 커밋

## notes
M19는 M01만 가져올 수 있고 순수 코드다. 파일 읽기·쓰기는 #8의 composition 어댑터가 한다. `test_feature_import_direction.py`는 이 task만 쓴다.
