# 1. session-fold

## id
1

## title
같은 세션의 교환을 가장 높은 교환 결과 하나에 접는다

## goal
한 세션이 상위 결과 칸을 여러 개 차지하지 않고 결과 하나와 근거 참조 3개까지로 나온다. Intent 1(세션 질문의 상위 결과가 서로 다른 세션으로 찬다)을 맡는다.

## units
D2, D3, D4, D5, I4, F1, F2, F3, A1, A2

## files
- src/vault_graph/retrieval/search/evidence_result_assembly.py
- tests/test_session_result_fold.py

## blockers
없음

## checks
- tests/test_session_result_fold.py

## done-when
- [ ] `_fold_session_exchanges`가 `_fold_exchange_copies` 뒤에서 같은 Vault·같은 세션 키의 교환을 접는다
- [ ] 접힌 결과가 가장 높은 교환의 점수와 자리를 쓰고, 근거 순서가 자신, 사본, 같은 세션 교환이다
- [ ] 붙는 교환은 참조만이고 3개까지다. 경고에 전체 수와 생략 수가 있다
- [ ] 다른 Vault와 `agent`·`session_id`가 없는 파일은 접히지 않는다
- [ ] A1, A2 evidence를 시험이 확인한다
