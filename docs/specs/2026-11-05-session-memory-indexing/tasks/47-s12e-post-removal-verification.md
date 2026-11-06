## id
47

## title
S12e 요청S11 반영 뒤 vg 경로 회상 확인

## goal
대체 경로가 사라진 뒤에도 vg 회상이 그대로 나온다. (Intent 6)

## spec
§4.4.9 이주6, §6 마지막 행

## acceptance
A-30(제거 뒤), A-29(S12), A-34

## files
- docs/design/reports/2026-11-legacy-removal-verification.md (신규)

## blockers
1, 46, 요청S11(외부, 필수)

## checks
vault-builder 저장소 `git log` 경로 필터와 `pytest tests/test_session_recall.py tests/test_cli_hook_session_start.py -q`

## wave
17

## done-when
- [ ] S8~S11 동안 vault-builder 쪽 변경이 요청S4·S9 범위뿐이었음을 `git log`로 확인했다
- [ ] 제거 뒤 vg 경로 회상이 그대로 나온다
- [ ] `git log main..feat/jh/session-memory-indexing`의 모든 커밋에 `Co-Authored-By`가 없다(0건)
- [ ] vault-graph pytest 전체 통과, 독립 커밋

## notes
이 task는 마지막 wave다. 요청S11이 없으면 시작할 수 없다.
