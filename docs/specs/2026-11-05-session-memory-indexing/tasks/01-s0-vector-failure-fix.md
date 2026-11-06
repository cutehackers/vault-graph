## id
1

## title
S0 원인3 단기: Chroma 페이지 조회, 계획 실패 격리, 재시도 간격, 경고

## goal
세션 시작 백그라운드 색인이 `too many SQL variables`로 죽지 않고, 실패해도 메타데이터·그래프가 발행되며, 같은 오류를 계속 반복하지 않는다. (Intent 5)

## spec
§1.2 원인3, §4.3.1 단기, §6, 위험B1

## acceptance
A-12(코드 부분), A-13, A-34

## files
- packages/vector-search/src/vector_search/chroma_store.py
- src/vault_graph/indexing/vector_index_adapter.py
- src/vault_graph/indexing/vector_failure_log.py (신규)
- src/vault_graph/interface/cli/hook_commands.py
- packages/vector-search/tests/test_chroma_store_paging.py (신규)
- tests/test_vector_plan_failure_isolation.py (신규)
- tests/test_vector_retry_interval.py (신규)

## blockers
없음. 이 작업의 첫 코드 커밋이어야 한다(A-34).

## checks
pytest packages/vector-search/tests/test_chroma_store_paging.py tests/test_vector_plan_failure_isolation.py tests/test_vector_retry_interval.py tests/test_cli_hook_session_start.py -q

## wave
1

## done-when
- [ ] 33,000개 이상 임시 컬렉션에서 `export_manifest`가 모든 행을 돌려주고, limit 없는 `get` 결과를 기록한다
- [ ] `plan` 예외가 `failed=True`가 되고, 시계를 주입한 테스트에서 같은 오류 2회 실패 뒤 2시간 안에는 벡터만 건너뛴다
- [ ] 성공 시 실패 기록을 지우고, session-start 표준 오류에 경고 한 줄(표준 출력은 그대로)
- [ ] vault-graph pytest 전체 통과, 독립 커밋

## notes
실제 컬렉션 확인은 #7(사람 컴퓨터)이 한다.
