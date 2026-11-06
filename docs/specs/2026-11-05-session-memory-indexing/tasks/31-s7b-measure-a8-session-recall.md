## id
31

## title
S7b 측정 A-8: 세션 질의 세트로 (a)(b)(c) 측정과 `e5-small` 재측정

## goal
새 형식이 이전보다 좋은지 숫자로 확인한다. LLM 없는 기준선이 이 값이다. (Intent 3)

## spec
§4.2.10, §8.1 A-8, 위험A1, 위험A4, 위험A10

## acceptance
A-8, A-9(실제 세션 하나의 v1·v2 비교 기록)

## files
- docs/design/reports/2026-11-session-recall.md (신규)

## blockers
1, 26, 25, 요청S10(외부, 필수), 사람이 만든 세션 질의 세트(한국어 40개 이상)

## checks
`tests/benchmarks/measure_session_recall.py`, `tests/benchmarks/measure_vault_search_parity.py` 실행 로그 (사람이 실행)

## wave
10

## done-when
- [ ] (c) recall@5가 (a)보다 높고, 측정1 적중률이 (a)보다 낮지 않다
- [ ] 세션 조각 수 5,000 이하, 512 초과 창 1% 이하, 재색인 시간과 최대 RSS가 같은 표에 있다
- [ ] 실제 세션 하나를 v1·v2로 모두 두고 빠진 v1 수와 남은 v1 수를 기록했다
- [ ] 질의 원문과 세션 내용은 보고서에 없다
- [ ] vault-graph pytest 전체 통과, 독립 커밋

## notes
사람 컴퓨터와 사람이 고른 기대 교환이 필요하다. #19 시작 때 한 조각 수 dry-run(위험A1) 결과를 여기에 합친다. 512 초과가 1%를 넘으면 창 크기를 다시 묻는다(위험A4).
