## id
8

## title
S4b `vg session export`, export 설정, Codex 계약 문서

## goal
원본 보존이 시작된다. 사용자가 정한 Vault 밖 경로에 원본 사본과 정규화 파일이 남는다. (Intent 1)

## spec
§4.2.3, §4.2.4, §6 export 행

## acceptance
A-2, A-11(계약 문서 부분)

## files
- src/vault_graph/operation/scope/session_export_settings.py (신규)
- src/vault_graph/interface/composition/adapters/session_export_files.py (신규)
- src/vault_graph/interface/cli/session_commands.py (신규)
- src/vault_graph/interface/cli/main.py
- docs/contracts/vg-session-jsonl-v1.md (신규)
- tests/test_session_export_settings.py (신규)
- tests/test_cli_session_export.py (신규)

## blockers
1, 5

## checks
pytest tests/test_session_export_settings.py tests/test_cli_session_export.py tests/test_feature_import_direction.py -q

## wave
3

## done-when
- [ ] `--out`이 Vault 안이면 파일 0개에 0이 아닌 종료 코드이고, git 작업 트리 안이면 경고 한 줄이다
- [ ] 원본 사본 sha256이 같고 권한이 0700·0600이며, 같은 세션 재실행은 파일을 다시 쓰지 않는다(mtime 유지)
- [ ] `--agent codex`는 "adapter 없음" 오류다
- [ ] 4.2.3 필드 대응표가 계약 문서에 있다
- [ ] vault-graph pytest 전체 통과, 독립 커밋

## notes
`main.py`는 이 task만 쓴다(#29는 wave 9에서 이후 수정). #10의 `vg status` 안내는 `index_status_reader.py`에 둔다.
