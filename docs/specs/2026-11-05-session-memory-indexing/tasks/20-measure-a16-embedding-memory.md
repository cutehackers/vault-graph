## id
20

## title
측정 A-16: `e5-small` 전체 재색인 RSS와 시간, 아레나 켬·끔

## goal
최대 RSS 6GB와 시간 조건을 확인하고 `cpu_mem_arena` 기본값을 정한다. (Intent 5)

## spec
§4.3.4, 위험B5, 위험B6

## acceptance
A-16(측정)

## files
- docs/design/reports/2026-11-embedding-memory.md (신규)

## blockers
1, 2, 17

## checks
`/usr/bin/time -l` 전체 재색인 로그 (사람이 실행)

## wave
6

## done-when
- [ ] 최대 RSS 6GB 이하, 시간이 약 830초 이하이고 아레나 켬·끔 결과가 함께 있다
- [ ] 끈 쪽이 20% 넘게 늘지 않으면 기본값을 끈다는 결정을 기록했다
- [ ] 6GB를 넘으면 예산 조정을 사람에게 묻는다는 메모를 남겼다
- [ ] vault-graph pytest 전체 통과, 독립 커밋

## notes
사람 컴퓨터가 필요하다(21GB급 전체 재색인).
