## id
46

## title
S12d 대체 경로 제거를 사람이 한 번 더 확인하는 게이트

## goal
vg가 없는 사용자의 회상과 정리 상실을 알고도 제거를 진행할지 사람이 정한다. 이 확인 전에는 요청S11이 반영되지 않는다. (Intent 6)

## spec
§4.4.9, 위험D8

## acceptance
A-30(확인 기록)

## files
- docs/design/reports/2026-11-legacy-removal-confirmation.md (신규)

## blockers
1, 40, 43, 사람 확인(필수)

## checks
해당 없음(사람 결정 기록). 근거로 #40 보고서의 지표1·2 값을 인용한다.

## wave
16

## done-when
- [ ] 확인 기록에 지표1·2가 0이라는 근거와 사람의 결정(진행 또는 보류)과 날짜가 있다
- [ ] 사람이 승인하기 전에는 요청S11을 내지 않는다는 점을 기록했다
- [ ] vault-graph pytest 전체 통과, 독립 커밋

## notes
사람 확인 gate다. 에이전트는 승인을 대신하지 않는다. 승인 질문은 결정 한 줄, 배경, 바뀌는 점(제거 뒤 vg 없는 사용자는 회상과 정리를 받지 못함), 위험, 옵션 순서로 한다. 제거 대상은 `memory-cleanup`, `maps build` 프로젝트 요약, `recall.sh`, `/project-memory`이고 구현은 vault-builder 쪽이다. vg 코드는 지우지 않는다.
