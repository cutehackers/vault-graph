## id

14

## title

1차-6 측정1을 다시 재고 결과를 기록한다 [수동]

## goal

사람이 정한 성공 기준을 숫자로 판정한다. `vg search`의 상위 5개 적중률이 조건A와 조건B 모두에서 Vault 검색보다 높아야 하고, 1차-5 뒤에도 1차-1 기준선보다 낮으면 안 된다. spec Intent 5를 다룬다.

## files

- `docs/design/reports/<날짜>-local-graph-search-parity-after-ko.md`

전부 사람이 직접 하는 측정이다. 질문 파일과 질문별 결과는 저장소 밖에 둔다. A-12의 "주입 대비 열린 비율"은 작업 9 이후 2주 운영 뒤 이 보고서에 덧붙인다(후속 항목, 이 작업의 완료 조건이 아님).

## blockers

13

## acceptance

A-19

## checks

- `uv run --python 3.12 python tests/benchmarks/measure_vault_search_parity.py` (질문, Vault, Graph Home, 출력 경로는 모두 저장소 밖)
- 보고서에 질문 문장이 하나도 없는지 질문 파일의 각 문장으로 `grep`해서 확인

## done-when

- [ ] (수동) Graph Home에서 `vg index --full`을 다시 실행했다
- [ ] (수동) 질문 20개로 조건A와 조건B를 다시 쟀고 실행 실패가 0건이다
- [ ] 보고서에 두 조건의 시스템별 적중률, 시간, 1차-1 기준선 대비 변화, 커밋이 있다
- [ ] 성공 기준을 충족했는지, 또는 판정을 보류했는지 보고서에 적었다
