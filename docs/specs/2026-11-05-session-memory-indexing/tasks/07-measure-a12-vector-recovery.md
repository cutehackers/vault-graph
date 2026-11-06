## id
7

## title
측정 A-12: 실제 Graph Home에서 `vg index` 성공 확인

## goal
#1이 실제 컬렉션(33,065개)에서 통하는지 확인한다. (Intent 5)

## spec
§8.2 A-12 측정, 위험B1

## acceptance
A-12(측정)

## files
- docs/design/reports/2026-11-vector-index-recovery.md (신규)

## blockers
1

## checks
`vg index --vault-id vault-graph` 실행 로그와 `vector/manifest.json` revision 변화 (사람이 실행)

## wave
2

## done-when
- [ ] 사람이 이 컴퓨터에서 실행했고 revision이 바뀌었다
- [ ] 보고서에는 합계만 적었다(세션 내용과 홈 경로 없음)
- [ ] vault-graph pytest 전체 통과, 독립 커밋

## notes
사람 컴퓨터의 실제 Graph Home이 필요하다. 에이전트는 보고서 틀만 준비한다.
