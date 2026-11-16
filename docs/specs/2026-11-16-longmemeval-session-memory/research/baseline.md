# arctic-m 기준선과 실패 분류

측정일: 2026-11-16. 코드: 커밋 `169cd9e`(기준 브랜치 `feat/jh/cross-encoder-rerank` + spec 문서). 데이터: `longmemeval_s_cleaned.json`(sha256 `d6f21ea9…a442`), 고정 순서 150문항. 임베딩: arctic-m(기본값). 명령: `tests/benchmarks/longmemeval_run.py --limit 150 --keep`, 재정렬 꺼짐과 `--reranker mmarco` 켜짐. 두 실행을 동시에 돌려 시간 값은 쓰지 않는다. 질문 원문은 옮기지 않는다.

### X19. 기준선 recall은 꺼짐 0.773, 켜짐 0.800이다
- source: scratchpad `base-off`, `base-on` 결과(2026-11-16), 아래 X20의 다시 돌린 문항 포함
- basis: X20

| 유형 | 문항 | 꺼짐 recall_all@5 | 꺼짐 recall_any@5 | 켜짐 recall_all@5 | 켜짐 recall_any@5 |
|---|---:|---:|---:|---:|---:|
| 전체 | 150 | 0.7733 | 0.9667 | 0.8000 | 0.9800 |
| knowledge-update | 16 | 0.9375 | 1.0 | 1.0 | 1.0 |
| multi-session | 36 | 0.5000 | 0.9722 | 0.6111 | 1.0 |
| single-session-assistant | 22 | 1.0 | 1.0 | 1.0 | 1.0 |
| single-session-preference | 7 | 1.0 | 1.0 | 1.0 | 1.0 |
| single-session-user | 19 | 1.0 | 1.0 | 1.0 | 1.0 |
| temporal-reasoning | 50 | 0.7000 | 0.9200 | 0.6800 | 0.9400 |

켜짐 값은 PR 35 보고서(2026-11-reranker-measurement §8.7)의 0.80, multi-session 0.611, temporal-reasoning 0.68과 같다.

### X20. 마지막 10~11문항은 vault-builder 원본이 바뀌어 다시 돌렸다
- source: scratchpad `base-*/results.jsonl` 오류 기록과 `tail.log`(2026-11-16)
- basis:

측정 중 vault-builder 세션이 `~/workspace/vault-builder`의 `tools/wiki/cli.py`를 고치기 시작해, 꺼짐 141~150, 켜짐 140~150번 문항의 `vault install`이 자체 검사에서 실패했다. 이 문항들만 같은 기준 코드와 vault-builder `main`(`fb21ee1`)의 고정 사본으로 다시 돌려 결과 줄을 바꿨다. 이후 측정은 모두 고정 사본을 쓴다.

### X21. 상위 5개 결과에 서로 다른 세션은 평균 2.8개뿐이다
- source: scratchpad `classify-off.json`, `classify-on.json`(2026-11-16)
- basis: X19

같은 작업 공간에서 `limit=30`으로 다시 검색해 서로 다른 세션을 차례로 다섯 개 골랐을 때 recall_all@5:

| | 지금 방식 | 서로 다른 세션 다섯 개 | 상위 5개의 세션 수 |
|---|---:|---:|---:|
| 꺼짐 전체 | 0.7733 | 0.8733 | 2.81 |
| 꺼짐 multi-session | 0.5000 | 0.6389 | 3.00 |
| 꺼짐 temporal-reasoning | 0.7000 | 0.8800 | 2.86 |
| 켜짐 전체 | 0.8000 | 0.8800 | 2.82 |
| 켜짐 multi-session | 0.6111 | 0.7778 | 2.94 |
| 켜짐 temporal-reasoning | 0.6800 | 0.8000 | 2.90 |

### X22. multi-session과 temporal-reasoning 실패의 가장 큰 원인은 같은 세션 교환의 칸 차지와 6~30위다
- source: scratchpad `classify-off.json`, `classify-on.json`(2026-11-16)
- basis: X21, X14

실패 문항마다 빠진 정답 세션을 다음 순서로 나눴다: 서로 다른 세션 다섯 안에 있음(같은 세션 교환이 칸 차지), `limit=30` 결과 안(6~30위), `limit=5` 후보 안이지만 30위 밖, 후보에 없음. 문항은 가장 나쁜 갈래로 센다.

| | 실패 | 칸 차지 | 6~30위 | 30위 밖 | 후보에 없음 |
|---|---:|---:|---:|---:|---:|
| 꺼짐 multi-session | 18 | 6 | 10 | 0 | 2 |
| 꺼짐 temporal-reasoning | 15 | 9 | 2 | 0 | 4 |
| 켜짐 multi-session | 14 | 6 | 6 | 0 | 2 |
| 켜짐 temporal-reasoning | 16 | 6 | 6 | 0 | 4 |

"날짜 추론 필요"는 질문의 시간 낱말(ago, last, 월 이름 등)로만 셌다. 꺼짐·켜짐 모두 temporal-reasoning 실패 전부(15, 16)와 multi-session 실패 10, 8문항에 시간 낱말이 있다. 날짜 범위로 좁힐 수 있는 질문은 이보다 훨씬 적다(X14, 150문항 중 15문항).

### X23. 층1·층2 기준선은 벡터를 새로 만든 Graph Home 사본에서 쟀다
- source: scratchpad `eval/fresh-base-l1-*`, `eval/base-l2`(2026-11-16)
- basis:

`~/.vault-graph-eval/layer1/graph-home`은 벡터 6,790개가 오래되어(`vector_stale`) 사본을 만들어 `vg index --all-vaults`로 다시 색인했다(2,865초). 원본은 건드리지 않았다. 층2는 저장소 픽스처로 새 Graph Home을 만들었다.

| | recall@5 | MRR | 세션 recall@5 |
|---|---:|---:|---:|
| 층1 dev | 0.9167 | 0.7357 | 0.9333 |
| 층1 test | 0.8958 | 0.7740 | 0.8667 |
| 층2 | 0.9611 | 0.8994 | 0.9762 |

### X24. 세션 날짜로만 거른 C는 LongMemEval에서 나빠졌다
- source: scratchpad `C-off`, `C-on`, `C2-off`, `C2-on` 결과(2026-11-16), 보고서 §3
- basis: X14, X19

범위가 붙는 15문항 중 좋아진 문항은 0이다. 규칙 범위 그대로 거르면 6문항, 끝을 질문 날짜까지 열면 4문항이 나빠졌다(꺼짐 전체 0.8533 → 0.8133, 0.8267). 나빠진 문항의 정답 세션 날짜는 범위 밖에 있다. 하나는 질문 당일 세션이 지난달 일을 말한다. 나머지는 두 사건을 비교하는 질문이라 한쪽 정답 세션이 범위 밖이다(예: 1월 범위, 정답 세션 10월·1월·2월).

### X25. 논문은 세션 날짜가 아니라 LLM이 뽑은 사건 날짜로 값을 색인해 거른다
- source: arXiv 2410.10813v2 §5.1, §5.4, Table 4 (2026-11-16 읽음)
- basis:

값은 그 안의 사건 날짜로 색인되고(§5.4 "indexed by the dates of the events they contain"), 사건은 색인 단계에서 LLM이 세션에서 뽑는다(§5.1). 질문의 범위는 검색 시 LLM이 뽑아 범위 밖 값을 거른다. temporal-reasoning recall은 GPT-4o로 범위를 뽑을 때 평균 6.8~11.3% 오르고, Llama 8B로 뽑으면 기준선보다 낮아진 경우가 있다.
