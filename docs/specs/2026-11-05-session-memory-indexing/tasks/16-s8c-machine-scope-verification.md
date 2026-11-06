## id
16

## title
S8c 이 컴퓨터 검증: 실제 `vault-map.json`으로 회상 전후 비교와 17쪽 훑기

## goal
vault-graph 회상이 비지 않고 personal Vault는 `sharable` 설정 전에는 빠지는지 확인한다. (Intent 7)

## spec
§4.4.2, 위험D4, 위험D13

## acceptance
A-20(이 컴퓨터), A-29(S8 확인 기록)

## files
- docs/design/reports/2026-11-scope-rule-check.md (신규)

## blockers
1, 10, 요청S4(외부, 설정 명령 반영 뒤)

## checks
S8 전후 `vg hook session-start` 출력과 `recall.sh` 첫 줄 (사람이 실행)

## wave
4

## done-when
- [ ] vault-graph Vault의 `project` 없는 페이지가 회상에 들어가고, personal Vault 것은 `sharable` 설정 전에는 없다
- [ ] 17쪽 중 다른 프로젝트 이야기를 담은 페이지 수를 적었다(위험D13)
- [ ] vg 경로와 `recall.sh` 경로가 모두 비지 않은 출력을 낸다(A-29)
- [ ] vault-graph pytest 전체 통과, 독립 커밋

## notes
사람 컴퓨터가 필요하다. 요청S4가 반영된 뒤에만 진행한다.
