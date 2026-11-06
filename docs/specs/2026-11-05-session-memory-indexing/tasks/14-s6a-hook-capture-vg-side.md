## id
14

## title
S6a 수집 훅 연결(vg 쪽): `vg hook capture`의 정규화와 `--normalized` 전달, `--recapture`

## goal
세션 끝마다 정규화 파일이 만들어져 Vault 도구에 넘어간다. 요청S10이 없으면 v1으로 돌아간다. (Intent 1, 2)

## spec
§4.2.4 recapture, §4.2.5 수집 흐름, §4.2.12-5, §6 수집 행

## acceptance
A-3(vg 쪽), A-37(vg 쪽)

## files
- src/vault_graph/interface/cli/hook_commands.py
- src/vault_graph/interface/cli/session_commands.py
- src/vault_graph/interface/composition/adapters/session_capture_runner.py (신규)
- tests/test_cli_hook_capture_normalized.py (신규)
- tests/test_cli_session_recapture.py (신규)

## blockers
1, 5, 8, 요청S10(외부, E2E는 #25에서)

## checks
pytest tests/test_cli_hook_capture_normalized.py tests/test_cli_session_recapture.py tests/test_cli_hook_capture.py -q

## wave
4

## done-when
- [ ] 정규화 실패와 종료 코드 2에서 `capture --direct` 원본 경로로 돌아가고, 종료 코드는 지금 규칙(0 또는 3)을 따른다
- [ ] export 설정이 있으면 같은 실행에서 export가 되고, 경로가 없어지면 export만 건너뛰며 경고 한 줄이다
- [ ] `--rerender`는 `vg session export --recapture`에서만 붙는다
- [ ] vault-graph pytest 전체 통과, 독립 커밋

## notes
요청S10 전에는 가짜 실행기로 모든 vg 쪽 분기를 단위 테스트할 수 있다. 실제 Vault 도구와의 E2E는 #25.
