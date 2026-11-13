# 14. S7b 정리 꾸러미에 "summary 없는 페이지" 목록

## id
14

## title
정리 후보에 summary 없는 페이지 종류를 더한다

## goal
정리 때 기존 기억 페이지의 summary를 채울 대상이 보인다. 의도3을 담당한다.

## files
(경로는 코드에서 확인함: 정리 꾸러미는 `list_memory_candidates` 도구와 `curate_memory` 프롬프트)
- src/vault_graph/context/memory/memory_candidates.py
- src/vault_graph/interface/composition/memory_candidate_sources.py
- src/vault_graph/interface/mcp/mcp_tools.py
- src/vault_graph/interface/mcp/mcp_prompts.py
- src/vault_graph/interface/mcp/mcp_tool_serialization.py (필요 시)
- tests/test_memory_candidates_missing_summary.py (신규)

## blockers
10

## acceptance
A-9 (보강 경로), A-10의 전제

## checks
- `uv run --python 3.12 pytest -q tests/test_memory_candidates_missing_summary.py tests/test_memory_candidates_merge_retire.py tests/test_memory_candidates_l1_session.py tests/test_mcp_tools.py`
- `uv run --python 3.12 ruff check src tests`
- `uv run --python 3.12 mypy src tests`

## done-when
- [ ] 후보 종류로 summary 없는 페이지가 나오고 `curate_memory` 프롬프트가 `update_memory`로 채우라고 안내한다.
- [ ] 한 번에 다루는 개수에 상한이 있다.
- [ ] 해당 페이지가 없으면 꾸러미가 이전과 같다.
