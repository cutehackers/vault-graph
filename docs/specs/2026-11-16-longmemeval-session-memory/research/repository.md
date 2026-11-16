# 저장소 사실 (커밋 de31b57)

이 spec이 근거로 쓰는 저장소 사실이다. 2026-11-16 이 worktree의 소스와 vault-builder 체크아웃을 읽어 확인했다. 실행하거나 잰 것은 없다.

## 결과 단위와 측정

### X1. 지금 결과 단위는 세션 교환 하나다
- source: src/vault_graph/retrieval/search/evidence_result_assembly.py:328-372@de31b57; src/vault_graph/indexing/ingestion/session_exchange_v2_chunker.py:204-219@de31b57
- basis:

`_group_by_unit`은 조각을 `(vault_id, "exchange", parent_key)` 또는 `(vault_id, "document", document_id)`로 묶는다. v2 세션 조각의 `parent_key`는 `<session_id>:<exchange_id>`이고, 교환 메타 줄이 없으면 `<path>:<제목>:<순번>`이다. 그래서 한 세션의 교환 여러 개가 각자 결과 하나가 된다.

### X2. 교환 사본 접기가 "추가 근거" 선례다
- source: src/vault_graph/retrieval/search/evidence_result_assembly.py:40-58,121-139,214-240,430-468@de31b57
- basis:

`_fold_exchange_copies`는 같은 내용의 교환을 가장 높은 순위 사본에 접고, 나머지를 `_ParentGroup.copies`에 순위대로 둔다. `_result_for_group`은 결과 자신의 근거 뒤에 사본의 근거 참조(경로와 교환 줄 범위)를 붙이고 `duplicate_content` 정보 경고를 단다. 접기는 `resolve_results` 안, 결과에 순위를 매기기 전에 한다.

### X3. LongMemEval 채점은 상위 5개 결과를 자른 뒤 세션을 센다
- source: tests/benchmarks/longmemeval_run.py:20-22,75,158-178,443-463@de31b57
- basis:

`vg search --mode evidence --limit 5` 결과에서 `score_top5`가 결과마다 근거 경로를 읽어 세션 파일 이름(`raw/sessions/.../<날짜>-<uuid>-partN.md`)의 세션을 모은다. 결과에 붙은 근거 경로도 모두 센다. 한 세션의 교환 여러 개가 5칸을 차지하면 다른 정답 세션이 밀린다. 문서 주석도 이 점을 적는다.

### X4. 세션 하나는 파일 여러 개일 수 있고, 묶음 키가 이미 있다
- source: src/vault_graph/indexing/ingestion/session_group.py:1-17,54-63@de31b57; src/vault_graph/storage/local/sqlite_metadata_store.py:30-54@de31b57
- basis:

세션 묶음은 frontmatter의 (`agent`, `session_id`)가 같은 파일들이고 키는 `<agent>:<session_id>`다. `documents` 표에 `session_group_key` 열이 있다. 파일은 수집마다 새 part 파일로 늘어난다.

### X5. 층1·층2와 LongMemEval 측정 도구
- source: docs/specs/2026-11-13-cross-encoder-rerank/research/repository.md:95-117@de31b57; tests/benchmarks/longmemeval_run.py:308-344@de31b57
- basis: 2026-11-13-cross-encoder-rerank:X15, 2026-11-13-cross-encoder-rerank:X16, 2026-11-13-cross-encoder-rerank:X18

층1은 `evaluate_search --split dev|test`(질문 파일은 저장소 밖), 층2는 저장소 안 가상 Vault `eval2`(채점 180문항, 목표 recall@5 0.95)다. `longmemeval_run`의 `summary.json`은 질문 유형별 `recall_all_at_5`, `recall_any_at_5`를 적는다. 상위 5개의 서로 다른 세션 수는 적지 않는다.

## 날짜

### X6. 세션 날짜는 창 텍스트에 없고 거를 수 있는 열도 없다
- source: src/vault_graph/indexing/ingestion/session_exchange_v2_chunker.py:346-357,464-496,561-570,656-662@de31b57; src/vault_graph/storage/local/sqlite_metadata_store.py:30-84@de31b57
- basis:

`_window_lines`는 턴 문단만 창에 넣는다. 날짜는 `section_path`의 `Session <날짜>` 이름표(frontmatter `first_turn_at`, 없으면 파일 이름 앞 날짜)와 그것으로 만든 임베딩 입력 `Session: <날짜>`에만 있다. 교환 메타 줄의 `started`·`ended`는 `exchange_time_ranges`가 읽지만 사본 정리에만 쓴다. `documents`·`chunks` 표에는 날짜 열이 없다.

### X7. 검색 요청과 MCP 검색 도구에 날짜 인자가 없다
- source: src/vault_graph/retrieval/search/search_response.py:87-108@de31b57; src/vault_graph/interface/mcp/mcp_tools.py:820-927@de31b57; src/vault_graph/interface/cli/main.py:873@de31b57
- basis:

`SearchRequest`의 필드는 질의, 범위, `limit`, 형식, `mode`, `include_retired`, `trace` 등이다. 검색하는 MCP 도구는 `ask_vault`, `search_vault`, `build_context_pack`이고 셋 다 날짜 인자가 없다. 도구 설명은 질의 언어만 안내한다.

### X8. LongMemEval 변환은 세션 날짜를 교환 시각으로 쓰고 질문 날짜는 버린다
- source: tests/benchmarks/longmemeval_convert.py:51-57,95-156,224-232@de31b57
- basis:

`haystack_dates`의 값(`2023/05/20 (Sat) 02:21`)을 시작 시각으로, 턴마다 1초씩 더해 `...Z`(UTC 표기)로 적는다. 원래 값에는 시간대가 없다. `LmeQuestion`에는 `question_date`가 없다.

## 수집 훅과 Vault 쓰기

### X9. 수집 훅의 시간 제한과 분리 프로세스 선례
- source: src/vault_graph/interface/cli/hook_commands.py:27-34,81-89,220-277,381-418@de31b57
- basis:

훅 실행기는 `vg hook capture`에 25초를 주고 vg는 20초에 실행기를 멈춘다. 종료 코드 3이면 실행기가 직접 수집한다. `start_catch_up_index`는 Graph Home `logs/`의 flock을 잡고 `start_new_session=True`로 분리 프로세스를 띄운 뒤 기다리지 않는다. 잠금이 잡혀 있으면 새로 띄우지 않는다. `capture`는 Graph Home을 `$HOME/.vault-graph`로 고정해 읽고, 결과에 수집한 Vault와 경로(`outcome.vault`, `outcome.path`)가 있다.

### X10. 바꿔야 하는 원칙 문장
- source: docs/SPEC.md:58,61,410@de31b57; AGENTS.md:3-31@de31b57
- basis:

SPEC 원칙1은 LLM 호출과 사실 추출을 금지한다. 원칙4와 AGENTS.md Project Boundary는 Vault 쓰기 길을 네 가지로 한정하고, AGENTS.md는 기계가 만든 내용(요약, 목록, 점수)을 Vault에 쓰지 않는다고 한다. SPEC §9.2 B-2는 `derived` 조각 규칙 (1)~(5)를 두고 (5)에서 `derived` 텍스트를 Vault에 쓰지 않게 한다.

### X11. vault-builder에는 사실 첨부 명령이 없고 세션 파일은 바뀌면 안 된다
- source: $HOME/workspace/vault-builder/tools/wiki/cli.py:220-263 (2026-11-16 읽음)
- basis:

`sessions` 하위 명령은 `capture`, `status`, `git-check`뿐이다. `capture`는 `raw/sessions/`에 새 파일만 더한다. `git-check`는 커밋된 세션 파일이 처음 더한 내용과 다르면 실패한다. 그래서 사실은 세션 파일에 덧붙일 수 없고 새 파일이어야 한다.

## 사용자가 확인한 값

### X12. Claude Code CLI 플래그
- source: brief B절 (상위 세션이 Claude Code 2.1.323에서 확인. 이 spec 작성 중에는 다시 확인하지 않음)
- basis:

`claude -p`에 `--model`, `--json-schema`, `--no-session-persistence`가 있다. `--bare`는 `ANTHROPIC_API_KEY`가 필요하다.

### X13. B 측정 규모
- source: brief "내가 확인한 규모" 절 (상위 세션이 데이터 파일로 셈)
- basis:

LongMemEval 150문항의 haystack 세션은 7,168개, 서로 다른 내용은 6,639개, 턴 68,763개, 문자 약 6,800만이다. 세션마다 한 번 추출하면 호출 약 6,600번이고, 호출당 10~20초면 순차 18~37시간이다(시간은 추정).
