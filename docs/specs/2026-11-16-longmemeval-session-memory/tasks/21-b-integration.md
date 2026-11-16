# 21. b-integration

## id
21

## title
vault-builder 결과를 받은 뒤 실제 명령으로 B를 통합 확인한다

## goal
가짜가 아닌 `sessions attach-facts`와 실제 Claude Code 세션으로 B 경로가 끝까지 돈다. Intent 3과 5를 확인한다. 이 task는 파일을 쓰지 않는다.

## units
D29, A24, A14

## files
없음 (실행 확인만 한다)

## blockers
12, 16, 18, 19

## checks
- 수동: vault-builder 결과가 들어온 뒤 LongMemEval 작업 공간 하나를 `--keep`으로 돌려 `.facts.md`와 `derived` 조각 수를 본다
- 수동: 사실 추출을 켜고 실제 Claude Code 세션 하나를 끝낸 뒤 Vault `raw/sessions/`와 Graph Home `logs/`를 본다

## done-when
- [ ] 첨부가 실제 `sessions attach-facts`로 만들어졌고 계약 판이 같다
- [ ] 작업 공간의 `.facts.md` 수와 `derived` 조각 수가 맞는다
- [ ] 실제 세션 뒤 원 part와 `.facts.md`만 새로 생기고 추출용 세션 파일이 없다
- [ ] 이 확인 전의 B 값은 보고서에 쓰지 않는다
- [ ] R6(자식 세션의 훅 동작) 결과를 22번 보고서에 넘길 메모로 남겼다
