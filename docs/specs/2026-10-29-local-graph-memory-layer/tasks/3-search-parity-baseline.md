## id

3

## title

1차-1 측정1 스크립트를 만들고 기준선(변경 전)을 잰다 [수동 포함]

## goal

`vg search`와 Vault 검색의 상위 5개 적중률과 대기 시간을 같은 질문으로 비교할 수 있게 된다. 이 결과가 1차-5 효과를 판정하는 기준선이 된다. spec Intent 5를 다룬다.

## files

- `tests/benchmarks/measure_vault_search_parity.py`
- `tests/test_measure_vault_search_parity.py` (가짜 하위 프로세스로 텍스트 결과 해석, 적중 계산, 실행 실패 집계를 검사)
- `docs/design/reports/<날짜>-local-graph-search-parity-baseline-ko.md`

결정 (2026-10-30 승인): 기준선은 조건A(현재 Vault)와 조건B(손으로 옮긴 세션 Vault 복사본)를 모두 잰다. A-19가 두 조건 모두에서 1차-1 기준선과 비교하기 때문이다.

사람이 직접 하는 일: 질문 20개 작성, 조건B용 Vault 복사본 작성, Graph Home 생성과 색인. Vault 검색은 Vault의 `tools/wiki/cli.py`를 실행만 하고 Vault 저장소는 고치지 않는다.

## blockers

1

## acceptance

A-7, A-20

## checks

- `uv run --python 3.12 --all-packages --all-extras pytest -q tests/test_measure_vault_search_parity.py`
- 보고서에 질문 문장이 하나도 없는지 질문 파일의 각 문장으로 `grep`해서 확인
- CI 검증 세 명령 (작업 1의 checks와 같음)

## done-when

- [ ] 스크립트가 `def main(questions: Path, vault: Path, graph_home: Path, out_dir: Path) -> None` 시그니처를 갖고, 질문마다 3회 실행해 첫 실행 시간과 중앙값을 기록한다
- [ ] Vault 검색 실행 실패는 미적중이 아니라 "실행 실패"로 따로 센다
- [ ] (수동) 사람이 실제 Vault 내용으로 질문 20개 JSONL을 저장소 밖에 만들었다
- [ ] (수동) 사람이 Claude Code 대화를 손으로 Markdown으로 옮긴 조건B용 Vault 복사본을 저장소와 실제 Vault 밖에 만들었다
- [ ] (수동) `vg setup`과 `vg index`로 Graph Home을 만들었다. 이 단계는 Graph Home에만 쓴다
- [ ] (수동) 조건A와 조건B를 모두 쟀다
- [ ] 질문별 결과는 `out_dir`에만 있고, 커밋한 보고서에는 질문 수, 시스템별 적중률, 시간, 조건, 커밋, 조건B의 세션 수와 형식만 있다
