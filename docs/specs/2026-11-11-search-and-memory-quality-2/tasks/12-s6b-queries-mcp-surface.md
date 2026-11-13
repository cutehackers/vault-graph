# 12. S6b `queries` 인자와 도구 설명 (MCP, context pack)

## id
12

## title
`search_vault`와 `build_context_pack`에 `queries` 인자와 도구 설명을 더한다

## goal
에이전트가 표현 여러 개를 줄 수 있다. 의도2(방안A)를 담당한다.

## files
- src/vault_graph/interface/mcp/mcp_tools.py
- src/vault_graph/context/pack/context_pack_builder.py
- tests/test_mcp_tools.py
- tests/test_context_pack_queries.py (신규)
- 층2용 고정 표현 묶음: tests/fixtures/eval_layer2/queries_expansion.json (신규, 층1 묶음은 저장소 밖)

## blockers
11, 14 (14도 mcp_tools.py와 tests/test_mcp_tools.py를 쓰므로 같은 웨이브에 두지 않는다)

## acceptance
A-8

## checks
- `uv run --python 3.12 pytest -q tests/test_mcp_tools.py tests/test_context_pack_queries.py`
- 층1 시험용 의역 질문 recall@5를 `query` 하나일 때와 `queries`일 때 비교
- `uv run --python 3.12 ruff check src tests`
- `uv run --python 3.12 mypy src tests`

## done-when
- [ ] `queries`(최대 4개)와 기존 `query`를 모두 받는다.
- [ ] 도구 설명에 한국어 표현, 영어 표현, 핵심 단어만, 예상 답 문장을 넣으라고 적었다.
- [ ] 질문마다 고정한 표현 묶음으로 층1 시험용 의역 recall@5가 `query` 하나일 때보다 높다. 같은 입력에 같은 결과다.
