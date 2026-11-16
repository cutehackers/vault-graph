# 17. fact-worker

## id
17

## title
사실 작업자(대기열, 잠금, 캐시, 첨부 쓰기, 실패 기록)를 만든다

## goal
수집 뒤 분리된 작업자가 캐시에 없는 교환만 추출해 Vault 명령으로 첨부를 쓴다. 실패는 기록하고 훅과 검색에 영향이 없다. 파일 쓰기와 하위 프로세스 실행이 있어 모두 `interface/composition/adapters/`에 둔다(docs/ARCHITECTURE.md §1, §4).

## units
D16, D20, I2, I7, F7, F8, F9, F10, A15, A16, A19, A25

## files
- src/vault_graph/interface/composition/adapters/fact_queue.py
- src/vault_graph/interface/composition/adapters/fact_cache.py
- src/vault_graph/interface/composition/adapters/fact_worker.py
- src/vault_graph/interface/composition/adapters/vault_attach_facts_cli.py
- src/vault_graph/interface/cli/facts_commands.py
- tests/test_fact_worker.py

## blockers
13, 14

## checks
- tests/test_fact_worker.py

## done-when
- [ ] 작업자는 대기열이 빌 때까지 처리하고 `logs/facts-worker.lock`으로 하나만 돈다
- [ ] 캐시 키는 (추출기, 모델, 스키마 판, 교환 내용 해시)이고 새 part에 다시 나온 교환은 추출기를 부르지 않는다
- [ ] 추출기 실패는 대기열 유지, `logs/facts-failures.json` 기록, 30분 안 재시도 없음이다
- [ ] 스키마 오류는 작업 실패이고, 없는 교환 id나 빈 문장 사실만 버린다. 남은 사실이 없으면 첨부 없이 캐시에 "사실 없음"을 남긴다
- [ ] 명령이 없으면 `facts_writer_missing`을 기록하고, 생긴 뒤에는 추출기 없이 캐시로 쓴다. `rejected`는 닫고 `exists`는 성공이다
- [ ] 첨부는 `sessions attach-facts`로만 쓰고 작업 파일의 Vault와 part 경로를 쓴다. part 파일 내용은 같다
- [ ] 하위 프로세스와 HTTP를 막아도 `vg search`, `vg index`, MCP 검색 도구, `vg hook session-start`가 통과한다
- [ ] 시험은 가짜 추출기만 쓰고 실제 어댑터를 부르면 실패한다
- [ ] `vg facts worker`(작업자 진입)가 `facts_commands.py`에 있다
