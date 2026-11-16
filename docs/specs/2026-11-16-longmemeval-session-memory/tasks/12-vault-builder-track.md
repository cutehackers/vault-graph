# 12. vault-builder-track

## id
12

## title
vault-builder 저장소 별도 세션의 결과를 기다려 받는다

## goal
Vault 사실 첨부 명령 `sessions attach-facts`가 vault-builder에서 구현되고 그 결과가 이 세션에 들어온다. Intent 5를 맡는다. 이 task는 이 저장소에 파일을 쓰지 않는다.

## units
D25, D26, D27, A23

## files
없음 (이 저장소에 쓰는 파일이 없다)

## blockers
없음

## checks
- 수동: vault-builder 저장소 세션의 테스트 결과와 `sessions attach-facts` 실행 기록을 읽는다

## done-when
- [ ] 상위 세션이 D25~D28 brief로 vault-builder 세션을 열었다
- [ ] 그 세션이 정상 입력 `written`, 재실행 `exists`, D27 거부 조건 `rejected`(파일 없음)를 보고했다
- [ ] `git-check`와 `capture`가 `.facts.md`를 세션 파일로 세지 않는다는 보고가 있다
- [ ] 보고가 `vault-session-facts/v1` 계약과 같은 판을 따른다
- [ ] 중지 조건: vault-builder 세션이 결과를 보고한다. 이 저장소에서 vault-builder 코드는 고치지 않는다
