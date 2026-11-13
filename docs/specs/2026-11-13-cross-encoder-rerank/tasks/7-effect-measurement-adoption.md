# 작업 7. 효과 측정, 섞기 값 고정, 채택 판정

## id

7

## title

효과 측정, 섞기 값 고정, 채택 판정

## goal

개발용으로만 `k`, `w`, `N`을 고정하고 시험용을 한 번 재서 켜도 되는지 판정한다. 기존 목표를 지키는지 확인해 Intent 1, 2를 닫는다.

## units

D1, D16, F7, A14, A15, A16, A17, A18, A20

## files

- `src/vault_graph/retrieval/search/reranker.py`
- `tests/test_reranker.py`
- `docs/design/reports/2026-11-reranker-measurement.md`

## blockers

1, 2, 5, 6

## checks

- 수동: 재정렬을 켠 측정용 Graph Home에서 층1 192문항 evaluate_search를 돌려 summary.json의 p95를 본다
- 수동: 층1 개발용을 꺼짐·켜짐으로 돌려 compare_search_eval로 비교하고, 값 고정 뒤 시험용을 한 번 잰다
- 수동: eval2 Graph Home에서 재정렬을 켜고 evaluate_search --vault-id eval2를 돌린다
- 수동: longmemeval_run --limit 150을 재정렬 preset 인자와 함께 돌린다
- 수동: 층1 개발용 꺼짐·켜짐 결과에서 세션 종류만 떼어 본다
- 수동: 목표4 질문 37문항을 재정렬 꺼짐·켜짐으로 build_context_pack에 돌려 적중 수를 비교한다

## done-when

- [ ] 개발용 96문항만으로 `k`(10·60), `w`(0.5·1·2), "재정렬 순서 그대로"를 비교해 코드 상수와 N을 고정했다. N을 키웠다면 관문2를 다시 쟀다.
- [ ] 고정 뒤 시험용 96문항을 한 번만 쟀고, 개발용보다 크게 낮은지 보고서에 적었다.
- [ ] 개발용 wiki recall@5와 MRR이 꺼짐보다 높고, MRR이 0.78 이상이며 title은 1.00이다.
- [ ] 켠 검색의 p95가 1초 이하이고(적재 뒤 한 프로세스), 적재 시간은 따로 적었다.
- [ ] 층2 recall@5가 0.95 이상이다.
- [ ] LongMemEval `--limit 150`에서 recall_all@5가 0.77 이상, recall_any@5가 0.9667 이상이다.
- [ ] 세션 recall@5가 0.85 이상이고 문서 검색과 따로 변화를 적었다.
- [ ] `build_context_pack` 적중이 꺼짐(34/37)보다 낮지 않다.
- [ ] 기준 중 하나라도 못 넘거나 시험용이 크게 낮으면 보고서에 사유를 적고 기본값은 꺼짐으로 둔다. 개선이 없으면 작업을 닫는다.
- [ ] 기본값은 꺼짐이고 켜는 일은 사용자가 `vg reranker use`로 한다.
