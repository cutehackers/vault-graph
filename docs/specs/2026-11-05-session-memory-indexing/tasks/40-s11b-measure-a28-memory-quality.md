## id
40

## title
S11b 측정 A-28: 기억 품질 측정과 S12 진행 판정

## goal
지표1·2가 0이어야 다음 단계로 간다. (Intent 7, 8)

## spec
§4.4.10, §4.4.11 단계4, 위험D9, 위험D10

## acceptance
A-28

## files
- docs/design/reports/2026-11-memory-quality.md (신규)

## blockers
1, 39, 37, 사람이 만든 평가 세트(질문 40개 안팎, 프로젝트 2~3개)

## checks
`tests/benchmarks/measure_memory_recall.py` 실행 로그 (사람이 실행)

## wave
13

## done-when
- [ ] 지표1과 지표2가 0이다. 0이 아니면 S12로 가지 않는다
- [ ] 지표6 정리 전후, 폐기 후보 중 실제 폐기 비율(위험D10), 안내 줄이 나온 세션 비율(위험D9)을 기록했다
- [ ] vault-graph pytest 전체 통과, 독립 커밋

## notes
사람 컴퓨터와 사람이 만든 평가 세트가 필요하다. 이 결과가 #41, #42의 시작 조건이다.
