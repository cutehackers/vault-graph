## id
35

## title
측정 A-19: dry-run 엔티티 upsert 수

## goal
그래프 갱신이 바뀐 문서 수에 비례하는지 실제 Vault로 확인한다. (Intent 5)

## spec
§8.2 A-19 측정

## acceptance
A-19(측정)

## files
- docs/design/reports/2026-11-graph-incremental.md (신규)

## blockers
1, 30

## checks
`vg index --dry-run --vault-id vault-graph` 로그 (사람이 실행)

## wave
10

## done-when
- [ ] 엔티티 upsert 수가 바뀐 문서 수에 비례함을 기록했다
- [ ] vault-graph pytest 전체 통과, 독립 커밋

## notes
사람 컴퓨터의 실제 Graph Home이 필요하다.
