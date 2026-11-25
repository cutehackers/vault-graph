# 질의 경로와 기억 데이터 확인 결과

확인일: 2026-11-25. 코드: 커밋 `9ddce0c`. Graph Home: `~/.vault-graph`, 임베딩 arctic-m. Vault: vault-graph 프로젝트 Vault(`~/vaults/vault-graph`), personal Vault(`~/vault`). 질문 원문은 이 대화에서 사용자가 쓴 것만 옮긴다.

## 질의 경로

### X1. 기본 검색 mode `knowledge`는 세션 원문을 후보에서 뺀다
- source: `src/vault_graph/retrieval/search/retrieval_service.py:76-91@9ddce0c`, `src/vault_graph/interface/mcp/mcp_tools.py:888@9ddce0c`
- basis:

`SEARCH_MODE_ROLES["knowledge"]`는 `canonical_knowledge`, `source_manifest` 두 역할만 고른다. `raw/`로 시작하는 문서는 모두 `raw_evidence`다(`indexing/ingestion/document_authority.py:31-32`). `search_vault`의 기본 `mode`는 `"knowledge"`다.

### X2. `ask_vault`의 검색 단계도 `knowledge` mode로 돈다
- source: `src/vault_graph/context/answer/evidence_planner.py:137-147@9ddce0c`
- basis: X1

`gather`는 `RetrievalService.search`에 `mode`를 넘기지 않아 기본값 `knowledge`로 검색한다. `ask_vault`의 `mode="evidence-first"` 인자는 검색 mode와 관계없는 값이다.

### X3. 답변기는 검색된 조각을 모두 `supported`로 표시하고 발췌만 나열한다
- source: `src/vault_graph/context/answer/answer_composer.py:13-66@9ddce0c`
- basis:

`ExtractiveAnswerComposer.compose`는 상위 5개 근거를 claim으로 만들고, 관계 상태가 contested가 아니면 `supported`로 둔다. 질문과 근거가 맞는지 확인하는 단계가 없다.

### X4. 세션에만 답이 있는 질문에 `vg ask`가 무관한 wiki 조각 11개를 돌려줬다
- source: 실행 `vg ask --graph-home ~/.vault-graph "0.2.0 배포할 때 생긴 문제를 어떻게 해결했지?"`(2026-11-25, cwd vault-graph 저장소)
- basis: X2, X3

답은 `raw/sessions/claude-code/2026-10-28-6b689ea0-…-part1.md` 57~91행("개발은 workspace로, 배포는 wheel 하나로")에 있다. 결과는 recall.sh 결정 2개(그중 하나는 대체된 결정), Riverpod, parallax, wiki-linting 등 personal Vault 페이지였고 모두 `[supported]`였다.

### X5. 같은 질의를 `evidence` mode로 하면 해당 세션이 3위로 나온다
- source: 실행 `vg search --mode evidence --limit 5 "0.2.0 배포 별개 모듈 하나의 패키지"`와 `--mode knowledge` 비교(2026-11-25)
- basis: X1

knowledge mode 상위 4개는 모두 personal Vault의 무관한 페이지였다. "docs refresh 브랜치 커밋" 질의도 같은 양상이었다.

### X6. 프로젝트 폴더에서 검색해도 다른 프로젝트 문서가 상위를 차지한다
- source: X4, X5 실행 결과
- basis: X4, X5

vault-graph 저장소에서 검색했는데 personal Vault의 Flutter·UX 페이지가 상위에 왔다. SPEC 결정13(모든 연결 Vault를 관련도 순 한 목록으로)대로 동작한 결과다.

### X7. 그래프는 제목·링크·frontmatter 관계를 규칙으로 뽑은 것이고 기본 검색에서 꺼져 있다
- source: `src/vault_graph/indexing/extraction/entity_extractor.py:1-40@9ddce0c`, `mcp_tools.py` `include_graph: bool = False`
- basis:

## 기억 데이터

### X8. vault-graph Vault의 기억은 대부분 세션에 있다
- source: `~/vaults/vault-graph` 파일 수(2026-11-25)
- basis:

세션 part 79개(`raw/sessions/claude-code/`), wiki 결정 8개, 개념 3개, 작업 흐름 2개, 지도 7개.

### X9. 사실 첨부가 있는 세션 part는 79개 중 9개다
- source: `find raw -name "*.facts.md"`(2026-11-25), `vg facts status`(대기열 0, 실패 0)
- basis: X8

사실이 없는 70개 part는 합쳐 11,089,616바이트다. 예시 part 하나가 42,270바이트, 294턴이다.

### X10. 사실 작업자는 교환 메타가 있는 v2 part만 처리한다
- source: `src/vault_graph/interface/composition/adapters/fact_worker.py:363-380@9ddce0c`
- basis:

`_exchanges`는 `<!-- vg:exchange id=… -->` 줄이 있는 교환만 고른다. 79개 part 중 35개가 이 줄이 없는 v1이다.

### X11. 사실 작업은 수집 훅만 대기열에 넣는다
- source: `src/vault_graph/interface/cli/hook_commands.py:491@9ddce0c`, `fact_queue.py:52`
- basis:

이미 저장된 part를 다시 처리하는 명령이 없다.

### X12. v1 35개 part의 원본 jsonl은 모두 남아 있다
- source: `~/.claude/projects/*/<session_id>.jsonl` 존재 확인(2026-11-25), `~/.claude/settings.json`에 `cleanupPeriodDays` 없음
- basis: X10

Claude Code 기본 보관 기간은 30일이다. 예시 원본(6b689ea0…)의 수정 시각은 2026-11-15다.

### X13. 교환 메타의 수정 파일 목록은 키워드 열 텍스트로만 색인된다
- source: `src/vault_graph/indexing/ingestion/session_exchange_v2_chunker.py:374-390@9ddce0c`
- basis:

`exchange_keyword_metadata`가 `files: …`를 키워드 행의 frontmatter 열 문자열로만 만든다. 경로로 기억을 찾는 조회는 없다.

### X14. 세션 원문의 assistant 줄 상당수는 도구 이름 줄이다
- source: `2026-10-28-6b689ea0-…-part1.md`에서 assistant 머리 282개, `Tools:` 줄 241개(2026-11-25)
- basis:

### X15. wiki 결정은 세션 교환 줄 범위를 근거로 적는다. 근거 원천이 없는 페이지도 있다
- source: `~/vaults/vault-graph/wiki/decisions/prefer-root-cause-fixes-over-workarounds-for-multilingual-search.md` Evidence 절, `use-markdown-for-compiled-knowledge.md:25`(`primary_sources: []`)
- basis:

### X16. Vault `raw/`에 쌓이는 원천은 세션, 자동 기억 노트 사본, 외부 문서다
- source: `~/vault/raw`(sources 30, imports/claude-memory 10, assets), `~/vaults/vault-graph/raw`(sessions 79)
- basis:

commit은 Vault에 저장되지 않고 git 저장소에 있다.

## 추출기

### X17. 추출기는 `claude`와 `llama-server` 두 가지이고 설정 파일이 없으면 `claude`다
- source: `src/vault_graph/operation/scope/facts_settings.py:3-6, 30, 72-80@9ddce0c`, `fact_extractor_selection.py:17-18`
- basis:

로컬 끝점 기본값은 `http://127.0.0.1:8080`, 기본 모델 파일은 `~/llm/models/Qwen3.5-27B-Q4_K_M.gguf`다. 설정 주석은 "로컬 기본값 전환은 측정 뒤"라고 적는다.

### X18. 짧은 세션 기준 추출 시간은 Claude 약 6.5초, 로컬 Qwen3.5 27B 약 14초(사고 끔)다
- source: `docs/design/reports/2026-11-longmemeval-session-memory.md:86@9ddce0c`, `llama_fact_extractor.py:60-62`
- basis: X9

LongMemEval 세션 기준이다. 실제 vault-graph part(X9)는 훨씬 길어 시간을 다시 재야 한다.

### X19. 이 Mac에는 llama-server와 모델 파일이 있지만 서버는 꺼져 있다
- source: `command -v llama-server`, `ls ~/llm/models`, `curl 127.0.0.1:8080/v1/models` 응답 없음(2026-11-25)
- basis: X17

## 코드 참조

### X20. 등록된 코드 저장소가 0개라 `explore_project`가 실패한다
- source: `vg code status`(`no enabled code repositories are registered`), MCP `explore_project` 호출 결과 `provide a registered repository_id`(2026-11-25)
- basis:

MCP 서버 안내는 코딩 작업이면 `explore_project`를 먼저 부르라고 한다.

### X21. 세션 44개 v2 part의 도구 호출은 Bash 8,368, Read 1,521, Edit 974, Write 595번이다
- source: 교환 메타 `tools=` 합계(2026-11-25)
- basis: X10

파일 읽기 상당수가 Bash(`cat`, `sed`)로 일어나 Read hook만으로는 파일 접근을 다 잡지 못한다.

## 외부 사례

### X22. NVIDIA Auto Ontology는 개념 사전·매핑·인증·답 가능성 검사를 두고 질의 때 LLM ReAct로 답한다
- source: https://github.com/NVIDIA/auto-ontology README와 docs/architecture.md(2026-11-25 읽음)
- basis:

DB 메타데이터에서 개념(동의어 포함), 열 매핑, 관계, SQL 속성을 만들고 사람이 인증한다. `check_answerable`은 질문 개체가 개념에 걸리는 비율(coverage)을 센다. 질의는 추론 모델이 retrieve, run_sql, submit 도구를 고르며 답한다. 인증은 검토 표시일 뿐 검색에 영향을 주지 않는다.

## 문서 정리 전 확인

### X23. 코드 출력과 입력 값에는 L1 이름이 남아 있고, 회상 제목에는 L3가 없다
- source: `src/vault_graph/context/pack/recall_backlog.py:73@9ddce0c`, `interface/mcp/mcp_prompts.py:243`, `interface/composition/adapters/auto_memory_reader.py:138,142`, `docs/SPEC.md:170`, `context/pack/recall.py:82-83`
- basis:

정리 대기 줄은 "L1 노트 N개"를 출력하고, `curate_memory` prompt와 자동 기억 폴더 오류 문구도 "L1"을 쓴다. `list_memory_candidates`의 `kinds` 값은 `l1_note`다. 회상 구획 제목은 "## 프로젝트 요약"과 "### 열린 일", "### 현재 결정", "### 교정·규칙"이고 L3라는 글자는 출력하지 않는다.

### X24. 현재 문서가 삭제 후보 폴더를 링크한다
- source: `docs/ARCHITECTURE.md:7,260,279@9ddce0c`, `docs/DEVELOPMENT.md:52`, `docs/SPEC.md:6,139,239,342,350-395,456-457`, `docs/TODO.md:29`, `docs/design/glossary.md:6,24`, `docs/design/reports/2026-10-15-modularization-completion-ko.md:6`, `open-docs.sh:5`
- basis:

ARCHITECTURE와 DEVELOPMENT, glossary는 `docs/design/specs/`의 모듈 명세(VG-MOD, 벡터 모듈 계약, SEL)를 링크한다. SPEC §8은 독립 패키지 계약을 `docs/design/specs/`와 `docs/design/plans/`에 둔다고 적는다. SPEC §0 머리, §7, §8, §10과 TODO는 `docs/archive/`를 링크한다. `docs/design/specs/` 안 문서는 `intents/`, `plans/`, `superpowers/`를 링크한다. `open-docs.sh`만 `docs/stenc`를 쓴다. `.github/`, `.gitignore`, `src/`, `tests/`에는 삭제 후보 경로가 없다. 2026-11-25 grep으로 확인했다.

### X25. 문서를 읽는 테스트는 넷이다
- source: `tests/test_context_pack_docs_contract.py:14-25@9ddce0c`, `tests/test_retired_search_filter.py:118-124`, `tests/test_naming_conventions.py:4-31`, `tests/test_readme_onboarding_contract.py:7-71`
- basis:

첫째는 SPEC의 "Minimum JSON shape" 절 JSON을 DTO와 비교한다. 둘째는 DECISIONS에 "INV-05"와 `retired`, `deprecated`를 함께 담은 항목이 있는지 본다. 셋째는 `docs/` 아래 모든 `.md`에서 금지어(테스트의 `FORBIDDEN_TERMS` 두 개)를 찾는다. 넷째는 README만 읽는다. 벤치마크 스크립트 몇 개는 `docs/design/reports/`에 결과를 쓴다.

### X26. 설계 용어집은 옛 기억 층을 정의하지 않는다
- source: `docs/design/glossary.md@9ddce0c`(L1, L2, L3, 계층, layer grep 0건)
- basis:

용어집은 VG-MOD 기능 그룹과 SEL 용어만 담는다.

### X27. 훅 실행기는 세 사건만 받고 UserPromptSubmit 처리는 없다
- source: `docs/SPEC.md:444@9ddce0c`(의존1), `src/` grep `UserPromptSubmit` 0건, `docs/TODO.md:67-68`(n차-11)
- basis:

vault-builder 훅 실행기는 SessionStart, PreCompact, SessionEnd만 settings에 더한다. 프롬프트마다 회상하는 일은 TODO에 "의존1 확장 필요"로 남아 있다.

### X28. `vg facts`는 이미 `--extractor` 선택을 받는다
- source: `src/vault_graph/interface/cli/facts_commands.py:36-40@9ddce0c`
- basis: X17

도움말은 "저장된 값을 두고, 없으면 claude"다. `auto` 값은 없다.

### X29. DECISIONS의 옛 층 결정은 두 항목이고 파일은 영어 형식이다
- source: `docs/DECISIONS.md:6-18,922-930,952-960@9ddce0c`
- basis:

"Move L1, L2 And L3 Memory Management To Vault Graph"와 "Keep L3 Lists Computed And The Brief As A Vault Page"다. 항목은 Question, Decision, Reason, Implications 순서의 영어 문단이다. 작성 규칙은 확정된 결정만 적고 대기 중인 질문은 진행 중인 문서에 두라고 한다.

### X30. AGENTS.md Project Boundary 첫 문장은 vault-graph를 검색·회상 층으로 부른다
- source: `AGENTS.md:5-9@9ddce0c`
- basis:

"Vault Graph is a local search and recall layer over Vault."로 시작하고 여섯 쓰기 경로를 이어 적는다.
