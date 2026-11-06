## id
12

## title
측정 A-18: 증분 run 디스크 증가량

## goal
clone 세대 준비로 증분 run이 늘리는 디스크가 약 650MB에서 50MB 이하로 줄었는지 확인한다. (Intent 5)

## spec
§4.3.3, §8.2 A-18 측정

## acceptance
A-18(측정)

## files
- docs/design/reports/2026-11-incremental-disk-cost.md (신규)

## blockers
1, 3, 4

## checks
`du` 전후 로그 (사람이 실행)

## wave
3

## done-when
- [ ] 증분 run 하나가 늘린 디스크 사용량이 50MB 이하로 기록됐다
- [ ] vault-graph pytest 전체 통과, 독립 커밋

## notes
사람 컴퓨터의 실제 Graph Home이 필요하다.
