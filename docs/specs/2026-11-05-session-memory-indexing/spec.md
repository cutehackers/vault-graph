# Spec: 세션 문서 형식과 임베딩 방식, 색인 속도, vg 기억 관리

## 1. Problem

- 작업 id: `20261105-l1-l3-f98b`. 경로: research-first, design-first spec. 1차·2차 spec gate 답변(9.1, 9.3)과 독립 리뷰의 막음 7건(9.4)을 반영한 개정판이다.
- 저장소: vault-graph worktree `.worktrees/session-memory`, 브랜치 `feat/jh/session-memory-indexing`, 기준 `main@abc77e7`.
- 다른 저장소 경로는 `vault-builder:` 접두어를 붙인다. 사람 홈 폴더는 `$HOME`으로 적는다.
- 조사 문서 다섯 개
  - [research/session-embedding.md](research/session-embedding.md): 세션 조각 단위
  - [research/index-performance.md](research/index-performance.md): 색인 원인 5개
  - [research/memory-layers.md](research/memory-layers.md): L1/L2/L3 현재 구성
  - [research/session-format.md](research/session-format.md): 공통 세션 형식과 임베딩 방식(2차)
  - [research/memory-management.md](research/memory-management.md): 기억 관리 방식과 L3 위치(2차)
- 아래 표의 "확인 방법" 열이 "조사"이면 그 문서의 측정이고, "읽음"이면 이 spec을 쓰며 코드를 다시 열어 확인한 것이다.

이 spec은 사용자가 낸 이슈 네 개를 다룬다. 이슈B와 이슈C는 사용자 허락으로 합쳤다.

| 코드 | 이슈 | 한 줄 요약 |
|---|---|---|
| 이슈A | 세션 문서 형식과 임베딩 방식 | 세션 원본을 담는 공통 형식이 없고, Vault의 세션 md는 사람 턴·도구 대상·턴 id를 잃어 조각 대부분이 도구 이름 한 줄이다 |
| 이슈B+C | 색인이 오래 걸리는 원인 5개와 가속 | 백그라운드 색인이 매번 실패하고, 성공해도 바뀐 문서 전체를 다시 임베딩한다 |
| 이슈D | L1/L2/L3 기억 관리 | 계층 사이 이동이 멈춰 있고, 관리 판단이 vault-builder 여러 곳에 흩어져 있으며, 회상 경로마다 프로젝트 범위 규칙이 다르다 |

### 1.1 이슈A 세션 문서 형식과 임베딩 방식

| 코드 | 지금 상태 | 근거와 확인 방법 |
|---|---|---|
| 발견A1 | 활성 세대의 조각 34,008개 중 28,330개(83%)가 `raw/sessions/` 아래 세션 파일에서 나온다. 임베딩 입력 토큰의 74.6%가 세션이다. 파일 하나가 최대 5,541조각이다. | 조사(index-performance 2절, 활성 세대 `metadata.sqlite3` 직접 집계) |
| 발견A2 | 세션 md의 턴 제목 블록 16,346개 중 79%가 본문 없이 `Tools: ...` 한 줄이다. 70%는 서브에이전트 턴이다. | 조사(session-embedding 발견4, 22개 파트 파일) |
| 발견A3 | 조각기는 제목 블록을 만날 때마다 조각을 끊는다. 세션 md는 턴마다 `## <timestamp> <role>` 제목이 있어 턴 하나가 조각 하나가 된다. | `src/vault_graph/indexing/ingestion/document_chunking.py:117-119@abc77e7` 읽음 |
| 발견A4 | 임베딩 입력은 `Section path: <제목>` + 본문이다. 세션에서는 제목이 timestamp와 role이라 의미 없는 숫자가 임베딩에 들어간다. | `document_chunking.py:139-145@abc77e7` 읽음 |
| 발견A5 | 조각 크기 상한은 공백으로 나눈 단어 256개다. 한국어와 코드가 섞이면 모델 토큰 512를 넘어 뒷부분이 잘린다. 512에 걸리는 조각이 1,656개다. | `document_chunking.py:11, 227-228@abc77e7` 읽음, 토큰 수는 조사(index-performance 6.2) |
| 발견A6 | 조각기는 모든 파일에 하나다. 파일 형식이나 frontmatter로 조각기를 고르는 지점이 없다. 조각 id에 상수 `CHUNKER_VERSION`이 들어간다. | `src/vault_graph/indexing/ingestion/document_normalizer.py:51-76@abc77e7` 읽음 |
| 발견A7 | vault-builder `sessions capture`는 user·assistant 텍스트와 도구 이름만 md로 옮긴다. 도구 대상(파일, 명령), 성공 여부, 턴별 uuid는 남지 않는다. 사람 턴과 알림 턴은 본문이 `<`로 시작하는지로만 구분된다. | 조사(session-embedding 2절, `vault-builder:tools/wiki/lib/session_capture.py:172-221, 543-560`) |
| 발견A8 | 원본에는 더 정확한 구조가 있다. Claude Code user 레코드의 95%에 `turnOrigin`(`human`, `task_notification` 등)이 있고, `tool_use.input`의 키가 도구마다 고정이며(`file_path`, `command`, `url`, `query`), `tool_result.is_error`로 실패를 안다. Codex `item_completed`는 `UserMessage`, `CommandExecution`(`exit_code`), `FileChange`를 준다. | 조사(session-format 발견5~9) |
| 발견A9 | 원본 jsonl은 Vault 밖에 있고 Claude Code는 기본 30일 뒤 지운다. Claude Code 원본은 이 Mac에 380개 1.8GB, Codex는 127개 352MB다. 대화 텍스트는 원본 바이트의 1~4%다. vault-builder는 Codex를 수집하지 않는다. | 조사(session-embedding 발견1~3), `docs/SPEC.md:34@abc77e7` 읽음 |
| 발견A10 | 측정1 벤치마크는 결과의 문서 경로로 적중을 판정한다. 세션 파일 하나에 교환이 여러 개라 "맞는 파일, 틀린 교환"도 적중이다. 세션 검색 품질을 재기에는 부족하다. | `tests/benchmarks/measure_vault_search_parity.py:1-14@abc77e7` 읽음 |
| 발견A11 | Vault 도구에는 정규화된 세션 입력을 받는 명령이 없다. `sessions capture`는 원본 jsonl 경로만 받고, `ingest-source`는 `raw/` 밖 파일과 세션 경로를 거부한다. | 조사(session-format 3절, `vault-builder:tools/wiki/cli.py:209-224`, `vault-builder:tools/wiki/lib/ingest.py:34-45`) |
| 발견A12 | 키워드 색인 FTS 표에는 `path`, `section`, `title`, `frontmatter`, `text` 다섯 열이 있다. 세션의 파일·명령·오류 정보를 본문과 분리해 넣을 자리가 이미 있다. | `src/vault_graph/storage/local/sqlite_keyword_index.py:38-47@abc77e7` 읽음 |

### 1.2 이슈B+C 색인 속도

| 코드 | 원인 | 근거와 확인 방법 |
|---|---|---|
| 원인1 | 세션 기록이 조각과 토큰 대부분을 차지한다(발견A1). | 조사 |
| 원인2 | 바뀐 문서의 모든 조각을 다시 임베딩한다. 벡터 지문에 `index_revision`, `source_role`, provenance family id가 들어 있어 내용이 같은 조각도 지문이 달라진다. 1,118조각 세션 파일에 400조각을 덧붙이면 1,118개를 모두 임베딩한다. | `src/vault_graph/indexing/vector_index_adapter.py:343-366@abc77e7` 읽음, 덧붙이기 실측은 조사(index-performance 3.1) |
| 원인3 | 백그라운드 `vg index`가 Chroma `collection.get(include=["metadatas"])`에서 `too many SQL variables`로 실패한다. e5-small 컬렉션 33,065개가 SQLite 변수 한도 32,766을 넘는다. `plan`이 `try` 바깥이라 벡터 실패가 `vg index` 전체를 멈춘다. 재시도 간격 기록이 없어 세션마다 다시 실패한다. 실패 run 26개. 2026-11-05 10:12 이후 새 세션 기록이 벡터 검색에 들어가지 않았다. | `packages/vector-search/src/vector_search/chroma_store.py:285-304@abc77e7`, `vector_index_adapter.py:178-197@abc77e7` 읽음. 컬렉션 크기와 로그는 조사(index-performance 4.1·4.2) |
| 원인4 | 실행마다 고정 비용이 든다. 세대 전체를 `shutil.copytree`로 복사해 약 650MB를 새로 쓴다. 모든 파일을 읽고 파싱한다. 문서 5개가 바뀌어도 그래프 엔티티 25,998개를 다시 쓴다. | `src/vault_graph/indexing/publication/projection_generation.py:92-98@abc77e7` 읽음, 크기와 dry-run 수치는 조사(index-performance 5절) |
| 원인5 | 전체 재색인 최대 RSS 21.2GB. 경로 순서로 묶은 256개 배치가 모두 500토큰 이상으로 패딩되어 계산 토큰이 실제의 4.5배다. 임베딩 결과를 모두 모은 뒤 한 번에 쓴다. ONNX CPU 메모리 아레나가 늘어난 메모리를 돌려주지 않는다. | `vector_index_adapter.py:178-226, 331-332@abc77e7`, `src/vault_graph/interface/composition/adapters/text_embeddings.py:99-100@abc77e7` 읽음, 패딩 측정은 조사(index-performance 6.2) |

### 1.3 이슈D 기억 관리

계층 이름은 `vault-builder:docs/html/project-memory-structure.html:210-350`을 따른다. L1은 Claude Code 자동 기억(`$HOME/.claude/projects/<key>/memory/`), L2는 Vault `wiki/` 페이지, L3는 프로젝트 요약이다.

| 코드 | 지금 상태 | 근거와 확인 방법 |
|---|---|---|
| 발견D1 | 세션 시작 회상은 frontmatter `project`가 없는 페이지를 모든 프로젝트 것으로 본다. Vault L3 요약은 `project`가 있는 페이지만 쓴다. 그래서 vault-graph 회상에 다른 프로젝트 기억이 섞인다. | `src/vault_graph/context/pack/recall.py:358-363@abc77e7` 읽음, L3 규칙은 조사(`vault-builder:tools/wiki/lib/maps.py:270-273`) |
| 발견D2 | vg 회상은 L3를 읽지 않는다. L3는 `recall.sh` 대체 경로와 `/project-memory`만 읽는다. vg 응답 시간(관측 16초)에 따라 같은 세션에 다른 기억이 들어간다. | 조사(memory-layers 1.2 발견2) |
| 발견D3 | `remember` draft에 `project` 필드가 없고 `tags`가 빈 목록이다. 그래서 vg로 저장한 기억은 L3에 나오지 않는다. | `src/vault_graph/operation/memory/memory_drafts.py:33-57@abc77e7` 읽음 |
| 발견D4 | vault-graph 프로젝트의 L1 노트 4개가 모두 Vault로 옮겨지지 않았다(`imported: false`). L1 → L2 이동은 사람이 Vault 세션에서 `memory-cleanup`을 요청해야 돈다. | 조사(memory-layers 1.2 발견5) |
| 발견D5 | 세션 원문을 L2로 증류하는 경로가 없다. 수집된 원문이 wiki에 반영되지 않았다. L3 페이지는 두 Vault 모두 없다. | 조사(memory-layers 1.2 발견6, brief 발견8) |
| 발견D6 | 관리 판단이 여러 곳에 흩어져 있다. "이 프로젝트의 기억"을 고르는 규칙이 세 벌(Vault `maps build`, vg 회상 구획B, `summarize_project_memory`)이고, L1 반영 판정은 Vault `memory_scan.py`와 `memory-cleanup` 스킬에, 회상 대체 경로는 `recall.sh`와 `/project-memory`에 있다. cwd → 프로젝트 판정 코드도 세 곳에 따로 있다. | 조사(memory-layers 1.1 부품2·3·7·9·10·15·16, 1.2 발견1·7) |
| 발견D7 | vg는 LLM을 부르지 않고(`docs/SPEC.md:59`), `raw/`에 쓰지 않는다(`AGENTS.md:19-20`). 그래서 "관리를 vg로 옮긴다"는 "판단 재료와 흐름은 vg, 판단은 세션 안 에이전트, 저장과 검증은 Vault 도구"로만 이룰 수 있다. L1 노트를 Vault 근거로 남기려면 `raw/` 밖 파일을 받는 Vault 명령이 필요한데 지금은 없다. | `docs/SPEC.md:59, 63@abc77e7`, `AGENTS.md:3-20@abc77e7` 읽음, `ingest-source` 제약은 조사(memory-management 재료2) |
| 발견D8 | 페이지 단위로 대체·폐기된 기억(`superseded`, `deprecated`, `retired`)은 회상에서 이미 빠진다. 페이지 안의 claim 행 단위 대체는 회상에서 빠지지 않는다. 기억 평가에서 "대체된 사실을 쓰지 않기"가 가장 약한 능력으로 보고되었다. | `src/vault_graph/context/memory/project_memory.py:39@abc77e7`, `recall.py:43, 457-460@abc77e7` 읽음, 평가 근거는 조사(memory-management 사례12) |

## 2. Intent

사용자는 세션 기반 vault-graph의 핵심을 "계층 사이에서 유기적으로 움직이는 기억"으로 본다(brief Targets 4). 기억의 품질을 가장 먼저 두고, 그다음 Mac Studio 환경에서의 관리와 구현을 본다(9.1 질문7). 그러려면 세션 원문이 기억의 재료로 제대로 쓰이고, 색인이 세션마다 제때 끝나며, 기억 관리의 판단과 흐름이 한 곳에 있어야 한다.

변경 뒤에 참이어야 하는 것:

1. Claude Code와 Codex의 모든 대화를 사용자가 정한 Vault 밖 경로로 내보낼 수 있다(9.1 질문1).
2. 에이전트마다 adapter가 원본을 하나의 공통 형식으로 바꾼다. 원본 형식이 달라도 그 뒤의 저장, 렌더링, 색인은 같은 방식으로 관리된다(9.1 질문2).
3. 세션 검색은 "세션이 재가공되는 가장 효율적인 문서 형식"과 "그 문서를 가장 효과적으로 임베딩하는 방식"으로 좋아진다. 모델은 바꾸지 않는다(9.1 질문5).
4. 세션 형식과 조각 방식이 바뀌어도 결정적 검색의 성질은 유지된다. 같은 Vault 파일로 다시 색인하면 같은 조각 id, 같은 키워드 결과, 같은 위치 표시가 나온다(brief Targets 1).
5. 원인 5개를 증상이 아니라 원인에서 고친다. 세션이 시작될 때 띄운 색인이 실패 없이 끝나고, 덧붙인 만큼만 임베딩하며, 메모리 사용량에 상한이 있다(brief Targets 2·3).
6. L1, L2, L3의 관리는 모두 vg가 맡는다. 무엇을 옮기고, 고치고, 폐기할지 고르는 흐름과 그 재료는 vg에 있고, Vault는 저장소(ingest, update, query와 검증)로 남는다. "분담은 리스크가 있으니 모두 이관"(9.1 질문3).
7. 세션 시작 회상은 이 프로젝트의 기억만 넣는다. 표시 없는 페이지를 넣을지는 Vault마다 `sharable`로 정한다(9.1 질문4).
8. 대체되거나 폐기된 기억은 회상에 들어가지 않는다(사용자 우선순위 "기억의 품질", 발견D8).

[가정] "모두 vg로 이관"은 원칙1(LLM 호출 없음)과 원칙5(`raw/` 직접 쓰기 없음)를 바꾸라는 뜻이 아니라고 본다. 그래서 판단은 세션 안 에이전트가 MCP로 하고, 쓰기는 Vault 도구 경로로만 한다. 이 경로를 늘리는 경계 문장 일곱 곳은 사용자가 승인했다(9.3 질문9, 4.4.8).

[가정] 사용자가 준 시간 제한은 없다. 순서는 brief의 "원인3 단기 수정 우선순위가 가장 높다"를 따른다.

## 3. Non-goals

- 임베딩 모델 선정과 교체. 9.1 질문5에 따라 이 spec 밖이다. `e5-small`을 그대로 쓰고, 바뀐 형식으로 다시 잰 값은 기준 확인(A-8)으로만 남긴다. KURE-v1, bge-m3, arctic-embed-m-v2.0 비교는 다음 spec이다.
- late chunking, multi-vector(ColBERT류), 학습형 희소 벡터. 앞 둘은 긴 문맥 모델이나 백엔드 교체가 필요해 모델 재선정 뒤에 다시 본다(조사 session-format 결정8 3단계). 희소 벡터는 SQLite 키워드 색인이 맡는다.
- 정규화 JSONL이나 원본 jsonl을 vg가 직접 검색 대상으로 색인하는 일. 검색 대상은 Vault 안의 세션 md다(조사 session-format 결정7).
- Codex adapter 구현. 이번에는 계약(4.2.3)만 쓰고 구현은 backlog B-1로 둔다(9.1 질문2).
- 로컬 언어 모델을 쓰는 모든 단계. 세션 교환의 요약·예상 질문(`derived` 조각)과 기억 정리의 후보 거르기는 다음 spec으로 미룬다(9.3 질문12). 이 spec은 LLM 없는 기준선을 만들고 잰다. 다음 spec이 지켜야 할 결정성 규칙은 4.2.8에 메모로만 남긴다. backlog B-2다.
- vg 안에서 기억 내용을 판단하거나 문장을 만드는 일. 판단은 세션 안 에이전트가 한다(원칙1).
- vg가 Vault 파일과 `raw/`를 직접 쓰는 일, 기계가 만든 내용(요약, 목록, 점수)을 Vault에 쓰는 일. 쓰기는 Vault 도구 경로로만 한다.
- 기억의 자동 폐기. 폐기 후보는 점수만 매기고, 폐기는 에이전트가 하고 사람이 확인한다.
- 질문 기반 회상(MCP `recall`, UserPromptSubmit 훅, `docs/SPEC.md` n차-8·n차-11).
- 가속7 CoreML, 가속10 Chroma 교체, 가속11 fastembed `parallel`. 측정 전이고 범위가 커서 별도 spec이다.
- 일반 md 파일(`wiki/`, `docs/`, 세션이 아닌 `raw/`)의 조각 방식 변경. `document-block-window-v2`와 그 조각 id는 그대로다.
- vault-builder 쪽 구현. 이 spec은 vault-graph가 기대하는 계약과 요청(4.5)만 적는다.
- 세대 보관 개수, 세대 발행 잠금 규칙 변경.

## 4. Design

### 4.0 세 저장소의 역할 (리뷰 반영 기준)

독립 리뷰의 막음 7건(9.4)은 모두 "어느 저장소가 그 일을 맡는가"를 정하면 풀린다. 개정은 아래 역할을 기준으로 했다. 근거는 `AGENTS.md:3-20@abc77e7`, `docs/SPEC.md` §0·§1·§2@abc77e7이다.

| 저장소 | 맡는 일 | 하지 않는 일 |
|---|---|---|
| Vault (llm-wiki 폴더) | 기억 원본 Markdown. 쓰기 검증(publish-draft, `patch-page`, `review propose`), 세션 파일 렌더링과 커서, 근거 사본 | 회상, 후보 고르기, 순위 |
| vault-builder | Vault 도구 코드(`tools/wiki/`), `vault-map.json`과 그 설정 명령, 훅 실행기, 대체 경로(4.4.9, 동결) | 새 판단 규칙 |
| vault-graph | 색인, 검색, 회상, 정리 흐름과 그 재료, 쓰기 요청 만들기(draft), Graph Home 기록 | Vault 파일 직접 쓰기, LLM 호출, `vault-map.json` 쓰기 |

이 표에서 나온 개정 원칙 셋:

1. vg가 이미 가진 정보로 풀 수 있으면 Vault에 새 쓰기를 만들지 않는다. 리뷰1은 `vault-map.json`의 연결 정보로 푼다(4.4.2).
2. Vault 도구에 이미 있는 쓰기 형식을 먼저 쓴다. 리뷰4와 리뷰6은 기존 `patch-page`(`vault-builder:tools/wiki/lib/draft_patch.py:26-33`)로 푼다(4.4.4, 4.4.13).
3. 세션 파일의 파트 번호와 커서는 Vault 도구가 소유한다. vg는 색인할 때 같은 세션의 파일을 함께 본다(리뷰2·3, 4.2.12, 4.2.13).

### 4.1 용어

이 spec은 아래 용어를 한 뜻으로만 쓴다.

| 용어 | 뜻 |
|---|---|
| 원본 jsonl | Claude Code(`$HOME/.claude/projects/`)나 Codex(`$HOME/.codex/sessions/`)가 쓰는 세션 기록 파일 |
| adapter | 에이전트 하나의 원본 jsonl을 정규화 JSONL로 바꾸는 vg 코드. 에이전트마다 하나다 |
| 정규화 JSONL | 스키마 `vg-session-jsonl/1`의 세션 파일. 세션 하나가 파일 하나다. 기계용 정본이다 |
| export 폴더 | 사용자가 정한 Vault 밖 경로. 원본 사본(`raw/`)과 정규화 JSONL(`normalized/`)이 들어간다 |
| 세션 파일 | Vault `raw/sessions/` 아래 세션 md 파트 파일. `vault-session/v1`(지금 형식)과 `vault-session/v2`(새 형식)가 있다. Vault 도구가 쓰고, 한 번 쓰면 바뀌지 않는다 |
| 교환 | 사람 턴 하나와, 다음 사람 턴 전까지 같은 에이전트의 턴들. 서브에이전트는 `agent_id`마다 따로 교환을 만든다. v2에서는 교환 id(첫 사람 턴 uuid, Codex는 `turn_id`)를 가진다 |
| 창 | 교환 안에서 자른 겹치지 않는 조각. 세션 파일의 원문 조각은 모두 창이다 |
| 교환 메타 | 교환의 도구 횟수, 건드린 파일, 실행한 명령, 오류 수, 결과(`outcome`). 키워드 색인에만 들어간다 |
| `derived` 조각 | 다음 spec(backlog B-2)의 용어. 로컬 언어 모델이 교환마다 만들 요약과 예상 질문. 이 spec에서는 만들지 않는다 |
| 임베딩 입력 | 모델에 넣는 문자열. 조각 본문과 조각기가 정한 머리말로 만든다 |
| 임베딩 키 | `sha256(임베딩 모델 spec 키 + 임베딩 입력)`. 이 값이 바뀔 때만 다시 임베딩한다 |
| 메타데이터 지문 | 임베딩과 상관없는 벡터 메타데이터(`index_revision`, `source_role`, provenance family, 백엔드 스키마 버전, `chunker_version`)의 해시 |
| 벡터 목록 표 | 세대 안 SQLite 표. 벡터마다 `vector_id`, `vault_id`, `chunk_id`, 임베딩 키, 메타데이터 지문을 둔다 |
| 임베딩 캐시 | Graph Home 안, 세대 밖의 SQLite. 임베딩 키 → 벡터. 지워도 다시 만든다 |
| 정리 후보 | 기억으로 옮길지 판단할 대상. 반영되지 않은 L1 노트, 어떤 wiki 페이지도 근거로 쓰지 않은 세션 교환, 병합 후보, 폐기 후보 네 종류다 |
| 정리 꾸러미 | vg가 결정적으로 만든 정리 후보 목록. 후보마다 비교할 기존 페이지가 붙는다 |
| L3 목록 | 열린 일, 현재 결정, 교정·규칙 목록. vg가 조회할 때 색인에서 계산한다. 저장하지 않는다 |
| brief | 프로젝트 목표, 구조, 지켜야 할 제약, 다음 단계를 적은 Vault 페이지. 에이전트가 판단해 기존 쓰기 경로로 쓴다 |
| 대체 경로 | vg가 없는 사용자를 위한 vault-builder 구성(`memory-cleanup`, `maps build` 프로젝트 요약, `recall.sh`, `/project-memory`). 이 spec 뒤 동결한다 |

### 4.2 이슈A 세션 문서 형식과 임베딩 방식

#### 4.2.1 전체 흐름

1. 원본 jsonl → adapter → 정규화 JSONL. vg가 한다(4.2.2).
2. 정규화 JSONL과 원본 사본 → export 폴더. vg가 한다. 사용자가 경로를 정했을 때만 남는다(4.2.4).
3. 정규화 JSONL → `vault-session/v2` 세션 파일. Vault 도구 `sessions capture --normalized`가 렌더링하고 쓴다(4.2.5, 요청S10). vg는 언제, 어떤 정규화 파일을 넘길지만 정한다.
4. 세션 파일 → 조각, 키워드 행, 벡터. vg 색인이 한다. v2는 `session-exchange-v2`(4.2.6), v1은 `session-exchange-v1`(4.2.7)로 조각 낸다.
5. 검색은 창으로 찾고 교환 단위로 돌려준다(4.2.6-6).

두 층으로 나누는 이유: 정규화 JSONL은 손실이 가장 적고 파싱이 쉬워 다시 렌더링하는 기준이 된다. 반면 Obsidian에서 읽기, git diff, 줄 위치, 지금의 FTS와 조각기는 모두 markdown을 전제로 한다(조사 session-format 2절 비교표).

#### 4.2.2 adapter와 정규화 JSONL `vg-session-jsonl/1`

- 새 기능 영역 M19 `src/vault_graph/operation/sessions/`. 허용 가져오기는 M01뿐이고, 어떤 영역도 M19를 가져오지 않는다. 파일 읽기와 쓰기는 `interface/composition/adapters/`가 한다. M19는 레코드를 받아 정규화 줄을 돌려주는 순수 코드다.
  - `class SessionAdapter(Protocol)`: `agent: str`, `version: str`, `normalize(records: Iterable[SourceRecord]) -> Iterator[NormalizedLine]`
  - `CLAUDE_CODE_ADAPTER_VERSION = "claude-code/1"`
  - `def redact(text: str) -> RedactedText` (가림 규칙 `vg-redact/1`)
- 파일 한 개 = 세션 하나. 첫 줄은 `session`, 이어서 `exchange`와 그 교환의 `turn`들이 순서대로 온다. 모든 줄에 `schema`와 `kind`가 있다.

| kind | 필드 |
|---|---|
| session | `session_id`, `agent`(`claude-code`, `codex`), `agent_version`, `adapter`, `project`, `cwd`, `git_branch`, `git_commit`, `parent_session_id`, `title`(에이전트가 만든 제목임을 표시), `started_at`, `ended_at`, `source_paths`(export 폴더 기준), `source_sha256` |
| exchange | `exchange_id`, `seq`, `agent_scope`(`main` 또는 `subagent:<agent_id>`), `subagent_type`, `parent_tool_use_id`, `started_at`, `ended_at`, `closed`, `prompt_source`, `tools`(이름 → 횟수), `files_touched`(이름순), `commands`(앞 160자, 가림 뒤), `errors`(개수), `outcome` |
| turn | `turn_id`, `parent_id`, `exchange_id`, `role`, `turn_kind`(`human`, `assistant_text`, `tool_only`, `notification`, `meta`, `compact_summary`), `at`, `agent_id`, `sidechain`, `text`(가림 뒤), `actions`: [{`tool`, `call_id`, `target`, `ok`, `error_head`(오류 첫 줄 200자, 가림 뒤)}] |

- `outcome`은 정해진 값 넷 중 하나다: `answered`, `tool_error_unresolved`, `interrupted`, `open`. 규칙은 조사 session-format 2.1을 따른다. LLM 판단을 넣지 않는다.
- 넣지 않는 것: 도구 결과 본문, thinking·reasoning(비어 있거나 암호화), attachment, api-request, 토큰 기록.
- Claude Code adapter 규칙(구현한다)
  - 사람 턴: `type: user`이고 `turnOrigin: human` 또는 `origin.kind: human`. 두 필드가 없는 옛 레코드는 본문이 `<`로 시작하지 않는지로 판단한다. `isMeta`, `tool_result`, `isCompactSummary`는 사람 턴이 아니다(`turn_kind`는 각각 `meta`, `tool_only`, `compact_summary`).
  - 행동 대상: `tool_use.input`의 `file_path`, `command`, `url`, `query`, `subagent_type`.
  - 성공 여부: `tool_result.is_error`, `toolUseResult.interrupted`.
  - 서브에이전트: `<session_id>/subagents/agent-<id>.jsonl`과 `.meta.json`의 `agentType`, `toolUseId`.
  - 순서: `parentUuid` 트리와 `timestamp`. 같은 uuid는 한 번만 쓴다.
- 결정성: 같은 원본 바이트와 같은 adapter 버전이면 정규화 JSONL 바이트가 같다. 줄 안 키 순서는 고정이고, 시각은 원본 값을 그대로 쓴다.
- 버전: 필드를 더하면 `vg-session-jsonl/1` 그대로, 뜻을 바꾸면 `/2`로 올린다. 원본 형식이 바뀌면 adapter 버전만 올린다(조사 session-format 2.3).

#### 4.2.3 Codex adapter 계약 (구현은 backlog B-1)

- 버전 `codex/1`. 입력은 `$HOME/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl`.
- 필드 대응

| 공통 필드 | Codex 원본 |
|---|---|
| session | `session_meta`(`id`, `cwd`, `git.branch`, `git.commit_hash`, `cli_version`, `parent_thread_id`) |
| 사람 턴 | `event_msg:item_completed`의 `UserMessage`. 없으면 `response_item:message` role `user`(`developer` 제외) |
| assistant 텍스트 | `AgentMessage` |
| 행동 | `CommandExecution.command`(`exit_code`, `status`), `FileChange.changes`의 경로 키, `McpToolCall.server/tool` |
| 교환 id | `turn_id`. 경계는 `task_started`, `task_complete`, `turn_aborted` |
| 서브에이전트 | `SubAgentActivity.agent_thread_id` |
| 압축 요약 | `compacted.message` |
| 순서 | `ordinal` |

- `reasoning`은 암호화되어 넣지 않는다.
- backlog B-1 완료 조건: Codex 고정 파일 세 개(버전이 다른 `cli_version`)로 A-1과 같은 검사가 통과하고, `vg session export --agent codex`가 동작한다. 수집 훅은 Codex 쪽 훅 연결 방법을 확인한 뒤 정한다(위험A7).

#### 4.2.4 `vg session export`

- CLI: `vg session export --agent {claude-code,codex} --out PATH [--session ID | --since DATE | --all] [--raw/--no-raw] [--recapture]`.
- `--recapture`: export한 각 세션의 정규화 파일로 훅 실행기 `capture --direct --normalized <파일> --rerender`를 실행해 v2 파트를 쓰게 한다(4.2.12-4). 사람이 이전할 때만 쓰는 선택이다. Vault 고르기는 지금처럼 실행기가 한다.
- 쓰는 곳
  - `--raw`(기본): `PATH/raw/<agent>/<session_id>/` 아래에 원본 jsonl, `subagents/`, `.meta.json`을 바이트 그대로 복사한다. 가림하지 않는다.
  - 늘: `PATH/normalized/<agent>/<session_id>.jsonl`.
- 지키는 것
  - `PATH`가 Graph Home에 등록된 Vault나 `vault-map.json`의 Vault 안이면 쓰지 않고 오류로 끝낸다.
  - `PATH`가 git 작업 트리 안이거나 알려진 동기화 폴더(iCloud Drive, Dropbox, Google Drive, OneDrive 경로) 안이면 표준 오류에 경고 한 줄을 낸다. 쓰기는 한다.
  - 만드는 폴더 권한은 0700, 파일은 0600이다.
  - 같은 세션의 `source_sha256`이 같으면 다시 쓰지 않는다. 원본이 자랐으면 정규화 파일을 새로 쓰고, 원본 사본은 덮어쓴다.
  - Codex는 B-1 전까지 "adapter 없음" 오류로 끝난다.
- 설정: Graph Home `configs/session-export.json`(`path`, `agents`, `raw`). 이 파일이 있으면 `vg hook capture`가 수집 때마다 같은 export를 한다. 그래서 Claude Code가 30일 뒤 원본을 지우기 전에 사본이 남는다. 형식 확인과 읽기·쓰기는 M01 `operation/scope/`의 새 파일 `session_export_settings.py`가 맡는다.

#### 4.2.5 `vault-session/v2` 세션 파일 (Vault 도구가 렌더링, 요청S10)

vg는 이 형식을 쓰지 않고 읽기만 한다. vault-builder에 요청하는 계약은 다음과 같다(조사 session-format 2.2).

- frontmatter: `schema: vault-session/v2`, `renderer: vg-session-md/2.<M>`, `source_schema: vg-session-jsonl/1`, `agent`, `session_id`, `part`, `first_exchange_id`, `last_exchange_id`, 그리고 v1의 `project`, `cwd`, `collected_at`, `trigger`, `redactions`, `body_sha256`.
- 본문
  - 교환은 `## <제목 앞부분> <날짜 시각> · <교환 id 앞 8자>` 제목, 바로 다음 줄에 숨은 메타 줄 `<!-- vg:exchange id=<uuid> scope=<agent_scope> tools=<이름:횟수,...> errors=<n> outcome=<값> files=<경로,...> -->`.
  - 턴은 `### <role> · <시각> · <턴 id 앞 8자>` 제목과 본문.
  - 도구 전용 assistant 턴은 바로 앞 텍스트 턴 아래 행동 목록 한 줄(`- Edit \`src/a.py\``, `- Bash \`pytest -q\` → 실패: <오류 첫 줄>`)로 접는다.
  - 서브에이전트 교환은 파일 끝 `## Subagent <agent_id> · <type>` 절에 모은다.
- 파트 파일에는 닫힌 교환만 쓴다. 열린 마지막 교환은 다음 수집이나 세션 끝에 쓴다. 그래서 교환이 두 파일에 걸치지 않는다.
- 같은 정규화 입력과 같은 renderer 버전이면 같은 바이트를 낸다.
- 비밀값 가림: Vault 도구가 자기 규칙(`vault-builder:tools/wiki/lib/session_capture.py:258-277`)을 렌더링 때 한 번 더 적용한다. vg adapter의 가림과 이중이 된다(위험A8).
- 수집 흐름(`vg hook capture`): 훅 JSON의 `transcript_path`를 Claude Code adapter로 정규화해 OS 임시 폴더(export 설정이 있으면 export 폴더)에 쓰고, 훅 실행기 `vault_hooks.py capture --direct --normalized <파일>`을 실행한다. Vault 고르기는 지금처럼 실행기와 Vault 도구가 한다. 실행기나 Vault 도구가 `--normalized`를 모르면(종료 코드 2) 지금의 `capture --direct`로 원본 경로를 넘겨 v1 파일을 쓰게 한다. vg가 수집에서 "시점"에 더해 "넘길 정규화 파일"을 정하므로 `AGENTS.md` 경로3 문장이 바뀐다(4.4.8 문장5, 승인됨).

#### 4.2.6 조각기 `session-exchange-v2`

1. 조각기 선택: 새 파일 `src/vault_graph/indexing/ingestion/chunker_selection.py`(M02)의 `def select_chunker(extracted: ExtractedDocument) -> DocumentChunker[ChunkDraft]`. frontmatter `schema`가 `vault-session/v2`면 `session-exchange-v2`, `vault-session/v1`이면 `session-exchange-v1`, 모르는 `vault-session/*`면 일반 조각기와 경고 한 줄, 그 밖은 지금의 `DocumentWindowChunker`. `DocumentNormalizer`(`document_normalizer.py:51-76@abc77e7`)는 고른 조각기의 `version`을 조각 id와 `chunker_version`에 쓴다.
2. 임베딩 입력 소유: `DocumentChunker` Protocol(`document_chunking.py:17-23@abc77e7`)에 `embedding_input(section_path, text) -> str`을 더한다. 일반 조각기는 지금의 `contextual_embedding_text`를 그대로 돌려준다. 벡터 색인(`vector_index_adapter.py:130, 206@abc77e7`)은 새 함수 `embedding_input_for(chunk: ChunkSnapshot) -> str`(M02)을 부른다.
3. 교환 읽기: `##` 제목과 숨은 메타 줄로 교환 id와 교환 메타를 읽고, `###` 제목으로 턴을 읽는다. 사람 턴 판단에 휴리스틱을 쓰지 않는다(Vault 렌더러가 adapter의 `turn_kind`를 제목 role로 옮긴다).
4. 창 자르기: 교환 안 턴 본문과 행동 목록 줄을 순서대로 이어 공백 토큰 96개 이하로 자른다(§10.2에서 160에서 96으로 줄였다). 겹치지 않는다. 숨은 메타 줄은 창 본문에 넣지 않는다. 교환이 바뀌면 새 창을 연다.
5. 창 `section_path`: (`Session <날짜> part<N>`, `Q: <교환 첫 사람 턴 앞 80자>`). 서브에이전트 교환이면 첫 값 뒤에 ` subagent <agent_id>`.
6. 부모 단위: 창마다 `parent_key = <session_id>:<exchange_id>`와 `parent_locators`(교환 전체 줄 범위)를 둔다. `ChunkSnapshot`에 선택 필드 두 개를 더한다: `parent_key: str | None`, `parent_locators: tuple[SourceLocator, ...]`. 일반 문서는 `None`과 빈 튜플이다. M05 결과 조립(`retrieval/search/evidence_result_assembly.py`)은 같은 `parent_key`의 창들을 가장 높은 순위의 창 하나로 묶고, 결과 위치를 `parent_locators`로, 발췌를 그 창 본문으로 둔다. 묶인 창 수는 결과 설명에 적는다.
7. 임베딩 입력: `Session: <project> <날짜> part<N>`, `Question: <교환 첫 사람 턴 앞 200자>`, 빈 줄, 창 본문. 숨은 메타 줄과 교환 메타는 넣지 않는다.
8. 교환 메타의 키워드 색인: 같은 교환의 모든 창의 키워드 행 `frontmatter` 열(발견A12)에 `files: … commands: … tools: … errors: <n> outcome: <값>`을 더한다. `text` 열과 임베딩 입력에는 넣지 않는다. `ChunkSnapshot`에 선택 필드 `keyword_metadata: str | None`을 더하고 키워드 색인이 이 값을 `frontmatter` 열 끝에 붙인다. §10 단계B(`sqlite-keyword-v3`)부터 `frontmatter` 열은 frontmatter 전체 JSON이 아니라 tags, summary, 이 값만 담는다.
9. 조각 id: `stable_id("chunk", "session-exchange-v2", vault_id, session_id, exchange_id, agent_scope, 창 번호)`. 파일 경로와 renderer 버전에 묶이지 않는다. 같은 교환 id가 두 파일에 있으면 경로 사전순으로 앞 파일만 색인하고 경고 한 줄을 낸다.
10. 위치(`source_locators`): 창에 든 줄 범위. 형식은 지금 markdown 리더의 `SourceLocator`(`src/vault_graph/indexing/ingestion/markdown_parser.py:418-428@abc77e7`)와 같다.
11. 모델 토큰 검사: 임베딩 입력이 모델 토큰 512를 넘는 창 수를 색인 결과 경고에 적는다. 창 경계는 공백 토큰 수로만 정한다.
12. 조각기 버전 이름: 창 크기를 바꾼 뒤 `chunker_version`은 `session-exchange-v2-w96`, `session-exchange-v1-w96`이다. 이 문서의 `session-exchange-v2`·`-v1`은 조각기 이름이고, 버전 문자열은 창 크기를 뒤에 붙인다. 조각 id(9번, 4.2.7)의 첫 값도 이 버전 문자열이라, 창 크기를 바꾸면 모든 세션 창이 한 번 새 id로 바뀐다.

#### 4.2.7 v1 세션 파일 (`session-exchange-v1`)

원본이 이미 지워진 v1 파일은 계속 색인해야 한다. 지금 일반 조각기 대신 교환 조각기로 바꾼다. 규칙은 v2와 같고 다음만 다르다.

- 턴은 `## <timestamp> <role>`, `## <timestamp> subagent <agent_id> <role>` 제목으로 읽는다. 사람 턴은 role `user`이고 본문이 `<`로 시작하지 않는 본 에이전트 턴이다.
- 본문 마지막 `Tools: a, b` 줄을 도구 목록으로 떼어 내고, 도구 전용 턴은 창 본문에서 뺀다. 도구 이름은 `keyword_metadata`의 `tools:`로 간다.
- 파일 첫 턴이 사람 턴이 아니면 "이어진 교환"이고 `section_path` 둘째 값은 `Q: (이전 파트에서 이어짐)`이다.
- 교환 id가 없으므로 `parent_key`는 `<path>:<교환 첫 턴 제목>:<출현 순번>`이다.
- 조각 id: `stable_id("chunk", "session-exchange-v1", vault_id, path, 교환 첫 턴 제목, 같은 제목의 출현 순번, 창 번호)`. v1 파일은 바뀌지 않으므로 안정적이다.
- 같은 세션의 v1과 v2가 함께 있으면, v2 교환의 시각 범위(`started_at`~`ended_at`)와 겹치는 v1 교환을 색인에서만 뺀다. Vault 파일은 옮기거나 지우지 않는다. v1에만 있는 교환은 그대로 색인한다(9.3 질문11).

#### 4.2.8 다음 spec을 위한 메모: `derived` 조각 (backlog B-2)

로컬 언어 모델 단계는 이 spec에서 만들지 않는다(9.3 질문12). 이 spec의 코드, 설정, 기준에는 `derived`가 없다. 다음 spec이 이 단계를 설계할 때 지켜야 할 조건만 남긴다(조사 session-format 결정8·9).

- 이 spec의 기준선(4.2.10 (c) 단계)과 비교해 교환 단위 recall@5가 오를 때만 기본값으로 켠다. 기본값은 꺼짐이다.
- 결정적 검색을 지키는 규칙
  1. 원문 창의 `text`, 조각 id, `source_locators`, 임베딩 입력은 켜기 전과 바이트 단위로 같다.
  2. `derived` 조각은 인용 본문으로 쓰지 않는다. 근거를 열면 원문 교환이 열린다.
  3. 결합 순위(`src/vault_graph/retrieval/search/candidate_ranking.py:12-55@abc77e7`)에서 `derived` 신호의 가중치는 keyword·vector보다 낮게 시작하고(조사 제안 0.5), `parent_key`로 원문 교환에 합쳐 같은 교환이 두 번 나오지 않는다.
  4. `derived`를 빼는 검색 모드를 두고, 측정1과 결정성 시험은 그 모드로 돌린다.
  5. `derived` 텍스트는 Vault에 쓰지 않는다.
- 원칙1(`docs/SPEC.md:59`)의 "요약을 vault-graph 안에서 생성하지 않는다"에 예외 문장이 필요하다. 그 문장은 다음 spec의 gate에서 정한다.
- 이 spec이 다음 spec을 위해 미리 해 두는 것: 부모 단위(`parent_key`)와 결과 묶기(4.2.6-6). `derived` 조각은 같은 `parent_key`로 붙을 수 있다.

#### 4.2.9 결정적 검색에 미치는 영향

| 대상 | 바뀌는 것 | 바뀌지 않는 것 |
|---|---|---|
| 키워드 검색 | 세션 조각이 창 단위가 된다. "Bash"만 맞는 결과가 사라진다. 파일 경로, 명령, 오류 수로 교환을 찾는다 | §10 이전에는 일반 문서의 키워드 행과 FTS 스키마(열 다섯 개)가 바뀌지 않았다. §10 단계B에서 `aliases` 열이 더해져 여섯 개가 되고, frontmatter 열 내용, 열 가중치, 한국어 조사 처리가 바뀐다(§10.6) |
| 의미 검색 | 세션 조각의 벡터가 모두 새로 만들어진다 | §10 이전에는 일반 문서의 벡터가 바뀌지 않았다. §10 단계C에서 wiki 페이지는 `wiki-page-window-v1`으로 다시 조각 내고 한 번 다시 임베딩한다 |
| 결과 단위 | 세션 결과는 교환 하나가 결과 하나다 | §10 단계A부터 일반 문서도 문서 하나가 결과 하나다(`document_id`로 묶음) |
| 위치 표시 | 세션 결과의 위치가 교환 전체 줄 범위다 | `SourceLocator` 형식, 파일 경로 |
| 인용 검증, 근거 id | 세션 조각을 가리키던 근거 id(`src/vault_graph/context/answer/evidence_planner.py:468-470@abc77e7`)가 새 id로 바뀐다. 전환 전 답변의 세션 근거는 다시 열리지 않는다 | wiki 페이지가 `raw/sessions/<파일>` 경로로 건 근거 |
| 그래프 | 세션 파일에서 뽑은 근거 행이 새 조각 id로 바뀐다 | 일반 문서의 그래프 |
| 측정1 벤치마크 | 순위가 바뀔 수 있다 | 판정 기준(문서 경로, 발견A10). 기대값 파일을 다시 만들지 않는다 |
| 결정성 | 없음 | 같은 Vault 파일로 두 번 색인하면 조각 id, 창 본문, 위치, 키워드 결과가 같다 |

#### 4.2.10 평가

- 세션 질의 세트: 한국어 질의 40~60개, 줄마다 `{"id", "question", "expected_exchanges": [exchange_id 또는 v1 parent_key], "kind"}`. `kind`는 `decision`, `how`, `file`, `error`, `paraphrase`. 사람이 기대 교환을 고른다. 개인 세션 내용을 담으므로 저장소 밖(Graph Home 또는 사용자 경로)에 둔다.
- 지표: 교환 단위 recall@5, recall@10, MRR. 같은 교환의 여러 창은 한 번만 센다. 보조로 `kind`별 recall, 상위 10개 중 서브에이전트 교환 비율, 재색인 시간, 최대 RSS.
- 비교 단계: (a) 지금, (b) v1 + `session-exchange-v1`, (c) v2 + `session-exchange-v2`. (c)가 LLM 없는 기준선이고, 다음 spec의 `derived` 단계는 이 값과 비교한다.
- 측정 도구: 새 파일 `tests/benchmarks/measure_session_recall.py`. 측정1 벤치마크와 같은 실행 방식(하위 프로세스, 결과 파일은 저장소 밖, 합계만 `docs/design/reports/`).
- 모델은 `e5-small` 그대로다. 같은 조건에서 다시 잰 값은 A-8의 기준 확인으로만 쓴다.

#### 4.2.11 이전 순서

1. vg: adapter, 정규화 JSONL, export(S4). 이 단계만으로 원본 보존이 시작된다.
2. vault-builder: `sessions capture --normalized`와 v2 렌더러(요청S10). 기존 v1 파일은 그대로 둔다.
3. vg: v1·v2 조각기와 부모 단위 결과(S5), 수집 연결(S6).
4. 원본이 아직 남은 세션(Claude Code 기본 30일)은 `vg session export --recapture`로 v2를 다시 쓸 수 있다(4.2.12-4). 이때 같은 세션의 v1과 v2가 함께 생기며, 겹친 v1 교환은 색인에서만 뺀다(4.2.7).
5. 원본이 없는 v1 파일은 `session-exchange-v1`로 계속 색인한다. 세션 파일에 `document-block-window-v2`는 더 쓰지 않는다.

#### 4.2.12 v1에서 v2로 넘어갈 때 파트 번호와 커서 (리뷰3)

파트 번호와 커서의 주인은 Vault 도구다. 지금 Vault 도구는 별도 상태 파일 없이 그 세션의 가장 높은 파트 파일 frontmatter에서 커서(`last_turn_uuid`, `last_turn_at`)를 읽고, 새 파트 번호를 그 번호 + 1로 정한다(`vault-builder:tools/wiki/lib/session_capture.py:483-511, 626-633`). v2도 이 규칙을 그대로 쓴다. 요청S10의 계약에 아래를 더한다.

1. 이어 쓰기(기본): `sessions capture --normalized`는 같은 세션의 가장 높은 파트가 v1이든 v2든 그 파일의 커서 뒤 턴만 쓴다. 파트 번호는 가장 높은 번호 + 1이다. 그래서 한 세션의 파트 번호는 v1과 v2를 통틀어 한 줄로 이어진다.
2. v2 파트는 커서로 `last_turn_uuid`, `last_turn_at`에 더해 `last_exchange_id`를 frontmatter에 남긴다. v1 파트에는 `last_exchange_id`가 없으므로, v1 다음 첫 v2 파트는 `last_turn_uuid`로 이어 쓸 위치를 찾는다.
3. 이어진 교환: 커서 뒤 첫 턴이 사람 턴이 아니면 그 교환은 앞 파트에서 시작한 교환이다. 교환 id는 정규화 JSONL의 원래 교환 id(그 교환 첫 사람 턴 uuid)를 그대로 쓰고, 숨은 메타 줄에 `continued=1`을 더한다. 이 교환의 `started_at`은 이 파트에 쓴 첫 턴 시각이다. 그래서 4.2.7의 시각 겹침 판단에서 앞 v1 파트의 교환과 겹치지 않는다.
4. 다시 쓰기(선택): `sessions capture --normalized --rerender`는 커서를 보지 않고 닫힌 교환 전체를 새 파트(가장 높은 번호 + 1부터)에 쓴다. 기존 파일은 그대로 둔다. 원본이 남은 세션을 v2로 옮길 때(4.2.11-4)만 쓴다. 겹친 v1 교환은 vg가 색인에서만 뺀다(4.2.7, 9.3 질문11).
5. vg는 파트 번호와 커서를 계산하지 않는다. `vg hook capture`는 지금처럼 정규화 파일만 넘기고, `--rerender`는 사람이 실행하는 이전 명령 `vg session export --recapture`(4.2.4)에서만 붙인다.

#### 4.2.13 증분 색인에서 같은 세션 파일을 함께 다시 처리 (리뷰2)

v1·v2 겹침 판단(4.2.7)과 같은 교환 id 중복 판단(4.2.6-9)은 한 세션의 파일 여러 개를 함께 봐야 한다. 지금 증분 색인은 바뀐 파일만 다시 조각 낸다. 그래서 새 v2 파트가 생겨도, 바뀌지 않은 v1 파트의 겹친 교환이 색인에 남는다.

- 묶음 키: 세션 파일 frontmatter의 (`agent`, `session_id`). v1과 v2 모두 이 두 값을 가진다(`session_capture.py:548`).
- 증분 run의 계획 단계는 바뀐 파일, 새 파일, 지운 파일의 묶음 키를 모으고, 같은 묶음 키를 가진 파일을 모두 다시 조각 낸다. 바뀌지 않은 파일이라도 다시 조각 낸다. 그 파일의 조각 id와 임베딩 키가 같으면 4.3.2 규칙대로 모델 입력은 생기지 않는다.
- 4.3.3의 `(size, mtime_ns)` 사전 검사는 "파일을 읽을지"만 정한다. 묶음 키는 문서 표에 저장해 둔 값으로 찾으므로, 사전 검사로 건너뛴 파일도 묶음에 들어간다. 문서 표에 `session_group_key` 열을 더한다.
- provenance family(`supersedes`로 묶인 문서들)도 같은 방식으로 다룬다. 바뀐 문서가 속한 family의 다른 문서를 함께 다시 계획한다. family id는 이미 문서 표에 있다.
- 검증 규칙: 같은 Vault 상태에서 증분 결과와 full run 결과의 조각 id 집합, 키워드 행, 벡터 메타데이터가 같아야 한다(A-36).

### 4.3 이슈B+C 원인 5개의 근본 수정과 가속

원인을 고치는 것만으로 얻는 가속과, 그 뒤에 더하는 가속을 나눠 적는다. 가속 번호는 조사 index-performance 7절의 번호다. 이슈A의 새 조각기는 이 절의 설계를 바꾸지 않는다. 바뀌는 수치는 원인1 행뿐이다.

| 원인 | 근본 수정 | 바뀌는 곳 | 함께 얻는 가속 |
|---|---|---|---|
| 원인1 | 4.2 세션 조각기. 본 대화 교환 약 2,500개(조사 session-format 발견10)와 서브에이전트 교환을 창으로 자르면 세션 조각 28,330개가 수천 개로 준다(추정, 위험A1) | 4.2.6, 4.2.7 | 전체 조각 약 60% 감소(추정) |
| 원인2 | 계획을 세 묶음으로 나눈다. 임베딩 키가 다르면 임베딩, 임베딩 키는 같고 메타데이터 지문만 다르면 메타데이터만 갱신, 사라진 조각은 삭제 | 4.3.2 | 가속3 |
| 원인3 | 단기: 페이지 단위 목록 조회와 실패 격리. 근본: 벡터 목록 표 | 4.3.1 | 실패 run의 세대 복사 반복 제거 |
| 원인4 | 세대 준비를 APFS clone으로, 파일 `(size, mtime_ns)` 사전 검사, 바뀐 문서 단위 그래프 갱신 | 4.3.3 | 가속4, 가속5, 가속6 |
| 원인5 | 길이 정렬과 토큰 예산 배치, 배치마다 저장, CPU 메모리 아레나 끄기 | 4.3.4 | 가속1 |
| 추가 | 임베딩 캐시 | 4.3.5 | 가속2 |

#### 4.3.1 원인3 백그라운드 색인 실패

단기 수정(첫 묶음 S0):

- `ChromaStore.export_manifest`(`chroma_store.py:285-304@abc77e7`)는 컬렉션마다 `collection.get(include=["metadatas"], limit=N, offset=k)`를 반복한다. N은 `_max_batch_size`(`chroma_store.py:29-40@abc77e7`)와 같은 값을 넘지 않는다.
- `VectorIndexer.apply`(`vector_index_adapter.py:178-197@abc77e7`)는 `plan` 호출도 `try` 안에 둔다. 계획 실패도 `VectorApplyResult(failed=True)`가 되어, 메타데이터와 그래프는 발행되고 `vg status`는 벡터가 오래됐다고 보인다.
- 재시도 간격: 세션 시작 백그라운드 색인(`src/vault_graph/interface/cli/hook_commands.py:162-237@abc77e7`)은 Vault마다 벡터 실패를 Graph Home `logs/vector-index-failures.json`에 남긴다. 항목은 `{vault_id, error_digest, first_failed_at, last_failed_at, count}`다. 같은 `error_digest`로 실패한 Vault는 마지막 실패에서 `min(2^(count-1), 24)`시간이 지나기 전에는 벡터 색인을 다시 하지 않는다. 메타데이터·그래프 색인은 막지 않는다. 성공하면 항목을 지운다.
- 경고: `vg hook session-start`는 실패 항목이 있으면 회상 출력 뒤 표준 오류에 "벡터 색인이 <Vault>에서 <N>시간째 실패 중: <오류 요약>" 한 줄을 낸다.

근본 수정(S2):

- 벡터 목록 표를 세대의 `vector/manifest.sqlite3`에 둔다. 포트는 `src/vault_graph/storage/interfaces/`, 구현은 `src/vault_graph/storage/local/`.
  - `class VectorManifestStore(Protocol)`: `rows(vault_ids: tuple[str, ...]) -> tuple[VectorManifestRow, ...]`, `apply(upserts, metadata_updates, deletions) -> None`, `count(vault_id: str) -> int`
- 계획(`VectorIndexer.plan`)은 Chroma 대신 이 표를 `WHERE vault_id IN (...)`로 읽는다.
- Chroma 쓰기와 표 쓰기는 같은 배치에서 한다(4.3.4). Chroma 쓰기가 성공한 배치만 표에 쓴다.
- 표가 없거나 Vault별 행 수가 Chroma 컬렉션 수와 다르면, 그 run에서 Chroma를 페이지 단위로 읽어 표를 다시 만든다.

#### 4.3.2 원인2 문서 단위 재임베딩

- `packages/vector-index`의 일반 계획(`plan_index`)은 항목마다 지문 하나를 받는다. 항목에 선택 필드 `metadata_fingerprint`를 더하고, 계획 결과에 `metadata_updates`를 더한다. 선택 필드가 없으면 지금 동작과 같다. 독립 모듈 계약(`docs/SPEC.md` §8.3)에 필드를 더하기만 한다.
- `vector_index_adapter.py`
  - 임베딩 키: `sha256(_embedding_spec_key(spec) + "\n" + embedding_input_for(chunk))`. 지금 `_chunk_fingerprint`(`vector_index_adapter.py:343-353@abc77e7`)의 자리다.
  - 메타데이터 지문: `(index_revision, backend_schema_version, source_role, family id, chunker_version)`의 해시.
  - 저장된 쪽은 벡터 목록 표의 두 값을 쓴다.
- `metadata_updates`는 Chroma `collection.update(ids, metadatas)`로 메타데이터만 고친다. 임베딩 모델을 열지 않는다. `VectorStore` 포트에 `update_metadata(records) -> None`을 더한다.
- 처음 전환하는 run: 이전 세대 Chroma 메타데이터에는 임베딩 키가 없다. 저장된 `source_chunk_hash`, `chunker_version`, embedding spec이 모두 같고 `chunker_version`이 `document-block-window-v2`이면 임베딩 입력이 같다고 보고 임베딩 키만 채운다. 세션 조각은 조각 id가 모두 바뀌므로 해당하지 않는다.

#### 4.3.3 원인4 실행마다 드는 고정 비용

- 세대 준비(`projection_generation.py:92-98@abc77e7`): `shutil.copytree` 대신 M04 새 함수 `def clone_tree(source: Path, target: Path) -> Literal["clone", "copy"]`를 부른다. macOS에서 `clonefile(2)`로 폴더를 복제하고, 실패하거나 다른 운영체제면 `copytree`로 돌아가며 경고 한 줄을 낸다.
- 사전 검사(`src/vault_graph/indexing/metadata_indexer.py:161-218@abc77e7`): 문서 표에 `source_size`, `source_mtime_ns`를 더한다. 증분 run에서 두 값이 같으면 파일을 읽지 않는다. 다르면 지금처럼 `content_hash`로 확정한다. full run은 보지 않는다. 같은 세션 묶음이나 provenance family에 바뀐 문서가 있으면, 사전 검사로 건너뛴 문서도 다시 계획한다(4.2.13).
- 그래프(`src/vault_graph/indexing/graph_indexer.py:98-130, 244-300@abc77e7`): 바뀐 문서와 지운 문서의 근거 행만 지우고 다시 뽑는다. 엔티티와 관계는 근거 참조 수로 유지하고 0이면 지운다. scope 리비전은 run마다 기록한다. 바뀐 문서가 가리키거나 바뀐 문서를 가리키는 문서까지 다시 뽑는다. 마지막 코드 묶음(S13)에 두고 full run과 같은 결과인지로 검증한다(A-19).

#### 4.3.4 원인5 임베딩 메모리

- `embed_items`(`packages/vector-index/src/vector_index/indexing.py:129-160@abc77e7`, 조사 index-performance 6.1)를 배치 반복자로 바꾼다: `def iter_embedding_batches(items, provider, *, token_budget: int, max_batch_items: int) -> Iterator[EmbeddingBatch]`. 기존 `embed_items`는 이 반복자를 모아 돌려주는 함수로 남긴다.
- 배치: 임베딩 입력을 추정 토큰 수로 정렬하고 `항목 수 × 배치 안 최대 추정 토큰 ≤ token_budget`으로 자른다. 추정 토큰 수는 모델 토크나이저를 쓸 수 있으면 그 값, 없으면 UTF-8 바이트 수 ÷ 3이다. 기본 `token_budget` 16,384, `max_batch_items` 256.
- 배치마다 Chroma `upsert`와 벡터 목록 표를 쓴다. 중간에 죽으면 스테이징 세대는 발행되지 않고, 이미 계산한 벡터는 임베딩 캐시가 살린다.
- 아레나: 구성에 `cpu_mem_arena: bool`을 더해 fastembed `enable_cpu_mem_arena`로 넘긴다. 끈 쪽의 전체 재색인 시간이 켠 쪽보다 20% 넘게 길지 않으면 기본값을 끔으로 둔다.
- 설정 `embedding_batch_size`는 계속 받고 뜻이 "배치 항목 수 상한"이 된다. `embedding_token_budget`을 새 선택 설정으로 더한다.

#### 4.3.5 가속2 임베딩 캐시

- 위치: Graph Home `cache/embeddings.sqlite3`. 세대 밖이다. 지워도 다음 run이 다시 임베딩할 뿐이다(§0 규칙5).
- 표: `(embedding_key TEXT PRIMARY KEY, dimensions INTEGER, vector BLOB float32, last_used_run TEXT)`.
- 임베딩 전에 캐시를 찾고, 없는 것만 모델에 넣는다. 새 벡터는 배치마다 캐시에 쓴다.
- 발행이 성공하면 활성 세대 벡터 목록 표에 없는 키를 지운다.
- 임베딩 키에 모델 spec 키가 들어가 모델이 바뀌어도 섞이지 않는다.

### 4.4 이슈D vg 기억 관리

#### 4.4.1 역할과 원칙

| 일 | 맡는 쪽 | 근거 |
|---|---|---|
| 정리 후보 찾기, 비교할 기존 페이지 찾기, 병합·폐기 후보 점수, L3 목록 계산, 회상, 정리 흐름(언제, 무엇을, 어떤 순서로) | vg. 결정적이고 LLM이 없다 | 색인과 사용 기록이 vg에 있다. 원칙1 |
| 기억할 가치 판단, 문장 작성, 추가·수정·폐기·건너뜀 결정, `basis` 결정 | 세션 안 에이전트. vg MCP 도구와 prompt를 따라 한다 | 원칙1. 지금 쓸 수 있는 가장 강한 판단자다(조사 memory-management 3.1) |
| 검증, 저장, 검토 대기열, L1 원본 복사 | Vault 도구 | 9.1 질문3 "Vault는 저장소" |
| 추론 기억 승인, 출처가 다른 모순 결정 | 사람 | 품질 우선 |

- 관리 결정과 흐름은 모두 vg에 있다. vault-builder에는 판단 규칙을 새로 두지 않는다. 지금 vault-builder에 있는 판단 구성(`memory-cleanup`, `maps build` 프로젝트 요약, `recall.sh`, `/project-memory`)은 vg 없는 사용자를 위한 대체 경로로 동결하고, 이전 마지막 단계에서 제거한다(4.4.9).
- 한 줄 원칙: vg는 기계가 만든 내용을 Vault에 쓰지 않는다. Vault에는 에이전트나 사람이 판단한 내용만 Vault 도구로 들어간다.
- 로컬 언어 모델은 이 spec에 넣지 않는다(9.3 질문12). 이득이 있을 수 있는 곳은 쌓인 세션 교환에서 정리 후보 순서를 매기는 일 하나다. 다음 spec(backlog B-2)에서 4.4.10 평가로 결정적 거르기보다 재현율이 분명히 높은지 확인한 뒤 정한다.

#### 4.4.2 프로젝트 범위와 `sharable`

- M10 `context/memory/`에 규칙 함수 하나를 둔다. 회상(M08), `summarize_project_memory`, L3 목록, 정리 꾸러미가 모두 이 함수를 쓴다.
  - 시그니처는 `def page_in_project(frontmatter: Mapping[str, object], project_id: str | None, *, vault_scope: VaultProjectScope) -> bool`이다. `VaultProjectScope`는 (`linked_projects: frozenset[str]`, `sharable: bool`)이고 M17 `vault_map.py`가 `vault-map.json`에서 만든다(리뷰16).
- 규칙(리뷰1 반영)
  1. `project`가 이 프로젝트면 참. 다른 프로젝트면 거짓.
  2. `project`가 없고, 그 Vault를 연결한 프로젝트가 이 프로젝트 하나뿐이면 참. Vault 자체가 프로젝트 표시 역할을 한다.
  3. `project`가 없고, 그 Vault를 연결한 프로젝트가 둘 이상이면 그 Vault의 `sharable` 값.
- 규칙2의 이유: 지금 vault-graph Vault의 wiki 17쪽은 모두 `project`가 없다. 리뷰1이 지적한 대로, 규칙2 없이 `sharable` 기본값 false를 쓰면 프로젝트 Vault의 회상이 빈다. 페이지마다 `project`를 채우려면 Vault에 쓰기가 필요하지만, 연결 정보는 vg가 이미 읽는 `vault-map.json`에 있다(4.0 원칙1). 지금 `vault-map.json`에서 프로젝트 Vault 다섯 개는 각각 프로젝트 하나에만, personal Vault는 프로젝트 다섯 개에 연결되어 있다.
- 규칙2는 Vault 종류(`role`) 이름으로 분기하지 않는다(`docs/SPEC.md` 결정15). 연결된 프로젝트 수만 본다. 프로젝트 Vault가 나중에 두 프로젝트에 연결되면 그때부터 `sharable`을 본다.
- `sharable`는 `vault-map.json`의 `vaults.<name>.sharable`(불리언)다. `vault-map.json`의 주인은 vault-builder이고 vg는 읽기만 한다(`docs/SPEC.md` 원칙6). 필드와 설정 명령은 요청S4다.
- 뜻(9.3 질문15): true면 그 Vault의 `project` 없는 페이지를 연결된 모든 프로젝트의 세션 시작 기억 목록에 넣는다. false면 넣지 않는다. 어느 쪽이든 검색(`search_vault`, `vg search`, `build_context_pack`)에는 그대로 나온다. 이 규칙은 회상, L3 목록, 정리 꾸러미에만 쓰고 검색 범위에는 쓰지 않는다.
- 필드가 없으면 false로 다룬다. 둘 이상의 프로젝트에 연결된 Vault에만 `vg status`와 세션 시작 표준 오류에 "`<Vault>`의 `sharable`이 설정되지 않아 false로 다룸. 설정 방법: <요청S4 명령>" 한 줄을 낸다. 프로젝트 하나에만 연결된 Vault는 `sharable`을 보지 않으므로 안내하지 않는다.
- `recall.py:_in_project`(`358-363@abc77e7`)를 이 함수로 바꾼다. 같은 규칙 문장을 `docs/SPEC.md` §6 외부 계약에 적는다.

#### 4.4.3 `remember`가 쓰는 페이지의 계층 표시

- `RememberRequest`에 `project_id: str | None`을 더한다. MCP 쓰기 도구가 `cwd`로 찾은 프로젝트 id를 채운다. 사용자 입력은 늘지 않는다.
- `build_remember_draft`(`memory_drafts.py:33-64@abc77e7`)는 `project_id`가 있으면 frontmatter `project: <id>`를 넣는다. `memory_kind`가 `correction`, `rule`이면 `tags`에도 같은 값을 넣는다(대체 경로의 `maps.py:276`이 `tags`로 고르기 때문이다).
- `update_memory`는 현재 `project`를 바꾸지 않는다.

#### 4.4.4 정리 꾸러미와 판단 흐름

새 파일 `src/vault_graph/context/memory/memory_candidates.py`(M10). 후보 다섯 종류:

| 종류 | 찾는 규칙(결정적) | 후보 키 |
|---|---|---|
| L1 노트 | 프로젝트 L1 폴더의 노트(`MEMORY.md` 제외) 중 sha256이 연결 Vault `raw/imports/claude-memory/` 문서의 `raw_sha256`과 같지 않은 것. 판정은 색인 때 실행한 Vault `memory-scan --json` 결과와 같아야 한다 | `l1:<sha256>` |
| 세션 교환 | 색인된 세션 교환 중 어떤 `wiki/` 페이지도 그 세션 파일 경로를 근거로 적지 않은 것. 순서: 사람 턴에 교정 신호가 있는 교환, 결정 단어가 있는 교환, `outcome`이 `tool_error_unresolved` 뒤 방향을 바꾼 교환, 나머지(최신순) | `session:<parent_key>` |
| 병합 후보 | 같은 프로젝트 범위에서 임베딩 유사도가 높은 현재 페이지 쌍(임계값은 4.4.10 평가로 정함) | `merge:<경로1>|<경로2>` |
| 폐기 후보 | 고정이 아니고, (1) 근거로 가리키는 코드 경로나 심볼이 등록 저장소에서 사라졌거나 (2) 최근 90일 동안 회상에 주입만 되고 한 번도 열리지 않은 페이지. (2)는 Graph Home 사용 기록으로 센다 | `retire:<경로>` |
| brief 갱신 | 4.4.7의 갱신 규칙에 걸린 프로젝트. 비교 재료는 brief 뒤에 생기거나 바뀐 결정 페이지 목록이다 | `brief:<project>:<결정 목록 해시 12자>` |

- 후보마다 비교 재료를 붙인다: 같은 프로젝트 범위에서 비슷한 기존 페이지 상위 5개(키워드 + 벡터), 각 페이지의 status, `superseded_by`, 근거 날짜.
- MCP 읽기 도구 `list_memory_candidates(cwd=None, kinds=None, limit=20)`: 위 꾸러미를 돌려준다. 같은 색인과 같은 기록이면 같은 결과다. 결과에는 후보 키, 근거 위치(L1 사본 경로 또는 교환 위치), 비교 재료가 있다.
- MCP prompt `curate_memory`(`src/vault_graph/interface/mcp/mcp_prompts.py`): 에이전트에게 정해진 순서를 준다.
  1. `list_memory_candidates`를 부른다.
  2. 후보마다 하나를 고른다. 새 사실이면 `remember`. 기존 페이지의 claim 하나가 새 사실로 바뀌었으면 `supersede_claim`. 기존 페이지 보강이면 `update_memory`. 페이지 전체가 바뀌면 `retire_memory(replaced_by=...)`. 폐기된 기억이 다시 맞게 되었으면 `restore_memory`(4.4.13). 가치가 없으면 건너뜀. 모든 쓰기 도구 호출에 후보 키(`candidate_key`)를 함께 넘긴다.
  3. L1 노트를 근거로 쓸 때는 먼저 `import_auto_memory`로 Vault에 사본을 남기고, 돌려받은 `raw/imports/...` 경로를 근거로 쓴다. 세션 교환을 근거로 쓸 때는 후보 결과의 교환 위치(파일 경로와 교환 줄 범위)를 그대로 적는다.
  4. 근거 원문에 사용자 자신의 말이 있고 그 문장을 인용하면 `basis: stated`, 그 밖은 `inferred`. 경계 사례는 `inferred`.
  5. 한 번의 정리에서 `inferred` 제안은 10개까지.
  6. brief 갱신 후보가 있으면 정리 마지막에 brief를 고친다. brief가 없으면 `remember(kind="project")`, 있으면 `update_memory`로 쓴다(4.4.7).
- 건너뜀 기록: MCP 도구 `mark_candidates_reviewed(keys, cwd=None)`가 Graph Home `memory/reviewed.jsonl`에 `{candidate_key, at, outcome: "skipped"}`를 덧붙인다. 기록된 후보는 다시 올라오지 않는다.

claim 대체 쓰기 경로 (리뷰4):

- 지금 `update_memory`는 frontmatter를 두고 본문 전체를 바꾸는 upsert draft를 만든다(`src/vault_graph/operation/memory/memory_drafts.py:74-97@abc77e7`). 옛 claim을 대체 행으로 남기려면 에이전트가 표 전체를 다시 써야 하고, 빠뜨리면 Vault 검증이 거부한다.
- Vault 도구에는 이미 `patch-page` draft의 `supersede-claim` 편집이 있다. 맞는 claim 행 하나를 `superseded`로 바꾸고 `Superseded by:` 근거를 붙인 뒤 새 행을 그 아래 넣는다(`vault-builder:docs/agent/DRAFTS.md:19, 24`, `vault-builder:tools/wiki/lib/draft_patch.py:94-117`). vg의 `retire_memory`도 이미 `patch-page`를 쓴다(`memory_drafts.py:106-129@abc77e7`).
- 새 MCP 쓰기 도구 `supersede_claim(path, claim, new_claim, evidence, basis, cwd=None, vault=None, candidate_key=None)`. M18에 `build_supersede_claim_draft`를 더해 `patch-page` draft(`edits: [{op: "supersede-claim", claim, by: new_claim, status, evidence}]`)를 만든다. `basis`에 따라 publish-draft 또는 `review propose`로 보낸다. 새 Vault 기능이 필요 없다.
- claim 표가 없는 페이지(`quality.provenance`가 `claim`이 아님)에서는 Vault 도구가 거부한다. vg는 그 메시지와 "페이지 전체를 바꾸려면 `retire_memory(replaced_by=...)`" 안내를 돌려준다.

정리 후보가 목록에서 빠지는 규칙 (리뷰5):

1. 처리 기록: 쓰기 도구(`remember`, `update_memory`, `supersede_claim`, `retire_memory`, `restore_memory`, `import_auto_memory`)가 `candidate_key`를 받으면, 결과가 `published`나 `proposed`일 때 `memory/reviewed.jsonl`에 `{candidate_key, at, outcome}`을 덧붙인다. `rejected`나 `error`면 기록하지 않아 후보가 남는다. 그래서 `inferred` 제안이 검토 대기 중이어도 다음 정리에 다시 올라오지 않는다.
2. 세션 교환의 근거 판단은 교환 단위다. wiki 페이지가 세션 파일을 근거로 적을 때 교환 위치(파일 경로 + 교환 줄 범위, 또는 교환 id 앞 8자)를 함께 적으면 그 교환만 근거로 쓰인 것으로 본다. 파일 경로만 적은 근거는 어떤 교환도 빼지 않는다. `curate_memory` 3단계가 교환 위치를 근거에 적으라고 안내한다. `list_memory_candidates` 결과의 근거 위치가 이 형식이다.
3. 세션 교환 후보의 나이 상한: `started_at`이 180일 [가정]보다 오래된 교환은 후보에 올리지 않는다. 검색에는 그대로 나온다. 밀린 양이 끝없이 쌓이지 않게 하는 상한이다.
4. brief 갱신 후보 키는 `brief:<project>:<기준에 든 결정 페이지 경로와 updated의 sha256 앞 12자>`다(리뷰14). 같은 날 결정이 더 생겨도 키가 바뀌어 다시 올라온다.
- 사용 기록과 건너뜀 기록의 쓰임(9.3 질문14): 두 기록은 Graph Home에 두고 정리 후보를 고르고, 순서를 정하고, 보여 주는 데만 쓴다. 무엇을 쓸지는 에이전트가 정하고 Vault 검증을 거친다. 회상 순위에는 쓰지 않는다(결정32). Graph Home을 지우면 이미 건너뛴 후보가 한 번 다시 나오고, 폐기 후보 (2)가 90일 동안 비어 있다. 이 쓰임은 `docs/SPEC.md` §0 규칙5의 예외로 적는다. 예외 문장: "사용 기록과 정리 건너뜀 기록은 Graph Home에 두고 정리 후보 제안에만 쓸 수 있다. 회상과 검색 순위에는 쓰지 않는다. 기억을 쓸지는 에이전트가 정하고 Vault 검증을 거친다."
- 시작 방법: 세션 시작 회상의 정리 대기 한 줄(4.4.6)과, 사용자가 "기억 정리해"라고 할 때 `curate_memory`. 훅 안에서는 정리하지 않는다.
- 즉시 쓰기는 지금과 같다. 사용자가 직접 말한 교정·규칙·결정은 에이전트가 세션 중 `remember(basis="stated")`로 쓴다.

#### 4.4.5 L1 노트 읽기와 보존(경로4 `import-source`)

- 읽기: 새 어댑터 `src/vault_graph/interface/composition/adapters/auto_memory_reader.py`. Claude Code 설정(`CLAUDE_CONFIG_DIR`, `autoMemoryDirectory`, 프로젝트 폴더 이름 규칙)을 따라 `<key>/memory/`를 찾고 읽기만 한다. L1 파일을 고치거나 옮기거나 지우지 않는다.
- 반영 판정: 색인 run이 연결 Vault마다 Vault `memory-scan --json`을 읽기 전용으로 실행하고 결과를 Graph Home `memory/memory-scan-<vault>.json`에 둔다. vg의 sha256 판정과 다르면 Vault 결과를 쓰고 경고 한 줄을 낸다(판정 규칙의 주인을 한 곳에 둔다).
- 보존: MCP 쓰기 도구 `import_auto_memory(note, cwd=None, vault=None)`. vg가 Vault 명령 `import-source <note> --into raw/imports/claude-memory/ --json`(요청S8)을 실행한다. Vault 명령이 바이트를 복사하고 source 페이지를 만든다. 같은 sha256이면 아무것도 만들지 않고 기존 경로를 돌려준다. 저장 Vault는 결정12(기본 저장 Vault)로 고른다.
- M18 `operation/memory/`에 `ImportRequest`와 포트 `VaultImporter.import_source(vault_root, note_path, *, timeout_s) -> WriteOutcome`를 더한다. 실행 어댑터는 `vault_publish_cli.py` 옆에 둔다.

#### 4.4.6 회상

| 구획 | 내용 | 예산 |
|---|---|---|
| 구획A | 고정 기억(지금) | 400 |
| 구획L3 | brief 앞부분과 L3 목록(열린 일, 현재 결정, 교정·규칙) | 500 |
| 구획B | 범위 안 나머지 기억 | 남은 예산 |
| 구획C·D | 대체·폐기 알림, 검토 대기 수, 정리 대기 한 줄, brief 갱신 안내 한 줄 | 150 + 30 |

- 총 1,500토큰은 그대로다(`recall.py:38-50@abc77e7`). 구획L3를 만들지 못하면 그 구획만 빠지고 남은 예산이 구획B로 간다.
- 구획B 순서는 지금처럼 `updated` 내림차순이고 종류 가중치(교정·규칙 > 결정 > 기타)를 먼저 본다. 사용 기록(마지막으로 열린 때)은 순위에 쓰지 않는다. 쓰면 Graph Home을 지웠을 때 회상이 달라져 `docs/SPEC.md` §0 규칙5에 어긋난다. 조사 memory-management 3.7의 "최근성(마지막 fetched)" 제안은 따르지 않는다.
- 대체 제외: 페이지 status `superseded`, `deprecated`, `retired`는 지금처럼 뺀다. 더해서 페이지 본문 claim 표에서 상태가 `superseded`인 행을 회상 발췌와 L3 목록에서 뺀다. claim 표 형식은 Vault 규칙(`vault-builder:docs/agent/OPERATING-SCHEMA.md:192-200`)을 따른다. 규칙 함수는 M10의 `def current_claims(body: str) -> tuple[ClaimRow, ...]`.
- 정리 대기 한 줄: `- 정리 대기: L1 노트 <N>개, 근거로 쓰이지 않은 세션 교환 <M>개. 정리하려면 "기억 정리해"라고 말하세요.` 둘 다 0이면 넣지 않는다. 세는 규칙은 `list_memory_candidates`와 같다. 회상 시간 한도를 넘으면 빼고 경고 한 줄을 낸다. 새 파일 `src/vault_graph/context/pack/recall_backlog.py`.
- `MEMORY.md`는 Claude Code가 따로 넣는다. 지금 L1 노트와 sha256이 같은 사본만 근거로 가진 L2 페이지는 구획B 맨 뒤로 보낸다.

#### 4.4.7 L3: 목록은 vg 계산, brief는 Vault 페이지(혼합)

사용자가 판단을 맡겼고(9.3 질문10), 이 spec은 혼합으로 정했다. Vault는 판단된 지식의 저장소이고, 목록은 다시 계산할 수 있으며, "기계 생성물을 Vault에 쓰지 않는다"(4.4.8 문장4)와 맞기 때문이다.

- L3 목록: `summarize_project_memory`(`src/vault_graph/context/memory/project_memory.py:43-140@abc77e7`)를 넓혀, 회상과 MCP가 같은 함수로 열린 일, 현재 결정, 교정·규칙 목록을 회상·조회 시점에 색인에서 계산한다. Graph Home에도 Vault에도 저장하지 않는다. 범위는 4.4.2, 대체 제외는 4.4.6.
- brief 페이지(9.3 질문13): 프로젝트 기본 저장 Vault의 `wiki/projects/<project>.md`, frontmatter `type: project`, `project: <project>`. 프로젝트마다 하나다.
  - 에이전트가 판단해 기존 쓰기 경로로 쓴다. 처음은 `remember(kind="project")`, 그 뒤는 `update_memory`. vg는 brief 본문을 만들거나 고치지 않는다.
  - MCP `remember`의 `kind` 허용 값에 `project`를 더한다(`docs/SPEC.md` §5 호환 규칙: 허용 값 추가). `kind="project"`면 페이지 경로를 제목이 아니라 `cwd` 프로젝트 id로 정한다. 프로젝트가 정해지지 않으면 `rejected`다.
  - Vault 스키마의 `project` 종류와 경로 규칙은 요청S9다.
- brief 갱신 시점은 vg가 관리한다.
  - 기준: brief의 `updated` 뒤에 생기거나 `updated`가 바뀐 결정 페이지(`type: decision` 또는 `memory_kind: decision`, 범위 4.4.2, 대체·폐기 제외)의 수 N.
  - N이 기준값(5, [가정])을 넘거나 같으면 "brief 갱신 필요" 상태다. brief가 없고 범위 안 결정 페이지가 기준값 이상이어도 같다.
  - 이 상태에서 세션 시작 회상 구획D에 `- brief 갱신 필요: brief 이후 새 결정 <N>개. "기억 정리해"로 갱신하세요.` 한 줄을 넣고, `list_memory_candidates`가 brief 갱신 후보를 올린다(4.4.4). 갱신은 `curate_memory` 6단계가 다룬다.
  - 계산은 결정적이고 색인만 읽는다. 함수는 M10의 `def brief_staleness(brief: DocumentSnapshot | None, decisions: Sequence[DocumentSnapshot], *, threshold: int) -> BriefStaleness`.

#### 4.4.8 경계 문장 변경 (승인됨)

사용자가 일곱 문장을 모두 승인했다(9.3 질문9). S8(기억 단계1) 커밋 전에 `AGENTS.md`와 `docs/SPEC.md`에 넣는다(조사 memory-management 5절). §0 규칙5 예외 문장(4.4.4)도 같은 커밋에 넣는다.

1. 쓰기 경로4 `import-source`: L1 노트를 근거로 남길 때 vg가 Vault `import-source`를 실행한다. 복사는 Vault 명령이 한다. vg는 L1 파일을 고치거나 옮기거나 지우지 않는다. `AGENTS.md:9`의 "three such paths"가 "four"가 되고, `docs/SPEC.md:62`(원칙4)도 같다.
2. 읽기 전용 Vault 명령: 색인은 `memory-scan --json`, `review list --json` 같은 읽기 전용 Vault 명령을 실행하고 결과를 Graph Home에 둘 수 있다. `AGENTS.md:19`의 "Search, indexing, watch, and recall never run these commands"를 "never run write paths"로 바꾼다.
3. L1 폴더 읽기: `docs/SPEC.md` §4 읽는 대상(`:100-104`)에 "Claude Code 자동 기억 폴더. 읽기만 한다"를 더한다.
4. 기계 생성물 금지: "vg는 기계가 만든 내용(요약, 목록, 점수)을 Vault에 쓰지 않는다. 에이전트나 사람이 판단한 내용만 경로 1, 2, 4로 들어간다"를 `AGENTS.md` Project Boundary에 더한다.
5. 수집 경로3: `AGENTS.md:15-17`의 "decides only when it runs, not which Vault or what content"를 "decides when it runs and which normalized file it passes. The Vault tool renders and writes; Vault Graph does not choose the Vault"로 바꾼다.
6. 원칙1 뒤 한 문장: "기억 관리에서 vg는 판단 재료를 결정적으로 만들고, 무엇을 기억·수정·폐기할지는 호출한 에이전트가 정한다."
7. `docs/SPEC.md:55` "Vault는 vault-graph 없이도 동작한다"를 "Vault는 저장소로서(ingest, update, query와 검증) vault-graph 없이도 동작한다. 기억 관리는 vault-graph가 맡는다"로 바꾼다. 대체 경로 제거(4.4.9) 뒤의 사실과 맞추기 위해서다.

리뷰7이 찾은 추가 세 곳. 승인된 문장1·5와 같은 내용을 `docs/SPEC.md` §0과 원칙5에 옮겨 적는 것이고 새 권한을 더하지 않는다. 사용자가 3차 gate 질문17에서 승인했다(9.4).

8. §0 규칙2 "Vault의 기억 페이지를 추가, 수정, 폐기한다"를 "Vault의 기억 페이지를 추가, 수정, 폐기, 되살린다. Claude Code 자동 기억 노트를 근거로 쓸 때는 Vault 도구로 그 사본을 남긴다"로 바꾼다(문장1, 4.4.13).
9. §0 규칙3 "vault-graph가 있으면 vault-graph가 실행 시점을 정한다"를 "vault-graph가 있으면 vault-graph가 실행 시점과 넘길 정규화 세션 파일을 정한다. 렌더링과 저장은 Vault 도구가 한다"로 바꾼다(문장5).
10. 원칙5 "vault-graph는 그 실행 시점만 정할 수 있다"를 "vault-graph는 그 실행 시점과 넘길 정규화 파일을 정한다. L1 사본도 Vault `import-source`가 쓴다"로 바꾼다(문장1·5).

#### 4.4.9 vault-builder 구성의 동결과 제거

| 코드 | 구성 | 이 spec 동안 | 이전 마지막 단계(S12) |
|---|---|---|---|
| 이주1 | `memory-cleanup` 스킬 (`vault-builder:.agents/skills/memory-cleanup/SKILL.md`) | 동결. 새 기능 없음. 범위 규칙만 맞춤 | 제거(요청S11) |
| 이주2 | `memory_scan.py` (`vault-builder:tools/wiki/lib/memory_scan.py:209-303`) | 유지. vg가 읽기 전용으로 실행 | 유지. 저장소의 반영 판정 명령이다 |
| 이주3 | `maps build` 프로젝트 요약 (`vault-builder:tools/wiki/lib/maps.py:255-305`) | 동결. 범위 규칙만 맞춤(요청S4) | 프로젝트 요약 생성 제거(요청S11). 일반 탐색 지도는 남김 |
| 이주4 | `recall.sh` | 동결. 범위 규칙만 맞추고, brief가 생기면 brief를 읽게 바꿈(요청S9) | 제거(요청S11) |
| 이주5 | `/project-memory` 스킬 | vg가 있으면 `summarize_project_memory`로 안내 | 제거(요청S11) |
| 이주6 | 훅 실행기 `vault_hooks.py` | 유지. `--normalized` 추가(요청S10) | `session-start`에서 `recall.sh` 대체를 빼고, vg가 없으면 빈 출력 |

- 제거 조건: 4.4.10의 지표1·2가 0이고, 사람이 S12 시작 때 제거를 한 번 더 확인한다. 제거 뒤 vg가 없는 사용자는 세션 시작 회상과 기억 정리를 받지 못한다. Vault의 ingest, update, query와 검증은 그대로 동작한다.

#### 4.4.10 기억 품질 측정

- 평가 세트: 이 사용자의 프로젝트 2~3개에서 질문 40개 안팎을 사람이 만든다. 축은 정보 추출, 여러 세션 추론, 시간 추론, 지식 갱신, 답하지 않기, 프로젝트 섞임, 대체된 결정 사용(조사 memory-management 3.9). 저장소 밖에 둔다.
- 실행: 질문마다 회상 텍스트와 `build_context_pack` 결과에 정답 페이지가 있는지 결정적으로 본다. 채점에 LLM을 쓰지 않는다. 도구는 `tests/benchmarks/measure_memory_recall.py`.
- 자동 지표: 지표1 대체·폐기 기억 주입 수(목표 0), 지표2 `sharable`가 false인 Vault의 다른 프로젝트 기억 주입 비율(목표 0), 지표3 주입 대비 열람 비율, 지표4 `inferred` 제안 승인율, 지표5 정리 대기 나이, 지표6 병합 후보 수. 지표3~6은 기록만 하고 판정에 쓰지 않는다.

#### 4.4.11 이전 순서 (단계마다 vg 회상과 `recall.sh` 회상이 모두 동작한다)

1. 단계1(S8): 경계 문장(4.4.8)과 §0 규칙5 예외, `page_in_project` + `sharable`, `remember`의 `project`·`tags`. vault-builder 요청S4. 회상 소스는 그대로다.
2. 단계2(S9): 구획L3(목록), 예산 분할, claim 행 대체 제외. 실패하면 구획L3만 빠진다.
3. 단계3(S10): 요청S8 `import-source` 뒤 L1 읽기, `memory-scan` 실행, 정리 대기 한 줄, 정리 꾸러미, MCP 도구와 prompt. `memory-cleanup`은 그대로 쓸 수 있다.
4. 단계4(S11): 평가 세트로 지표1~6을 잰다. 지표1·2가 0이 아니면 다음 단계로 가지 않는다.
5. 단계5(S12): `kind="project"`, brief 갱신 규칙과 안내, brief 첫 작성. 요청S9로 `recall.sh`가 brief를 읽는다. 사람 확인 뒤 요청S11로 대체 경로를 제거한다.

#### 4.4.12 모듈 배치

| 일 | 위치 |
|---|---|
| `page_in_project`, L3 목록, `current_claims`, `brief_staleness`, 정리 후보와 비교 재료 | M10 `context/memory/` (`project_memory.py` 확장, 새 파일 `memory_candidates.py`) |
| 구획L3, 정리 대기 줄, 예산 분할 | M08 `context/pack/recall.py`, 새 파일 `recall_backlog.py` |
| 코드 경로 소멸 신호(M11)와 후보 합치기 | `interface/composition/` (M10은 M11을 가져올 수 없다) |
| L1 폴더 읽기, `memory-scan` 실행·저장, `import-source` 실행 | `interface/composition/adapters/` |
| `ImportRequest`, `VaultImporter` 포트 | M18 `operation/memory/` |
| MCP 도구 `list_memory_candidates`, `mark_candidates_reviewed`(읽기 쪽 파일), `import_auto_memory`(쓰기 쪽 파일), prompt `curate_memory` | `interface/mcp/mcp_tools.py`, `mcp_memory_tools.py`, `mcp_prompts.py` |

| `build_supersede_claim_draft`, `build_restore_draft` | M18 `operation/memory/memory_drafts.py` |
| MCP 쓰기 도구 `supersede_claim`, `restore_memory` | `interface/mcp/mcp_memory_tools.py` |
| 검색 선택 `include_retired` | M05 `retrieval/search/evidence_result_assembly.py`, MCP `search_vault`, CLI `vg search` |

- MCP 도구는 14개에서 19개가 된다(`list_memory_candidates`, `mark_candidates_reviewed`, `import_auto_memory`, `supersede_claim`, `restore_memory`). 기존 도구의 이름과 입출력은 바꾸지 않고, `search_vault`와 쓰기 도구에는 선택 입력(`include_retired`, `candidate_key`)만 더한다(`docs/SPEC.md` §5 호환 규칙).

#### 4.4.13 폐기한 기억 찾기와 되살리기 (리뷰6, 질문16)

폐기는 파일을 지우지 않는다. `retire_memory`는 frontmatter `status`만 `retired`나 `deprecated`로 바꾼다(`memory_drafts.py:106-129@abc77e7`). 지금은 기본 검색이 폐기 페이지를 늘 빼고(`evidence_result_assembly.py:62-67@abc77e7`) 포함 옵션이 없다(`docs/SPEC.md` §0 "현재 구현과의 차이"). 그래서 에이전트가 폐기된 사실을 모르고 같은 내용을 다시 저장할 수 있고, 사용자가 되살릴 방법이 없다.

1. 찾기: `search_vault`와 `vg search`에 선택 입력 `include_retired`(기본 false)를 더한다. 참이면 폐기 페이지도 결과에 넣고 결과마다 `status`, `retired_reason`, `retired_at`, `superseded_by`를 붙인다. 회상과 L3 목록은 이 옵션을 쓰지 않는다(대체·폐기 제외 규칙 4.4.6 그대로).
2. 다시 저장 막기: 정리 꾸러미의 비교 재료(4.4.4)는 `include_retired`로 찾는다. 폐기 페이지는 "폐기됨: <이유>" 표시와 함께 나온다. 에이전트는 같은 내용이면 새로 쓰지 않고 `restore_memory`를 고른다.
3. 되살리기: 새 MCP 쓰기 도구 `restore_memory(path, reason, basis, cwd=None, vault=None, candidate_key=None)`. M18 `build_restore_draft`가 frontmatter만 바꾸는 `patch-page` draft를 만든다: `status: active`, `restored_at: <오늘>`, `restored_reason: <이유>`. `retired_reason`, `retired_at`, `superseded_by`는 이력으로 남긴다. `basis`에 따라 publish-draft 또는 `review propose`로 보낸다. 새 Vault 기능이 필요 없다.
4. 되살린 페이지는 다음 색인 뒤 회상과 기본 검색에 다시 나온다. `superseded_by`가 남아 있어도 `status: active`면 현재 기억으로 본다. 대체 판단은 `status` 하나로 한다.
5. 회상 구획C의 폐기 알림 줄은 지금처럼 남긴다. 알림 줄에 "되살리려면 `restore_memory`"를 더한다.

### 4.5 vault-builder 요청 목록

vault-graph는 아래를 구현하지 않는다.

| 코드 | 요청 | 필요 조건 |
|---|---|---|
| 요청S1 | 세션 md 형식을 바꾸면 frontmatter `schema` 버전을 올린다. 형식 문서에 v2 문법(4.2.5)을 적는다 | 항상 |
| 요청S4 | `vault-map.json` `vaults.<name>.sharable` 선택 필드와 설정 명령. 대체 경로(`maps.py`, `recall.sh`, `memory-cleanup`)가 같은 범위 규칙(4.4.2 규칙1~3, 연결 프로젝트 하나뿐인 Vault 포함)을 따른다. 필드가 없으면 false | S8 전 |
| 요청S7 | 설계 문서의 회상 주입 설명을 실제 동작에 맞춘다(조사 memory-layers 발견8) | 항상 |
| 요청S8 | `import-source <file> --into raw/imports/<kind>/ --json`: `raw/` 밖 파일을 정해진 이름으로 바이트 그대로 복사하고 source 페이지까지 만든다. 같은 sha256이면 아무것도 만들지 않는다 | S10 전 |
| 요청S9 | Vault 스키마에 페이지 종류 `project`와 경로 `wiki/projects/<project>.md` 추가, `recall.sh`가 brief를 읽기 | S12 전 |
| 요청S10 | `sessions capture --normalized <jsonl> [--rerender] --json`과 `vault-session/v2` 렌더러(4.2.5), 파트 번호와 커서 규칙(4.2.12: v1·v2 통합 번호, `last_exchange_id`, `continued=1`), 훅 실행기 `capture --direct --normalized` | 항상 |
| 요청S12 | (조건부, 위험D12) `retired_reason`, `superseded_by`가 남은 `status: active` 페이지를 lint가 받아들인다 | S10 E2E에서 거부될 때만 |
| 요청S11 | 대체 경로 제거: `memory-cleanup`, `maps build` 프로젝트 요약, `recall.sh`, `/project-memory`. 훅 실행기의 `recall.sh` 대체 제거 | S12에서 사람 확인 뒤 |

요청S2(원본 보관), 요청S3(v1에 턴 uuid), 요청S5(Codex 수집), 요청S6(Vault 증류 스킬)은 1차 답변으로 필요 없어졌다. 원본 보관은 vg export, 턴 uuid와 Codex는 정규화 JSONL과 요청S10, 증류는 vg 정리 꾸러미가 맡는다.

backlog:

- B-1 Codex adapter 구현(4.2.3 계약).
- B-2 로컬 언어 모델 단계: 세션 교환의 `derived` 조각(4.2.8 메모)과 정리 후보 거르기(4.4.1). 이 spec의 기준선(A-8, A-28) 측정 뒤 별도 spec으로 연다(9.3 질문12).

### 4.6 작업 묶음

선행 열의 묶음이 끝나야 시작한다. 각 묶음은 독립 커밋으로 끝내고 vault-graph `pytest` 전체를 통과해야 한다.

| 코드 | 내용 | 선행 | 관련 기준 |
|---|---|---|---|
| S0 | 원인3 단기: 페이지 조회, 계획 실패 격리, 재시도 간격, 경고 | 없음 | A-12, A-13 |
| S1 | 원인5: 토큰 예산 배치, 배치 반복자, 아레나 설정과 측정 | S0 | A-16 |
| S2 | 원인2와 원인3 근본: 임베딩 키 분리, `update_metadata`, 벡터 목록 표, 임베딩 캐시 | S1 | A-14, A-15, A-17 |
| S3 | 원인4 일부: clone 세대 준비, `(size, mtime_ns)` 사전 검사 | S0 | A-18 |
| S4 | M19 adapter(Claude Code), 정규화 JSONL, 가림, `vg session export`, Codex 계약 문서 | 없음 | A-1, A-2, A-11 |
| S5 | 조각기 선택, `session-exchange-v2`·`-v1`, 부모 단위 결과, 교환 메타 키워드, `embedding_input_for`, 같은 세션 묶음 재처리(4.2.13) | S2, S3 | A-4~A-7, A-9, A-36 |
| S6 | `vg hook capture`의 정규화와 `--normalized` 연결, `vg session export --recapture` | S4, 요청S10 | A-3, A-37 |
| S7 | 세션 평가 도구와 측정, `e5-small` 재측정 | S5, S6 | A-8 |
| S8 | 기억 단계1: 경계 문장(4.4.8 문장1~10)과 §0 규칙5 예외 반영, 범위 규칙(연결 프로젝트 수 포함), `sharable`과 미설정 안내, `remember`의 `project`·`tags` | 요청S4 | A-10, A-20, A-21 |
| S9 | 기억 단계2: L3 목록, 구획L3와 예산, claim 행 대체 제외 | S8 | A-25, A-26, A-27 |
| S10 | 기억 단계3: L1 읽기, `memory-scan`, 정리 꾸러미와 빠지는 규칙, MCP 도구 다섯(`supersede_claim`, `restore_memory` 포함), `include_retired`, prompt, 정리 대기 줄 | S9, S5, 요청S8 | A-22, A-23, A-24, A-38, A-39 |
| S11 | 기억 단계4: 기억 평가 도구와 측정 | S10 | A-28 |
| S12 | 기억 단계5: `kind="project"`, brief 갱신 규칙과 안내, brief 첫 작성, 대체 경로 제거 | S11, 요청S9, 요청S11, 사람 확인 | A-27, A-29, A-30, A-35 |
| S13 | 원인4 나머지: 바뀐 문서 단위 그래프 갱신 | S3 | A-19 |
| S14 | 문서: `AGENTS.md`, `docs/SPEC.md`, `docs/ARCHITECTURE.md`, 승인된 결정의 `docs/DECISIONS.md`, backlog B-1·B-2 | 각 묶음 | A-11, A-33 |

모듈과 가져오기 방향:

- 새 영역은 M19 `operation/sessions/` 하나다. 허용 가져오기는 M01, 어떤 영역도 M19를 가져오지 않는다. `tests/test_feature_import_direction.py`의 `_AREAS`와 `_ALLOWED`에 한 줄씩 더한다.
- 새 가져오기는 M03 → M02(`embedding_input_for`), M08 → M10(`page_in_project`, `current_claims`), M10 → M05(비슷한 페이지 찾기)다. 모두 `docs/ARCHITECTURE.md` §3.1 허용 방향이다.

## 5. Decisions

[사용자]는 사용자가 정한 것(brief, 9.1·9.3 답변), [가정]은 이 spec이 정하고 spec 승인으로 함께 확인받는 것이다. 남은 사용자 질문은 없다. 승인 때 따로 보여 줄 목표값은 5.5에 모았다. 리뷰 반영으로 정한 것은 5.6에 있다.

### 5.1 범위와 순서

1. 결정1 [사용자] 이슈 네 개를 한 spec에 두고 이슈B와 이슈C를 합친다. 이유: brief Targets 3과 사용자 지시.
2. 결정2 [사용자] 원인 5개를 모두 원인 쪽에서 고친다. 이유: brief Targets 2.
3. 결정3 [사용자] 원인3 단기 수정을 가장 먼저 한다(S0). 이유: brief. 지금 새 세션 기록이 벡터 검색에 들어가지 않는다.
4. 결정4 [사용자] 임베딩 모델 선정은 이 spec 밖이다. `e5-small`을 유지한다. 이유: 9.1 질문5.

### 5.2 이슈A

5. 결정5 [사용자] vg에 `vg session export`를 두고, 원본과 정규화 파일을 사용자가 정한 Vault 밖 경로에 쓴다. 이유: 9.1 질문1.
6. 결정6 [사용자] 에이전트별 adapter가 공통 형식으로 바꾼다. Claude Code adapter는 구현하고 Codex adapter는 계약만 쓰고 구현은 backlog B-1이다. 이유: 9.1 질문2.
7. 결정7 [가정] 공통 형식은 두 층이다. 기계용 정본은 정규화 JSONL `vg-session-jsonl/1`(Vault 밖), 검색·사람용은 그것에서 결정적으로 렌더링한 `vault-session/v2` md(Vault 안)다. 이유: JSONL은 손실이 적고 파싱이 쉽지만 Obsidian에서 읽을 수 없고 새 리더와 위치 형식이 필요하다. md는 지금 리더, FTS, 줄 위치를 그대로 쓴다(조사 session-format 결정7).
8. 결정8 [가정] v2 md는 Vault 도구가 렌더링하고 쓴다(`sessions capture --normalized`, 요청S10). vg는 언제, 어떤 정규화 파일을 넘길지만 정한다. 이유: vg는 Vault 파일을 직접 쓰지 않는다. md 형식의 주인이 Vault 도구에 남아 Vault만 쓰는 수집(vg가 없을 때)과 형식이 같다. 대안(vg가 렌더링하고 Vault가 검사만)은 Vault 쪽 검사 규칙이 렌더러를 다시 구현해야 한다.
9. 결정9 [가정] 사람 턴, 도구 대상, 성공 여부는 adapter가 원본 필드로 판단한다. md 텍스트 휴리스틱은 원본에 필드가 없는 옛 레코드와 v1 파일에만 쓴다. 이유: 발견A8. `turnOrigin`이 95%에 있다.
10. 결정10 [가정] 세션 조각은 교환 안의 고정 창(공백 토큰 96, 겹침 없음)이다. 처음 값 160은 같은 평가 세트에서 96이 MRR 0.43→0.45, 512 초과 12.0%→0.65%여서 바꿨다(§10.2). 창 경계는 모델 토큰이 아니라 공백 토큰으로 정한다. 이유: 질문과 답이 한 조각에 들어가고, 겹침이 없어 키워드 결과가 중복되지 않는다. 모델을 바꿔도 조각 id가 바뀌지 않는다(조사 session-embedding 위험4).
11. 결정11 [가정] v2 조각 id는 (세션 id, 교환 id, agent 범위, 창 번호)로 만든다. 파일 경로와 renderer 버전에 묶지 않는다. 이유: 렌더러가 조금 바뀌거나 파트 번호가 바뀌어도 id가 그대로다(조사 session-format 2.3).
12. 결정12 [가정] 교환 메타(파일, 명령, 도구, 오류, 결과)는 키워드 색인의 `frontmatter` 열에만 넣고 임베딩 입력과 `text`에는 넣지 않는다. 이유: "그 파일을 고친 세션" 같은 질의는 정확한 단어가 맞아야 하고, 경로 문자열은 임베딩 의미를 흐린다. FTS 열은 이미 있다(발견A12).
13. 결정13 [가정] 검색은 창으로 찾고 결과는 교환 하나로 묶어 교환 전체 줄 범위를 돌려준다. 이유: 같은 교환의 창이 결과를 채우지 않고, 근거를 열면 질문과 답 전체가 보인다. 일반 문서는 §10 단계A부터 문서 하나가 결과 하나다(§10.6).
14. 결정14 [가정] 조각기가 임베딩 입력 규칙도 소유한다(`DocumentChunker.embedding_input`). 이유: 벡터 색인이 조각기 종류로 분기하지 않게 규칙을 조각기 안에 숨긴다(AGENTS.md "Deep Modules").
15. 결정15 [가정] 서브에이전트 교환은 따로 조각 내고 검색 점수는 본 대화와 같게 둔다. 이유: 서브에이전트 턴이 70%라 섞으면 본 대화가 묻힌다. 점수를 낮출지는 A-8 측정(상위 10개 중 서브에이전트 비율) 뒤 다시 정한다.
16. 결정16 [가정] 원본이 없는 v1 파일은 `session-exchange-v1`로 계속 색인하고, 세션 파일에 `document-block-window-v2`를 더 쓰지 않는다. 이유: v1에만 남은 기록을 잃지 않으면서 도구 전용 조각을 없앤다.
16-1. 결정16-1 [사용자] 같은 세션의 v1과 v2가 겹치면 vg가 색인에서만 겹친 v1 교환을 뺀다. Vault 파일은 그대로 둔다. 이유: 9.3 질문11. 기존 근거 경로를 끊지 않고 중복만 없앤다.
16-2. 결정16-2 [사용자] 로컬 언어 모델 단계(`derived` 조각, 후보 거르기)는 다음 spec으로 미룬다(backlog B-2). 이 spec은 LLM 없는 기준선을 만들고 잰다. 이유: 9.3 질문12.
17. 결정17 [가정] 세션 질의 세트로 교환 단위 recall@5·@10·MRR을 재고, 측정1은 회귀 확인으로만 쓴다. 기대값 파일은 다시 만들지 않는다. 이유: 측정1은 파일 단위라 "맞는 파일, 틀린 교환"도 적중이다(발견A10).
18. 결정18 [가정] adapter 코드는 새 기능 영역 M19 `operation/sessions/`에 둔다. 허용 가져오기는 M01뿐이다. 이유: 세션 정규화는 색인(M02·M03)과 기억 쓰기(M18) 어디에도 속하지 않는 독립 정책이고, 에이전트가 늘어도 이 영역만 커진다.

### 5.3 이슈B+C

19. 결정19 [가정] 계획은 임베딩 키와 메타데이터 지문을 따로 비교하고, 메타데이터만 바뀌면 Chroma `update`로 고친다. 이유: 벡터 값은 `index_revision`, `source_role`, family와 무관하다(원인2).
20. 결정20 [가정] 벡터 목록 표는 세대 안, 임베딩 캐시는 세대 밖에 둔다. 이유: 표는 그 세대에 무엇이 있는지라 세대와 함께 되돌아가야 하고, 캐시는 벡터 값이라 세대를 다시 만들어도 살아 있어야 한다.
21. 결정21 [가정] 재시도 간격은 같은 오류에 대해 1, 2, 4, …, 최대 24시간이고 메타데이터·그래프 색인은 막지 않는다. 이유: 저절로 풀리지 않는 오류가 세션마다 650MB 쓰기를 반복하지 않게 한다.
22. 결정22 [가정] 배치는 토큰 예산(기본 16,384)으로 자르고 아레나 기본값은 측정으로 정한다. 이유: 패딩이 실제의 4.5배, 어텐션 비용이 8.2배다(조사 index-performance 6.2).
23. 결정23 [가정] 바뀐 문서 단위 그래프 갱신(가속6)은 마지막 코드 묶음(S13)이다. 가속7·10·11은 이 spec에서 하지 않는다. 이유: 가장 위험하거나 측정 전이다.

### 5.4 이슈D

24. 결정24 [사용자] L1, L2, L3 관리를 모두 vg로 옮긴다. Vault는 저장소다. 분담하지 않는다. 이유: 9.1 질문3.
25. 결정25 [사용자] `project`가 없는 페이지의 회상 범위는 Vault별 설정 `sharable`로 정한다. true면 연결된 모든 프로젝트의 세션 시작 기억 목록에 넣고, false면 넣지 않는다. 어느 쪽이든 검색에는 나온다. 설정이 없으면 false로 다루고 `vg status`와 세션 시작에 안내 한 줄을 낸다. 이유: 9.1 질문4, 9.3 질문15(이름도 사용자가 정함).
26. 결정26 [사용자] vg가 L1 폴더를 읽는다. 이유: 9.1 질문6.
27. 결정27 [가정] "모두 이관"을 "관리 결정과 흐름은 vg, 판단은 세션 안 에이전트, 저장과 검증은 Vault 도구"로 구현한다. 이유: vg는 LLM을 부르지 않고 `raw/`에 쓰지 않는다(발견D7). 이 둘을 바꾸지 않고도 판단 규칙이 vault-builder에 남지 않는다.
28. 결정28 [가정] 정리 판단 단위는 "후보 하나 + 비슷한 기존 페이지 5개"이고, 에이전트는 추가·수정·폐기(대체)·건너뜀 중 하나를 고른다. 이유: 쓰기 전 기존 기억과 비교하는 방식이 중복과 모순을 가장 직접 줄인다(조사 memory-management 사례4).
29. 결정29 [가정] `basis: stated`는 근거 원문에 사용자 자신의 말이 있고 그 문장을 인용할 때만이다. 경계 사례는 `inferred`이고, 한 번의 정리에서 `inferred`는 10개까지다. 이유: 품질 우선. 틀린 기억이 검토 없이 발행되지 않게 하면서 검토 부담에 상한을 둔다.
30. 결정30 [가정] 대체된 claim 행을 회상과 L3 목록에서 뺀다. 이유: "대체된 사실을 쓰지 않기"가 기억 품질에서 가장 약한 지점이다(발견D8).
31. 결정31 [가정] 폐기는 점수로 후보만 올리고 자동으로 하지 않는다. 이유: 폐기는 되돌리기 어렵고 판단이 필요하다.
32. 결정32 [사용자] 회상 구획B 순위에 사용 기록을 쓰지 않는다. 조사의 "마지막 열린 때 기준 최근성" 제안을 따르지 않는다. 사용 기록과 건너뜀 기록은 Graph Home에 두고 정리 후보를 고르고 정렬하고 보여 주는 데만 쓰며, `docs/SPEC.md` §0 규칙5에 그 예외를 적는다(문장은 4.4.4). 이유: 9.3 질문14. Graph Home을 지워도 회상은 같고, 정리에서는 이미 본 후보를 한 번 더 보는 것만 달라진다.
33. 결정33 [가정] 회상 1,500토큰을 구획A 400, 구획L3 500, 구획C·D 180, 나머지 구획B로 나눈다. 이유: 프로젝트 요약이 회상 앞에 고정 크기로 들어가고, 기존 고정 기억 예산은 그대로다.
34. 결정34 [가정] 정리는 사용자가 시작한다(`curate_memory`). 훅 안에서 하지 않는다. 이유: 훅에는 LLM이 없고 시간 제한이 있다. 세션 시작의 정리 대기 한 줄이 밀린 양을 알린다.
35. 결정35 [가정] vault-builder의 판단 구성(`memory-cleanup`, `maps build` 프로젝트 요약, `recall.sh`, `/project-memory`)은 이 spec 동안 동결하고 이전 마지막 단계에서 사람 확인 뒤 제거한다. 이유: 9.1 질문3 "분담은 리스크". 이전 중에는 단계마다 두 회상 경로가 모두 동작해야 한다.
36. 결정36 [사용자] 로컬 언어 모델은 이 spec의 기억 관리에 넣지 않는다(결정16-2와 같은 답). 이유: 9.3 질문12. 판단 품질은 세션 안 Claude가 작은 로컬 모델보다 높고(추정), 로컬 모델이 줄일 수 있는 것은 후보 거르기의 토큰 비용이다.
37. 결정37 [사용자] 경계 문장 일곱 곳(4.4.8)을 바꾼다. 쓰기 경로4 `import-source`, 읽기 전용 Vault 명령, L1 폴더 읽기, 기계 생성물을 Vault에 쓰지 않음, 수집 경로 문장, 원칙1 보충, "Vault는 저장소로서 vg 없이 동작". 이유: 9.3 질문9.
38. 결정38 [사용자에게 위임받아 정함] L3는 혼합이다. 목록은 vg가 회상·조회 때 계산하고 저장하지 않는다. brief는 Vault 페이지이고 에이전트가 기존 쓰기 경로로 쓴다. 갱신 시점은 vg가 정한다(brief 뒤 새 결정 수가 기준값 이상이면 세션 시작 안내와 정리 후보). 이유: 9.3 질문10. 다시 계산할 수 있는 것은 Vault에 쓰지 않고, 판단한 것만 Vault에 남긴다.
39. 결정39 [사용자] brief는 `wiki/projects/<project>.md`, 새 종류 `project`다(요청S9). MCP `remember`의 `kind`에 `project`를 더한다. 이유: 9.3 질문13.

### 5.5 승인 때 확인할 [가정] 목표값

사용자가 정하지 않았고 이 spec이 정한 수치다. 측정이나 운영에서 맞지 않으면 그 묶음에서 다시 묻는다.

| 코드 | 값 | 쓰는 곳 | 근거와 확인 |
|---|---|---|---|
| 목표1 | 세션 조각 5,000개 이하(지금 28,330개) | A-8 | 본 대화 교환 약 2,500개 집계에서 추정. 위험A1 |
| 목표2 | `e5-small` 전체 재색인 최대 RSS 6GB 이하(지금 21.2GB) | A-16 | 토큰 예산 16,384 배치에서 추정. 위험B6 |
| 목표3 | 한 정리에서 `inferred` 제안 10개까지 | 4.4.4, 결정29, A-23 | 검토 부담 상한. 지표4로 확인 |
| 목표4 | brief 갱신 기준값: brief 뒤 새 결정 5개 | 4.4.7, A-35 | 위험D9 |
| 목표5 | 사용 기록 폐기 후보 기간 90일 | 4.4.4 | 조사 memory-management 3.7 예시값. 위험D10 |
| 목표6 | 창 크기 공백 토큰 96, 512 모델 토큰 초과 창 1% 이하 | 결정10, A-8 | 위험A4 |
| 목표7 | 증분 run 디스크 증가 50MB 이하(지금 약 650MB) | A-18 | clone 세대 준비 |
| 목표8 | 세션 교환 정리 후보 나이 상한 180일 | 4.4.4, 결정44 | 지표5(정리 대기 나이)로 확인. 위험D11 |

### 5.6 리뷰 반영 (2026-11-06)

사용자 지시: "리뷰에서 바라본 현재 vault, vault-builder, vault-graph의 역할과 의도를 고려해서 개선". 아래는 이 지시로 spec이 정한 것이고 최종 승인으로 확인받는다. 기준은 4.0이다.

40. 결정40 [가정] `project`가 없는 페이지는, 그 Vault를 연결한 프로젝트가 하나뿐이면 그 프로젝트 것이다. 둘 이상이면 `sharable`을 본다(4.4.2, 리뷰1). 이유: 연결 정보가 이미 `vault-map.json`에 있어 Vault에 쓰지 않고 풀린다. 결정25("설정이 없으면 false")는 여러 프로젝트가 함께 쓰는 Vault에 그대로 적용된다.
41. 결정41 [가정] 세션 파트 번호와 커서는 Vault 도구가 v1·v2를 통틀어 한 줄로 관리한다. 기본은 이어 쓰기이고, 다시 쓰기(`--rerender`)는 사람이 실행하는 이전 명령에서만 쓴다(4.2.12, 리뷰3). 이유: 지금 커서의 주인이 Vault 도구다. 이어 쓰기는 겹침을 만들지 않는다.
42. 결정42 [가정] 증분 색인은 같은 세션 묶음 키(`agent`, `session_id`)와 같은 provenance family의 파일을 함께 다시 계획한다(4.2.13, 리뷰2). 이유: 여러 파일을 함께 보는 규칙이 증분에서도 full run과 같은 결과를 내야 결정적 검색이 지켜진다.
43. 결정43 [가정] claim 대체는 새 MCP 쓰기 도구 `supersede_claim`이 Vault의 기존 `patch-page` `supersede-claim` 편집으로 한다(4.4.4, 리뷰4). 이유: Vault에 이미 있는 검증된 형식이고, 본문 전체를 다시 쓰지 않아 claim 이력이 빠지지 않는다.
44. 결정44 [가정] 쓰기 도구가 받은 `candidate_key`로 처리한 후보를 Graph Home에 자동 기록하고, 세션 근거는 교환 위치로 판단하며, 세션 교환 후보는 180일 나이 상한을 둔다(4.4.4, 리뷰5). 이유: 검토 대기 중인 제안이 다시 올라오지 않고, 파일 단위 근거로 목록이 한꺼번에 사라지지 않는다.
45. 결정45 [사용자, 질문16 권장안을 최종 승인으로 확인] 폐기 기억은 `include_retired`로 찾고 `restore_memory`로 되살린다. 정리 비교 재료는 폐기 페이지를 포함한다(4.4.13, 리뷰6). 이유: 폐기는 파일을 지우지 않으므로 되돌릴 수 있어야 하고, 에이전트가 폐기된 사실을 모르고 다시 저장하지 않게 한다. 되살리기도 기존 `patch-page`로 한다.
46. 결정46 [사용자, 질문17] `docs/SPEC.md` §0 규칙2·3과 원칙5를 승인된 문장1·5에 맞춰 고친다(4.4.8 문장8~10, 리뷰7). 이유: 같은 문서 안에서 경계 규칙이 서로 다르면 다음 구현자가 좁은 쪽을 따른다.

## 6. Failure and boundary behavior

| 상황 | 소유 | 동작 |
|---|---|---|
| 원본 jsonl 줄 하나가 JSON이 아님 | vg M19 | 그 줄을 건너뛰고 정규화 결과의 경고 수에 센다. 세션 전체를 버리지 않는다 |
| 원본 레코드에 `turnOrigin`·`origin.kind`가 없음 | vg M19 | 본문이 `<`로 시작하지 않는지로 사람 턴을 판단한다 |
| adapter가 모르는 레코드 `type` | vg M19 | 무시한다. export 결과에 종류별 무시 수를 적는다 |
| `vg session export --out`이 Vault 안 | vg CLI | 아무것도 쓰지 않고 오류로 끝난다 |
| `--out`이 git 작업 트리나 동기화 폴더 안 | vg CLI | 표준 오류에 경고 한 줄을 내고 쓴다 |
| `--agent codex`(B-1 전) | vg CLI | "Codex adapter 없음" 오류로 끝난다 |
| 수집 훅에서 정규화 실패 | vg `vg hook capture` | 정규화 없이 지금의 `capture --direct`로 원본 경로를 넘긴다(v1 파일이 생김). 종료 코드는 지금 규칙(0 또는 3)을 따른다 |
| 실행기나 Vault 도구가 `--normalized`를 모름(종료 코드 2) | vg `vg hook capture` | 같은 훅에서 `capture --direct`로 다시 실행한다 |
| export 설정 경로가 없어짐(외장 디스크 분리 등) | vg `vg hook capture` | export만 건너뛰고 경고 한 줄. 수집은 OS 임시 폴더의 정규화 파일로 계속한다 |
| v2 숨은 메타 줄이 없거나 깨짐 | vg M02 | 그 교환을 v1 규칙으로 조각 내고(`parent_key`는 제목 기반) 경고 한 줄 |
| 같은 교환 id가 두 파일에 있음 | vg M02 | 경로 사전순 앞 파일만 색인하고 경고 한 줄 |
| 모르는 `vault-session/*` 버전 | vg M02 | 일반 조각기로 조각 내고 경고 한 줄 |
| 턴 하나가 공백 토큰 160개를 넘음 | vg M02 | 단어 경계로 여러 창에 나눈다 |
| 임베딩 입력이 모델 토큰 512를 넘음 | vg M03 | 모델이 512에서 자른다. 넘은 창 수를 경고에 적는다 |
| 같은 세션의 v1과 v2가 함께 있음 | vg M02 | v2 교환 시각 범위와 겹치는 v1 교환을 색인에서만 뺀다. Vault 파일은 그대로다 |
| v2 교환에 `started_at`·`ended_at`이 없음 | vg M02 | 그 세션의 v1 교환을 하나도 빼지 않고 경고 한 줄. 중복이 생길 수 있으나 기록을 잃지 않는 쪽을 고른다 |
| Chroma 목록 조회가 페이지 조회로도 실패 | vg M03 | 벡터 결과 `failed=True`. 메타데이터·그래프는 발행된다. 재시도 간격이 시작된다 |
| 같은 오류로 재시도 간격 안 | vg 세션 시작 백그라운드 색인 | 그 Vault의 벡터 색인만 건너뛴다. 회상 출력 뒤 경고 한 줄 |
| 사람이 `vg index`를 직접 실행 | vg CLI | 재시도 간격을 보지 않는다. 성공하면 실패 기록을 지운다 |
| 벡터 목록 표가 없거나 행 수가 Chroma와 다름 | vg M03 | Chroma를 페이지 단위로 읽어 표를 다시 만든다. 경고 한 줄 |
| Chroma `update` 실패 | vg M03 | 벡터 결과 `failed=True`. 다음 run에서 다시 메타데이터 갱신 대상이 된다 |
| 배치 저장 중 프로세스가 죽음 | vg M03·M04 | 스테이징 세대는 발행되지 않는다. 다음 run은 임베딩 캐시에서 이어 간다 |
| 임베딩 캐시 파일이 깨짐 | vg M03 | 캐시 없이 임베딩하고 경고 한 줄. 다음 성공 run이 새로 만든다 |
| `clonefile` 실패 | vg M04 | `copytree`로 돌아가고 경고 한 줄 |
| 파일 `mtime`은 그대로인데 내용이 바뀜 | vg M03 | 증분 run이 놓친다. `vg index --full`이 바로잡는다(위험B4) |
| 그래프 증분 결과가 full run과 다름 | vg M03 | S13을 합치지 않는다 |
| `sharable`이 없음 | vg M17 `vault_map.py`, M08 | false로 다룬다. `vg status`와 세션 시작 표준 오류에 Vault마다 설정 안내 한 줄. 검색 결과는 바뀌지 않는다 |
| `sharable`이 불리언이 아님 | vg M17 `vault_map.py` | 그 필드만 무시하고 false로 다룬다. 경고 한 줄, `vg status`에 보인다 |
| `cwd`가 프로젝트로 풀리지 않음(`remember`, `list_memory_candidates`) | vg | `remember`는 `project`를 넣지 않는다. `list_memory_candidates`는 빈 꾸러미와 "프로젝트를 찾지 못함" 메시지 |
| L1 폴더가 없거나 읽을 수 없음 | vg 어댑터 | L1 후보 0개, 정리 대기 줄에서 L1 부분을 빼고 경고 한 줄 |
| `memory-scan --json` 실행 실패나 계약 미달 Vault | vg 어댑터 | vg sha256 판정만 쓰고 경고 한 줄 |
| vg와 `memory-scan`의 반영 판정이 다름 | vg | `memory-scan` 결과를 쓰고 경고 한 줄 |
| `import-source`를 모르는 Vault(요청S8 전) | vg M18 | `import_auto_memory`가 `error`와 "Vault 도구를 업데이트하라"를 돌려준다. 다른 후보 처리는 계속된다 |
| 같은 L1 노트를 두 번 `import_auto_memory` | Vault 도구 | 같은 sha256이면 새 파일 없이 기존 경로를 돌려준다 |
| 에이전트가 한 정리에서 `inferred`를 10개 넘게 보냄 | vg M18 | 11번째부터 `rejected`, "이번 정리의 제안 상한" 메시지. "한 정리"는 같은 MCP 서버 프로세스에서 마지막 `list_memory_candidates` 호출부터 다음 호출 전까지다 |
| 건너뜀 기록 파일이 없거나 깨짐 | vg | 모든 후보가 다시 올라온다. 경고 한 줄 |
| claim 표 형식을 읽지 못함 | vg M10 | 그 페이지는 claim 행 제외 없이 페이지 단위로만 다룬다. 경고 한 줄 |
| 구획L3를 만들지 못함(brief 없음, 목록 0개, 오류) | vg M08 | 구획L3를 빼고 그 예산을 구획B로 넘긴다 |
| brief 페이지가 두 Vault에 있음 | vg M10 | 프로젝트 기본 저장 Vault의 것만 쓴다. 경고 한 줄 |
| `remember(kind="project")`인데 `cwd` 프로젝트가 정해지지 않음 | vg M18 | `rejected`, "brief는 프로젝트 폴더에서 써야 한다" |
| `remember(kind="project")`인데 brief가 이미 있음 | vg M18 | 지금 규칙대로 `rejected`와 "`update_memory`를 쓰라" |
| Vault가 종류 `project`를 모름(요청S9 전) | Vault 도구가 거부, vg가 전달 | `rejected`와 Vault 메시지. 구획L3는 목록만 낸다. brief 갱신 안내는 계속 나온다 |
| brief 갱신 기준에 걸렸지만 에이전트가 건너뜀 | vg | 건너뜀 기록에 후보 키를 남긴다. 키가 기준에 든 결정 목록의 해시라 새 결정이 하나라도 생기면 다시 올라온다. 세션 시작 안내 줄은 기준에 걸려 있는 동안 계속 나온다 |
| 사용 기록이 없거나 Graph Home을 막 다시 만듦 | vg M10 | 폐기 후보 (2)는 0개다. (1) 코드 경로 소멸 후보만 나온다 |
| 대체 경로 제거 뒤 vg가 없는 사용자 | vault-builder 훅 실행기 | 세션 시작 회상이 빈 출력이다. 수집은 Vault 도구만으로 계속된다 |
| 같은 세션 묶음의 다른 파일을 읽지 못함 | vg M02·M03 | 그 묶음의 겹침 제외를 하지 않고(모든 v1 교환 유지) 경고 한 줄. 기록을 잃지 않는 쪽을 고른다 |
| v1 다음 첫 v2 파트에서 `last_turn_uuid`가 정규화 파일에 없음 | Vault 도구 | 지금 v1 규칙처럼 `last_turn_at`보다 늦은 턴만 쓰고 경고 한 줄(`session_capture.py:117-133`) |
| `supersede_claim`의 `claim`이 정확히 한 행과 맞지 않음, claim 표 없음 | Vault 도구가 거부, vg가 전달 | `rejected`와 Vault 메시지. 후보는 처리 기록이 없어 남는다 |
| `restore_memory` 대상이 폐기 상태가 아님 | vg M18 | Vault를 부르지 않고 `rejected`, "폐기된 페이지가 아니다" |
| 쓰기 결과가 `rejected`·`error`인데 `candidate_key`가 있음 | vg | 처리 기록을 남기지 않는다. 후보가 다음 정리에 다시 나온다 |
| Graph Home을 지움 | vg | 기억, 세션 파일, export 폴더는 그대로다. 조각 id와 키워드 결과는 다시 색인하면 같다. 건너뜀 기록과 임베딩 캐시는 비어 첫 정리와 첫 색인이 길어진다 |

## 7. What could be wrong

이 절은 확인하지 못한 사실이다. 각 줄의 확인 방법을 해당 묶음 시작 때 먼저 한다.

| 코드 | 확인하지 못한 사실 | 틀리면 | 확인 방법 |
|---|---|---|---|
| 위험A1 | 세션 조각이 28,330개에서 5,000개 이하로 준다. 본 대화 교환 약 2,500개는 셌지만 서브에이전트 교환과 창 수는 세지 않았다. | 원인1의 가속 폭이 작다. A-8 목표를 다시 잡는다 | S5 시작 때 실제 세션 파일로 새 조각기를 dry-run해 조각 수를 센다 |
| 위험A2 | Claude Code 원본 필드(`turnOrigin`, `tool_use.input` 키, `is_error`)는 공개 계약이 아니다. | 버전이 바뀌면 adapter가 사람 턴과 도구 대상을 잘못 고른다 | adapter 버전과 원본 Claude Code 버전별 고정 파일을 둔다(A-1). 모르는 레코드 종류 수를 export 결과에 적는다 |
| 위험A3 | 압축 요약(`isCompactSummary`)과 스킬 본문(`isMeta`)이 v1 파일에서 사람 턴과 구분된다. | v1 파일의 교환이 잘못 나뉜다. v2에는 영향 없음(adapter가 원본 필드로 판단) | S5에서 압축이 있었던 v1 파트 파일을 열어 본다 |
| 위험A4 | 160 공백 토큰 창의 임베딩 입력이 대부분 모델 토큰 512 안에 든다. | 창 뒷부분이 임베딩에서 잘린다. 키워드 검색에는 남는다 | A-8에서 512 초과 창 비율을 잰다. 1%를 넘으면 창 크기를 다시 묻는다 |
| 위험A5 | 키워드 색인이 `frontmatter` 열을 문서 frontmatter에서 채우는 방식이 조각마다 다른 값(`keyword_metadata`)을 받을 수 있다. | 교환 메타를 넣으려면 FTS 열 추가나 키워드 행 구조 변경이 필요하다 | S5 시작 때 `sqlite_keyword_index.py`의 행 쓰기 코드를 읽는다 |
| 위험A6 | 근거 id와 조각 id를 Graph Home 밖(Vault 페이지)에 저장한 곳이 없다. | 전환 뒤 그 기록이 가리키는 세션 근거가 열리지 않는다 | S5에서 연결 Vault 전체를 조각 id 형식으로 검색한다 |
| 위험A7 | Codex 세션을 수집할 훅 연결 방법이 있다. `item_completed`가 모든 Codex 버전에 있다. | B-1에서 Codex는 수동 export만 되고 자동 수집이 안 된다 | B-1 시작 때 Codex 문서와 버전별 원본을 확인한다 |
| 위험A8 | vg 가림(`vg-redact/1`)과 Vault 가림 규칙이 같은 값을 가린다. 원본 export(`--raw`)는 가리지 않는다. | 한쪽만 가린 비밀값이 정규화 파일이나 Vault에 남는다. 원본 사본이 동기화 폴더에 있으면 밖으로 나간다 | S4에서 두 규칙을 같은 표 테스트로 묶는다. A-2의 경고와 권한 검사 |
| 위험A9 | Vault 도구가 v2를 결정적으로 렌더링한다(같은 입력, 같은 바이트). | 같은 세션을 다시 수집할 때 새 파트가 생기거나 `body_sha256`이 어긋난다 | 요청S10 수용 기준에 넣고, A-3 E2E에서 두 번 수집해 비교한다 |
| 위험A10 | v1과 v2 교환의 겹침을 timestamp 범위로 정확히 판단할 수 있다. v1에는 첫·끝 uuid만 있다. | 겹친 교환이 두 번 나오거나 v1에만 있던 교환이 빠진다 | S5에서 실제 세션 하나를 v1·v2로 모두 두고 비교한다(A-9) |
| 위험B1 | `too many SQL variables`의 원인이 limit 없는 `get`이다. 숫자 일치만 확인했다. | 페이지 조회로도 실패한다 | S0에서 33,000개 이상 임시 컬렉션으로 비교한다(A-12) |
| 위험B2 | Chroma 1.5.9의 `collection.update(ids, metadatas)`가 임베딩을 건드리지 않는다. | 메타데이터 갱신이 벡터를 지운다 | S2 첫 테스트로 update 전후 벡터를 비교한다 |
| 위험B3 | `clonefile(2)`를 Python에서 폴더에 쓸 수 있고, clone 파일 쓰기가 원본 세대에 영향을 주지 않는다. | 활성 세대가 바뀐다 | S3에서 원본 sha256을 비교한다(A-18) |
| 위험B4 | `(size, mtime_ns)`가 놓치는 경우는 mtime을 보존하는 복사뿐이다. | 증분 색인이 바뀐 파일을 건너뛴다 | S3에서 git checkout과 `sessions capture` 뒤 mtime 변화를 본다 |
| 위험B5 | fastembed 0.8.0이 `enable_cpu_mem_arena`를 받고, 꺼도 지연이 20% 안에서 늘어난다. | 아레나를 켠 채 두고 토큰 예산 배치만으로 메모리를 묶는다 | S1 측정 |
| 위험B6 | 토큰 예산 16,384에서 최대 RSS가 6GB 안에 든다. | 예산을 줄이거나 목표를 다시 정한다 | S1 측정 |
| 위험B7 | 바뀐 문서 단위 그래프 갱신이 full run과 같다. | 그래프 조회가 틀린 관계를 돌려준다 | A-19 비교 테스트 |
| 위험D1 | L1 폴더 위치를 Claude Code 설정(`CLAUDE_CONFIG_DIR`, `autoMemoryDirectory`, 프로젝트 폴더 이름 규칙)에서 정확히 찾는다. | L1 후보가 0개로 나와 밀린 정리를 모른다 | S11에서 실제 폴더와 비교하고, `memory-scan` 결과와 같은지 본다(A-24) |
| 위험D2 | 세션 근거를 인용하는 wiki 페이지가 `raw/sessions/<파일>` 경로를 본문이나 frontmatter에 그대로 적는다. | 근거로 쓰인 교환도 후보로 다시 올라온다 | S11에서 `vault-builder:tools/wiki/lib/ingest.py:44`의 근거 표기를 읽는다 |
| 위험D3 | Vault claim 표의 상태 열 형식이 Vault마다 같고 vg가 읽을 수 있다. | 대체된 claim 행이 회상에 남는다(지표1이 0이 아님) | S10에서 `OPERATING-SCHEMA.md:192-200`과 실제 페이지로 파서 테스트를 만든다 |
| 위험D4 | `sharable` 미설정을 false로 다루면 지금 personal Vault 회상 18개 중 대부분이 세션 시작 목록에서 빠진다(검색에는 남는다). 프로젝트 Vault는 결정40으로 영향이 없다. 안내 한 줄을 사용자가 놓칠 수 있다. | 회상이 갑자기 짧아졌다고 느낀다 | S8 전후 회상 출력과 안내 줄을 비교해 PR 설명에 적는다 |
| 위험D5 | 요청S9가 Vault 스키마에 종류 `project`와 `wiki/projects/` 경로를 더한다. | publish-draft가 brief를 거부해 brief가 생기지 않는다. 구획L3는 목록만 낸다 | S12 시작 전 요청S9 반영을 E2E로 확인한다(A-27) |
| 위험D6 | `stated` 판정(사용자 말 인용)이 넓게 쓰인다. | 틀린 기억이 검토 없이 발행된다 | 지표4와 S12에서 사람 표본 검토 20건 |
| 위험D7 | 에이전트가 `curate_memory` 순서를 지킨다(비교 재료를 읽고 고른다). | 중복 페이지가 늘어난다 | S11 지표6(병합 후보 수)을 정리 전후로 비교한다 |
| 위험D8 | 대체 경로 제거 뒤 vg가 없는 사용자가 없다. | 그 사용자는 회상과 정리를 잃는다 | S12 시작 때 사람이 확인한다(4.4.9) |
| 위험D9 | brief 갱신 기준값 5가 적당하다. | 너무 작으면 세션마다 갱신 안내가 나오고, 너무 크면 brief가 오래된 채 남는다 | S11 평가 동안 안내가 나온 세션 비율과 brief 갱신 사이 결정 수를 기록하고 PR 설명에 적는다 |
| 위험D11 | wiki 페이지가 세션 근거를 교환 위치(줄 범위나 교환 id 앞 8자)까지 적는다. 지금 근거 표기는 파일 경로 단위일 수 있다. | 교환 후보가 근거로 쓰인 뒤에도 남는다. 처리 기록(결정44)이 있으면 빠지지만, vg 밖에서 쓴 페이지의 근거는 못 본다 | S10 시작 때 Vault 근거 표기 규칙(`vault-builder:docs/agent/OPERATING-SCHEMA.md`)과 실제 페이지를 읽는다. 위험D2와 함께 확인 |
| 위험D12 | Vault `patch-page`의 frontmatter 덮어쓰기로 `status: active`를 넣으면 lint가 `retired_reason`, `superseded_by`가 남은 active 페이지를 받아들인다. | `restore_memory`가 거부된다 | S10 첫 E2E로 확인한다. 거부되면 요청S12(lint 규칙 완화)를 vault-builder에 낸다 |
| 위험D13 | 프로젝트 하나에만 연결된 Vault의 `project` 없는 페이지가 모두 그 프로젝트 것이다. | 다른 프로젝트 이야기를 담은 페이지가 그 프로젝트 회상에 섞인다 | S8에서 vault-graph Vault 17쪽을 사람이 훑어 다른 프로젝트 페이지 수를 PR 설명에 적는다 |
| 위험D10 | 사용 기록 기반 폐기 후보(90일 주입만, 열람 0)가 의미 있는 후보를 낸다. 열람 기록은 MCP 리소스 읽기만 센다. | 쓰이는 기억이 폐기 후보로 자주 오른다. 자동 폐기는 없으므로 에이전트 판단 부담만 는다 | S11에서 폐기 후보 중 에이전트가 실제로 폐기한 비율을 기록한다 |

## 8. Acceptance criteria

각 기준의 "확인" 줄이 검증 방법이다. "측정"은 실제 Graph Home과 Vault로 실행하고, 결과 합계만 `docs/design/reports/`에 커밋한다(질의 원문과 세션 내용은 저장소 밖, `docs/SPEC.md` §6-3과 같은 방식). "E2E"는 환경 변수 `VAULT_BUILDER_ROOT`의 vault-builder로 임시 Vault를 만들어 실제 Vault 도구를 하위 프로세스로 부르는 테스트다.

### 8.1 이슈A 세션 문서 형식과 임베딩 방식

- A-1 Claude Code adapter와 정규화 JSONL
  - 고정 원본 세 개(`turnOrigin` 있음, 없음, 서브에이전트·압축 포함)를 정규화한 결과가 기대 파일과 바이트 단위로 같다. 두 번 돌려도 같다.
  - `turnOrigin: task_notification`, `isMeta`, `isCompactSummary` 레코드가 사람 턴이 아니다.
  - `Edit`, `Bash`, `WebFetch` 행동의 `target`이 각각 파일 경로, 명령 앞부분, url이고, `is_error: true` 행동은 `ok: false`와 `error_head`를 가진다.
  - 고정 비밀값(API 키 형식, 토큰 형식)이 `text`, `commands`, `error_head` 어디에도 남지 않는다. Vault 가림 규칙과 같은 표 테스트가 통과한다.
  - 줄마다 `schema: vg-session-jsonl/1`과 `kind`가 있다.
  - 확인: M19 단위 테스트.
- A-2 `vg session export`
  - `--out`이 Vault 안이면 파일 0개, 0이 아닌 종료 코드다.
  - 원본 사본이 원본과 sha256이 같다. 폴더 권한 0700, 파일 권한 0600이다.
  - git 작업 트리 안 경로면 경고 한 줄이 있다.
  - 같은 세션을 두 번 export하면 두 번째는 파일을 다시 쓰지 않는다(mtime 그대로).
  - `--agent codex`는 "adapter 없음" 오류다.
  - 확인: 임시 폴더 통합 테스트.
- A-3 수집 흐름(E2E, 요청S10 뒤)
  - SessionEnd 훅 JSON으로 `vault_hooks.py capture`를 실행하면 project Vault `raw/sessions/` 아래에 `schema: vault-session/v2` 파일이 생긴다.
  - 같은 세션을 새 턴 없이 다시 보내면 새 파일이 생기지 않는다. 같은 정규화 입력으로 두 번 렌더링한 바이트가 같다.
  - 열린 마지막 교환은 파일에 없다.
  - `--normalized`를 모르는 Vault 도구에서는 v1 파일이 생기고 훅 종료 코드가 0이다.
  - export 설정이 있으면 같은 실행에서 export 폴더에도 정규화 파일이 생긴다.
  - 확인: E2E 테스트와 실행 로그.
- A-4 조각기 선택과 창 규칙
  - `schema` 없는 파일과 일반 문서의 조각 id, `text`, `source_locators`, 임베딩 입력이 `abc77e7`과 바이트 단위로 같다.
  - v2 고정 파일에서 창 본문에 숨은 메타 줄이 없고, 모든 창의 공백 토큰 수가 160 이하이며, 두 창이 같은 줄을 함께 갖지 않는다.
  - v1 고정 파일(도구 전용 턴, 태그 감싼 user 턴, 서브에이전트, 이어진 교환, 160 초과 턴, 사람 턴 없음)이 기대 창 목록과 같다.
  - 모르는 `vault-session/v9`는 일반 조각기와 경고 한 줄이다.
  - 확인: 고정 파일 표 테스트. 고정 v1 파일 하나는 실제 `sessions capture` 결과에서 내용을 바꿔 만든다.
- A-5 조각 id 안정과 결정성
  - 같은 Vault를 두 번 색인하면 조각 id, 창 본문, 위치, 키워드 결과 순서가 같다.
  - v2 파일의 renderer 버전 표기와 파트 번호만 바꾼 사본을 색인하면 조각 id가 같다.
  - 새 파트 파일을 더해도 기존 파일의 조각 id가 바뀌지 않는다.
  - 확인: 단위 테스트 셋.
- A-6 교환 메타 키워드 검색
  - 고정 Vault에서 v2 교환이 고친 파일 경로로 `vg search`하면 그 교환이 상위 5개에 있다.
  - 그 파일 경로 문자열이 창의 `text`와 임베딩 입력에 없다.
  - `vg search "Bash"` 결과에 도구 이름만 있는 조각이 없다.
  - 확인: 통합 테스트.
- A-7 부모 단위 결과
  - 한 교환의 창 셋이 모두 맞는 질의에서 결과에 그 교환이 한 번만 나오고, 위치가 교환 전체 줄 범위다.
  - 일반 문서만 있는 고정 Vault의 검색 결과는 `abc77e7`과 같다.
  - MCP 문서 리소스로 결과 위치를 열면 교환의 사람 턴과 답이 모두 들어 있다.
  - 확인: 통합 테스트, MCP 리소스 테스트.
- A-8 평가와 기준 재측정(S7, 측정)
  - 세션 질의 세트(한국어 40개 이상)로 4.2.10의 (a), (b), (c) 단계를 잰다. (c)의 교환 단위 recall@5가 (a)보다 높다.
  - 측정1 적중률이 (a)보다 낮지 않다.
  - 활성 세대의 세션 조각 수가 5,000개 이하다(지금 28,330개). [가정: 목표값, 위험A1]
  - 임베딩 입력이 모델 토큰 512를 넘는 세션 창이 1% 이하다.
  - 모델은 `e5-small`이다. 전체 재색인 시간과 최대 RSS를 같은 표에 적는다.
  - 확인: `tests/benchmarks/measure_session_recall.py`, `measure_vault_search_parity.py`, 보고서 커밋.
- A-9 v1 처리와 v1·v2 겹침
  - 원본이 없는 v1 파일은 `session-exchange-v1`로 색인되고 세션 파일에 `document-block-window-v2` 조각이 0개다.
  - 같은 세션의 v1·v2가 있는 고정 Vault에서 겹친 교환은 검색 결과에 한 번만(v2 쪽) 나오고, v1에만 있는 교환은 남는다. 색인 전후로 Vault 파일 sha256이 같다.
  - 실제 세션 하나를 v1·v2로 모두 두고 빠진 v1 교환과 남은 v1 교환 수를 기록한다(위험A10).
  - 확인: 통합 테스트, 측정 기록.
- A-10 LLM 없는 기준선과 경계 문장(S8)
  - `src/vault_graph/`에 로컬 언어 모델 포트, `derived` 조각, `--no-derived` 옵션이 없다. `docs/SPEC.md` 원칙1 문장은 4.4.8 문장6 보충 말고 바뀌지 않는다.
  - `AGENTS.md`와 `docs/SPEC.md`에 4.4.8의 문장1~10과 §0 규칙5 예외 문장(4.4.4)이 있고, 이 커밋이 S8의 첫 커밋이다.
  - 확인: `src/`에서 `derived`, `LocalLanguageModel` 검색 결과 0건, 문서 diff 검토.
- A-11 Codex 계약과 backlog
  - 4.2.3 필드 대응표가 `docs/contracts/vg-session-jsonl-v1.md`에 있다.
  - backlog B-1(Codex adapter)과 B-2(로컬 언어 모델 단계, 4.2.8 메모의 결정성 규칙 포함)가 완료 조건과 함께 `docs/SPEC.md` §9.2 n차 로드맵의 새 행으로 있다.
  - 확인: 문서 검토.

### 8.2 이슈B+C 색인 속도

- A-12 원인3 단기 수정
  - 33,000개 이상 항목을 가진 임시 Chroma 컬렉션에서 `export_manifest`가 모든 행을 돌려준다. limit 없는 `get`의 결과도 기록한다(위험B1).
  - `VectorIndexer.plan`이 예외를 내도 `vg index`가 traceback으로 멈추지 않는다. 결과에 벡터 실패와 오류 요약이 있고, 새 세대에 메타데이터·그래프가 발행되며, `vg status`가 벡터가 오래됐다고 보인다.
  - 측정: 이 컴퓨터에서 `vg index --vault-id vault-graph`가 성공하고 `vector/manifest.json`의 revision이 바뀐다.
  - 확인: 통합 테스트 둘, 측정 로그.
- A-13 재시도 간격과 경고
  - 같은 오류로 두 번 실패한 Vault는 2시간 안에 세션 시작 백그라운드 색인이 벡터 색인을 하지 않고 메타데이터 색인은 한다.
  - 성공하면 실패 기록이 사라진다.
  - 실패 기록이 있으면 `vg hook session-start` 표준 오류에 경고 한 줄이 있고 표준 출력은 같다.
  - 확인: 시계를 주입한 단위 테스트.
- A-14 원인2 재임베딩 범위
  - 조각 100개 문서 끝에 20개 분량을 덧붙이면 모델 입력이 새 조각과 마지막 조각 합 이하다.
  - provenance family만 바뀐 문서는 모델 입력 0개다.
  - 메타데이터 갱신 뒤 Chroma 벡터 값이 같다(위험B2).
  - 확인: 가짜 임베딩 제공자 통합 테스트.
- A-15 벡터 목록 표
  - 증분 계획 중 Chroma 목록 조회가 한 번도 불리지 않는다.
  - 표를 지우거나 행 하나를 지운 세대에서 증분 색인하면 표가 다시 만들어지고 계획이 같다.
  - 확인: 통합 테스트.
- A-16 원인5 메모리
  - 모든 배치가 `항목 수 × 최대 추정 토큰 ≤ token_budget`과 `항목 수 ≤ max_batch_items`를 지키고, 배치마다 Chroma 쓰기가 한 번 있다.
  - 측정: `e5-small` 전체 재색인 최대 RSS가 6GB 이하다. [가정: 목표값, 위험B6] 재색인 시간이 지금(26k 조각 약 830초)보다 길지 않다. 아레나 켬·끔 결과를 함께 적는다.
  - 확인: 단위 테스트, `/usr/bin/time -l` 로그.
- A-17 임베딩 캐시
  - 캐시가 데워진 상태에서 `vg index --full`의 모델 입력이 0개다.
  - 캐시를 지우고 다시 만든 벡터가 같다.
  - 발행 뒤 캐시 키 수가 활성 세대 벡터 수 이하다.
  - 확인: 가짜 임베딩 제공자 통합 테스트.
- A-18 원인4 고정 비용
  - 세대 준비 뒤 스테이징 SQLite를 고쳐도 활성 세대 파일 sha256이 같다. `clonefile` 실패 테스트에서 `copytree`와 경고 한 줄이 나온다.
  - 바뀐 파일이 없는 증분 run에서 Vault 파일을 하나도 열지 않는다.
  - 측정: 증분 run 하나가 늘린 디스크 사용량이 50MB 이하다(지금 약 650MB).
  - 확인: 단위 테스트, `du` 로그.
- A-19 바뀐 문서 단위 그래프 갱신
  - 링크를 거는 문서, 링크를 받는 문서, `supersedes`로 family가 바뀌는 문서 각각에서 증분 결과의 엔티티·관계·근거 행 집합이 full run과 같다.
  - 측정: `vg index --dry-run --vault-id vault-graph`의 엔티티 upsert 수가 바뀐 문서 수에 비례한다.
  - 확인: 비교 테스트, dry-run 로그.

### 8.3 이슈D vg 기억 관리

- A-20 범위 규칙과 `sharable`
  - 표 테스트: (`project` 같음, 다름, 없음) × (연결 프로젝트 하나, 둘 이상) × (`sharable` true, false, 필드 없음)의 열여덟 경우가 4.4.2 규칙1~3대로다. "필드 없음"은 false와 같은 결과다. 연결 프로젝트가 하나인 Vault의 `project` 없는 페이지는 `sharable` 값과 상관없이 그 프로젝트 것이다.
  - 이 컴퓨터의 `vault-map.json`으로: vault-graph 프로젝트 세션 시작 회상에 vault-graph Vault의 `project` 없는 페이지가 들어간다(리뷰1). personal Vault의 `project` 없는 페이지는 `sharable`을 설정하기 전에는 들어가지 않는다.
  - 둘 이상 프로젝트에 연결되고 `sharable`이 없는 Vault가 있으면 `vg status`와 `vg hook session-start` 표준 오류에 그 Vault 이름과 설정 방법을 담은 안내가 한 줄씩 있고, 설정하면 사라진다.
  - `sharable` false Vault의 `project` 없는 페이지가 회상에는 없고, 같은 질의의 `vg search` 결과에는 있다.
  - 회상, `summarize_project_memory`, L3 목록, `list_memory_candidates`가 같은 고정 Vault에서 같은 페이지 집합을 프로젝트 기억으로 고른다.
  - 확인: 단위 테스트, `page_in_project`를 정의하는 곳이 M10 하나인지 보는 검색.
- A-21 `remember`의 계층 표시
  - 프로젝트 폴더를 `cwd`로 한 `remember` draft에 `project: <id>`가 있고, `memory_kind="correction"`이면 `tags`에 `correction`이 있다. 프로젝트 밖이면 `project`가 없다.
  - 확인: draft 단위 테스트.
- A-22 정리 꾸러미
  - 고정 상태(L1 노트 둘 중 하나만 반영, 세션 교환 셋 중 하나만 wiki가 인용, 비슷한 페이지 쌍 하나, 근거 코드 경로가 사라진 페이지 하나)에서 `list_memory_candidates`가 네 종류 후보를 정해진 순서로 돌려주고, 후보마다 비교 재료가 5개 이하로 붙는다.
  - 같은 상태로 두 번 부르면 결과가 같다.
  - `mark_candidates_reviewed` 뒤 그 후보가 다시 나오지 않고, 기록은 Graph Home `memory/reviewed.jsonl`에만 있다. 이 파일을 지우면 그 후보가 다시 나온다.
  - 사용 기록에 "90일 주입만, 열람 0"인 페이지가 폐기 후보로 나오고, 사용 기록을 지우면 그 후보만 사라진다.
  - 후보를 만드는 동안 Vault와 L1 폴더 파일 sha256이 바뀌지 않는다.
  - 확인: 통합 테스트.
- A-23 판단 흐름과 `basis` 규칙
  - MCP prompt 목록에 `curate_memory`가 있고, 본문에 4.4.4의 여섯 단계가 있다.
  - 한 정리에서 11번째 `inferred` 제안이 `rejected`다. [가정: 목표3]
  - 측정 1회: 실제 세션에서 "기억 정리해"로 정리를 돌려, 만든 `stated`와 `inferred`의 수와 승인 결과를 PR 설명에 적는다(비밀값 없이).
  - 확인: MCP prompt 테스트, 단위 테스트, 측정 기록.
- A-24 L1 읽기와 `import-source`
  - 고정 L1 폴더(`CLAUDE_CONFIG_DIR`, `autoMemoryDirectory` 각각 지정)에서 어댑터가 노트를 찾는다.
  - vg의 미반영 판정이 같은 Vault의 `memory-scan --json`과 같다.
  - E2E(요청S8 뒤): `import_auto_memory`가 `raw/imports/claude-memory/` 아래 사본 경로를 돌려주고, 같은 노트를 다시 보내면 새 파일이 없다. L1 노트 파일 sha256과 mtime이 바뀌지 않는다.
  - 확인: 어댑터 테스트, E2E.
- A-25 대체와 폐기
  - claim 표에 `superseded` 행이 있는 고정 페이지에서 그 행의 문장이 회상 출력과 L3 목록에 없고, 현재 행은 있다.
  - 폐기 후보 점수가 높은 페이지가 있어도 Vault 파일이 바뀌지 않는다(자동 폐기 없음).
  - 확인: 단위 테스트, sha256 비교.
- A-26 회상 예산
  - 회상 출력이 1,500토큰과 9,000자 이하이고 구획A ≤ 400, 구획L3 ≤ 500, 구획C·D ≤ 180토큰이다.
  - 구획L3를 만들지 못하는 고정 상태에서 구획B가 그만큼 길어지고 나머지 구획은 같다.
  - 사용 기록을 지운 상태와 있는 상태에서 구획A·L3·B 텍스트가 같다.
  - 정리 대기 줄은 후보가 있을 때만 있고, 수가 `list_memory_candidates`와 같다.
  - 확인: 단위 테스트.
- A-27 L3 목록과 brief
  - S9: `summarize_project_memory`와 구획L3가 같은 함수로 같은 목록을 만든다. Graph Home과 Vault에 L3 목록 파일이 없다(회상 전후 두 폴더의 파일 목록 비교).
  - S12(E2E, 요청S9 뒤): `remember(kind="project")`가 프로젝트 기본 저장 Vault에 `wiki/projects/<project>.md`(`type: project`, `project: <id>`)를 만들고, 다음 회상의 구획L3 앞부분에 brief가 나온다. 같은 프로젝트에서 두 번째 `remember(kind="project")`는 `rejected`이고 `update_memory`는 된다.
  - vg가 brief 본문을 만들거나 고치는 코드 경로가 없다.
  - 확인: 단위 테스트, E2E, `src/`에서 `wiki/projects/`에 draft를 만드는 호출이 `remember`·`update_memory` 경로뿐인지 검색.
- A-28 기억 품질 측정(S11)
  - 평가 세트(질문 40개 안팎)로 지표1~6을 잰다. 지표1(대체·폐기 기억 주입 수)과 지표2(`sharable` false Vault의 다른 프로젝트 기억 주입 비율)가 0이다.
  - 확인: `tests/benchmarks/measure_memory_recall.py`, 보고서 커밋.
- A-29 이전 중 회상 유지
  - S8~S12 각 묶음 뒤에 vg 경로 회상과 `recall.sh` 경로 회상이 모두 비어 있지 않은 출력을 낸다(고정 Vault, 고정 기억 하나 이상).
  - 확인: 각 묶음 PR에 두 경로 출력 첫 줄을 적은 확인 기록. vg 쪽은 통합 테스트.
- A-30 대체 경로 동결과 제거
  - S8~S11 동안 vault-builder 쪽 `memory-cleanup`, `maps.py` 프로젝트 요약, `recall.sh`, `/project-memory`에 범위 규칙 맞춤(요청S4)과 brief 읽기(요청S9) 말고 변경이 없다.
  - S12: 사람 확인 기록이 있은 뒤 요청S11이 반영되고, vg 경로 회상이 그대로 나온다.
  - 확인: vault-builder 저장소 `git log` 경로 필터, 확인 기록.
- A-35 brief 갱신 시점(S12)
  - `brief_staleness` 표 테스트: brief 없음 + 결정 4개 → 갱신 아님, brief 없음 + 결정 5개 → 갱신 필요, brief 뒤 새 결정 4개 → 갱신 아님, 5개 → 갱신 필요. 대체·폐기된 결정과 다른 프로젝트 결정은 세지 않는다.
  - 갱신 필요 상태에서 세션 시작 회상 구획D에 `brief 갱신 필요` 줄이 한 번 있고, `list_memory_candidates`에 `brief:<project>:<해시>` 후보가 있으며, 비교 재료가 새 결정 페이지 목록이다.
  - 에이전트가 `update_memory`로 brief를 고치고 다시 색인하면 안내 줄과 후보가 사라진다.
  - 후보를 건너뛰면 후보는 사라지고, 새 결정이 하나 더 생기면 다시 나온다. 안내 줄은 기준에 걸려 있는 동안 계속 나온다.
  - 계산 전후로 Vault 파일 sha256이 같다(vg가 brief를 쓰지 않음).
  - 확인: M10 단위 테스트, 회상 통합 테스트, 고정 Vault E2E.

- A-36 증분과 full의 같음(S5, 리뷰2)
  - 고정 Vault에 v1 파트 둘이 있는 세션에 v2 파트 하나를 더하고 증분 색인한 결과(조각 id 집합, 키워드 행, 벡터 메타데이터)가, 같은 상태를 full run한 결과와 같다. 겹친 v1 교환은 두 결과 모두에 없다.
  - v2 파트를 지우고 증분 색인하면 빠졌던 v1 교환이 돌아온다.
  - `supersedes`로 family가 바뀐 문서에서도 증분과 full이 같다.
  - 바뀐 파일이 없는 세션 묶음의 파일은 열지 않는다.
  - 확인: 통합 테스트.
- A-37 v1에서 v2로 넘어가기(E2E, 요청S10 뒤, 리뷰3)
  - v1 파트 2까지 있는 세션을 `--normalized`로 수집하면 파트 3이 v2이고, 파트 2의 `last_turn_uuid` 뒤 턴만 들어 있다. 첫 교환이 이어진 교환이면 숨은 메타 줄에 `continued=1`이 있다.
  - 이 세션을 색인하면 v1과 v2 사이에 빠지거나 겹친 턴이 없다(턴 uuid 집합 비교).
  - `vg session export --recapture`는 v2 파트를 가장 높은 번호 + 1부터 쓰고 기존 파일 sha256이 같다. 색인 결과에서 겹친 v1 교환이 빠진다.
  - 확인: E2E.
- A-38 claim 대체와 처리 기록(S10, 리뷰4·5)
  - E2E: claim 표가 있는 페이지에 `supersede_claim(basis="stated")`를 보내면 옛 행이 `superseded`이고 `Superseded by:` 근거가 있으며 새 행이 그 아래에 있다. 다른 claim 행과 본문은 바이트 단위로 같다. 다음 회상에 옛 행 문장이 없다.
  - `candidate_key`를 넘긴 `remember(basis="inferred")`가 `proposed`이면 그 후보가 다음 `list_memory_candidates`에 없다. `rejected`면 남는다.
  - 파일 경로만 적은 근거는 교환 후보를 빼지 않고, 교환 줄 범위를 적은 근거는 그 교환만 뺀다.
  - 180일보다 오래된 세션 교환은 후보에 없고 `vg search`에는 있다.
  - brief 후보 키가 같은 날 두 번째 결정이 생기면 바뀐다.
  - 확인: E2E, 통합 테스트.
- A-39 폐기 기억 찾기와 되살리기(S10, 리뷰6)
  - `include_retired` 없이 검색하면 폐기 페이지가 없고, 참이면 있으며 결과에 `status`와 `retired_reason`이 있다. 회상 출력은 옵션과 상관없이 같다.
  - 정리 비교 재료에 폐기 페이지가 "폐기됨" 표시와 함께 나온다.
  - E2E: `restore_memory`가 frontmatter만 바꾸고(`status: active`, `restored_at`, `restored_reason`) 본문 바이트가 같다. 다시 색인하면 회상과 기본 검색에 나온다. 폐기되지 않은 페이지에는 `rejected`다.
  - 확인: 통합 테스트, E2E.

### 8.4 경계, 호환, 작업 조건

- A-31 Vault 쓰기 경계
  - `src/vault_graph/`에서 Vault 경로, `raw/`, L1 폴더에 쓰는 새 호출이 없다. 기존 read-only 경계 테스트가 통과한다.
  - 색인, 회상, export, 정리 꾸러미 전후로 고정 Vault와 고정 L1 폴더의 모든 파일 sha256이 같다.
  - Vault에 쓰는 경로는 publish-draft, `review propose`, 수집 실행기, `import-source` 넷뿐이다(4.4.8 문장1). `supersede_claim`과 `restore_memory`도 publish-draft나 `review propose`로만 쓴다.
  - vg가 만든 목록, 점수, 요약이 Vault 파일에 들어가는 경로가 없다(4.4.8 문장4).
  - 확인: 경계 테스트, sha256 비교 테스트.
- A-32 호환
  - 기존 MCP 도구 14개와 CLI 명령의 기존 입력·출력 필드가 그대로다. 새 MCP 도구는 다섯이고, 기존 도구에는 선택 입력(`include_retired`, `candidate_key`)만 더한다.
  - Graph Home 설정에 `embedding_batch_size`만 있어도 색인이 동작한다.
  - `sharable`가 없는 version 2 `vault-map.json`으로 기존 테스트가 통과한다.
  - `tests/test_feature_import_direction.py`의 `_KNOWN_VIOLATIONS`가 빈 집합이고 `_KNOWN_VIOLATION_CEILING`이 0이며, `_AREAS`에 M19가 있다. `tests/test_module_import_cycles.py`가 0건이다.
  - 확인: `pytest` 전체.
- A-33 문서
  - `AGENTS.md`와 `docs/SPEC.md`에 4.4.8의 문장1~10과 §0 규칙5 예외 문장이 있다. `docs/SPEC.md` §0 "현재 구현과의 차이"의 "폐기 페이지를 포함해 검색하는 옵션은 없다" 줄이 지워진다.
  - `docs/SPEC.md` §4에 재시도 간격, 임베딩 캐시, export 설정 위치가, §5에 MCP 도구 19개, `include_retired`, `kind`의 `project`가, §6에 범위 규칙과 `sharable`이 있다.
  - `docs/ARCHITECTURE.md` §1·§3.1·§4에 M19와 새 파일 위치가 있다.
  - 9.1·9.3 답과 승인된 [가정] 결정이 `docs/DECISIONS.md`에 `Question`, `Decision`, `Reason`, `Implications` 형식으로 있다.
  - 확인: 문서 검토, `tests/test_context_pack_docs_contract.py` 통과.
- A-34 브랜치와 순서
  - 모든 커밋이 `feat/jh/session-memory-indexing`에 있고 `Co-Authored-By` 줄이 없다.
  - S0 커밋이 이 작업의 첫 코드 커밋이다.
  - 확인: `git log main..feat/jh/session-memory-indexing`, `git log --format=%B main..feat/jh/session-memory-indexing | grep -c Co-Authored-By`가 0.

## 9. Open decisions

### 9.1 Spec gate 답변 (2026-11-06)

- 질문1: vg에 Claude Code와 Codex 대화 export 기능을 둔다. 내보낼 곳은 Vault 밖 사용자 지정 경로다.
- 질문2: 에이전트별 adapter와 공통 세션 형식을 이번에 정한다. Codex adapter는 spec만 쓰고 구현은 backlog로 둔다.
- 질문3: L1, L2, L3 관리를 모두 vg로 옮긴다. Vault는 저장소(ingest, update, query) 역할을 맡는다.
- 질문4: Vault별 설정 `sharable`를 둔다. true면 project 표시 없는 페이지를 연결된 모든 프로젝트 회상에 넣는다.
- 질문5: 임베딩 모델 재선정은 이 spec의 범위 밖이다. 세션 중간 문서 형식과 임베딩 방식에 집중한다.
- 질문6: 질문3의 답으로 vg가 L1 폴더를 읽는다.
- 질문7, 질문8: 추가 리서치 뒤 제안한다(`research/memory-management.md`, `research/session-format.md`).

질문7(관리 방식)과 질문8(L3 위치)의 제안은 4.4에 반영했다.

### 9.2 남은 질문

없다. 질문16과 질문17은 3차 gate에서 답했다(9.4). 사람이 정하지 않은 수치는 5.5의 [가정] 목표값 표(목표1~8)에 모았다.

9.3 기록의 "S8 제외"는 개정 전 묶음 번호다. `derived` 묶음을 뺀 뒤 묶음 번호를 하나씩 당겼으므로, 지금 S8은 기억 단계1이다(4.6).

### 9.3 Spec gate 답변 2차 (2026-11-06)

- 질문9: 경계 문장 7곳을 모두 승인한다(4.4.8).
- 질문11: v1과 v2가 겹치면 vg가 색인에서만 겹친 v1 교환을 뺀다. Vault 파일은 그대로 둔다.
- 질문12: 로컬 모델 `derived` 단계는 다음 spec으로 미룬다. 이 spec은 LLM 없는 기준선을 만들고 잰다(S8 제외).
- 질문10: 첫 질문이 이해되지 않아 다시 묻는다.
- 질문10(다시): 사용자가 판단을 위임했다. [가정] 목록은 vg가 회상 때 계산하고 저장하지 않는다. brief는 Vault 페이지로 두고 에이전트가 기존 쓰기 경로로 쓴다. 갱신 시점은 vg가 관리한다(brief 이후 새 결정 수가 기준을 넘으면 세션 시작 안내와 `curate_memory`가 갱신을 다룬다). 이유: Vault는 판단된 지식의 저장소이고, 목록은 다시 계산할 수 있으며, 질문9로 승인한 "기계 생성물은 Vault에 쓰지 않는다" 규칙과 맞는다.
- 질문13: brief는 `wiki/projects/<project>.md`, 새 종류 `project`로 둔다(요청S9).
- 질문14: 사용 기록과 건너뜀 기록을 Graph Home에 두고 정리 후보 제안에만 쓴다. §0 규칙5에 예외를 적는다. 회상 순위에는 쓰지 않는다(결정32 유지).
- 질문15: 설정의 역할 설명을 요청해 다시 묻는다.
- 질문15: 설정 이름을 사용자 제안대로 `sharable`로 바꾼다(`share_untagged` 대체). 설정이 없으면 false로 다루고, `vg status`와 세션 시작에 설정 안내 한 줄을 낸다. false는 세션 시작 기억 목록에 넣지 않는다는 뜻이며 검색에는 그대로 나온다.

### 9.4 독립 리뷰 반영 (2026-11-06)

독립 리뷰가 막음 7건과 참고 11건을 냈다. 사용자는 "vault, vault-builder, vault-graph의 역할과 의도를 고려해서 개선"하라고 지시했다. 기준은 4.0이다.

| 리뷰 | 문제 | 반영 |
|---|---|---|
| 리뷰1 | `sharable` 기본 false면 `project` 없는 프로젝트 Vault 페이지로 회상이 빈다 | 4.4.2 규칙2, 결정40. Vault에 쓰지 않고 `vault-map.json` 연결 수로 푼다 |
| 리뷰2 | 여러 파일을 함께 보는 규칙이 증분에서 깨진다 | 4.2.13, 결정42, A-36 |
| 리뷰3 | v1→v2 커서와 파트 번호 규칙이 없다 | 4.2.12, 결정41, 요청S10, A-37 |
| 리뷰4 | claim 대체 쓰기 경로가 없다 | 4.4.4 `supersede_claim`, 결정43, A-38. Vault 기존 `patch-page` 사용 |
| 리뷰5 | 처리한 후보가 목록에서 빠지지 않는다 | 4.4.4 빠지는 규칙, 결정44, A-38. 리뷰14(brief 키)도 함께 |
| 리뷰6 | 폐기 기억을 찾거나 되살릴 수 없다 | 4.4.13, 결정45, A-39(질문16 권장안) |
| 리뷰7 | 경계 문장 세 곳이 승인 범위 밖이다 | 4.4.8 문장8~10, 결정46, 질문17로 확인 |

참고 중 함께 반영한 것: 리뷰14(brief 후보 키, 4.4.4), 리뷰16(`sharable` 전달 경로, 4.4.2 `VaultProjectScope`). 나머지 참고(리뷰8~13, 15, 17, 18)는 해당 묶음의 구현과 리뷰에서 다룬다.

3차 gate 답변(2026-11-06):

- 질문17: `docs/SPEC.md` §0 규칙2·3과 원칙5를 세 곳 모두 고친다(4.4.8 문장8~10).
- 최종 승인: 개정 spec을 승인한다. 질문16은 권장안(`include_retired`와 `restore_memory`)으로 확정한다. 목표1~8은 각 묶음 측정에서 다시 확인한다.

## 10. 추가: 파일 종류별 검색 품질 (2026-11-07, 사용자 지시)

사용자 지시(원문 요지): "임베딩 크기가 중요한 게 아니라 검색의 품질을 높이는 방법을 근본적으로 접근해야 한다. 파일의 종류, 크기 같은 것을 근본적으로 고려하고 리서치해서 개선하라." 창 크기 비교(§9.4 뒤 측정)는 참고로만 쓴다.

조사: [research/search-quality-internal.md](research/search-quality-internal.md)(코드와 실패 사례), [research/search-quality-external.md](research/search-quality-external.md)(방법과 근거).

### 10.1 평가 세트 (저장소 밖)

- wiki: personal Vault 페이지 35문항. 직접 쓴 의역 15개(정답 페이지 단어를 피함), 제목 그대로 20개.
- 세션: vault-graph 세션 교환 14문항, 직접 쓴 의역.
- 기준선(변경 전): wiki knowledge 모드 recall@5 0.43(의역 0.14, 제목 0.55), all 모드 0.60(결정·방법 0.0). 세션 recall@5 0.64, MRR 0.43(160단어), 0.45(96단어).
- 대리 세트(질의를 원문에서 뽑음)의 세션 recall@5 0.98은 이 세트에서 0.64였다. 원문에서 뽑은 질의는 쓰지 않는다.

### 10.2 원인과 고칠 것 (조사 문서의 원인1~8)

| 코드 | 원인 | 고칠 것 | 색인 다시 만듦 |
|---|---|---|---|
| 원인1 | 기본 knowledge 모드가 `wiki/sources/`(source_manifest)를 후보 단계에서 버린다 | 기본 모드에 source_manifest를 넣고 역할은 순위 가중치로 쓴다. raw_evidence(세션·원문)는 기본에서 계속 뺀다 | 아니오 |
| 원인2 | `derived_from`이 같은 페이지들을 한 family로 접어 형제 페이지가 사라진다 | `supersedes` 같은 직접 대체 관계만 접는다 | 아니오 |
| 원인3 | 결과 단위가 조각이라 한 문서가 상위 칸을 여럿 차지한다 | 모든 문서를 문서 단위로 묶고, 문서 점수는 최고 조각 점수에 나머지를 작게 더한다 | 아니오 |
| 원인4 | Vault마다 순위를 1부터 다시 매기고, 내용이 같은 페이지가 따로 나온다 | 범위 전체를 한 순위로 합치고 `content_hash`가 같은 문서는 하나로 보인다 | 아니오 |
| 원인5 | `bm25()` 열 가중치가 모두 같고 frontmatter 열에 JSON 전체가 들어간다 | 제목·별칭·경로 열 가중치, 제목 일치 신호 | 키워드 표 |
| 원인6 | 한국어 조사를 처리하지 않는다(§4.2.9 표의 "한국어 조사 처리" 칸은 사실과 다르다) | 질의 쪽 조사 떼기와 한글 앞부분 일치 | 아니오 |
| 원인7 | 구역마다 잘라 아주 작은 조각과 템플릿 구역(Claim Evidence 등)·허브 페이지가 상위를 차지한다 | 정리·source 페이지는 페이지 하나를 기본 단위로, 템플릿 구역은 벡터 입력에서 뺌. 허브 페이지는 표시만 하고 가중치는 아직 주지 않았다(§10.5) | 일반 문서 벡터 |
| 원인8 | 문서 단위 표현이 없다 | frontmatter에서 기계적으로 만든 "페이지 카드"(제목, 별칭, 요약, 태그, 파일 이름)를 문서 단위 벡터로 더한다 | 일반 문서 벡터 |

세션은 창 크기보다 위 원인3(교환 단위 묶기와 점수 합)과 원인6이 크다. 창 크기는 96단어로 바꾼다(같은 세트에서 MRR 0.43→0.45, 512 초과 12.0%→0.65%).

### 10.3 원칙과의 관계

- LLM을 쓰지 않는다(원칙1). 페이지 카드는 frontmatter의 기존 값을 기계적으로 모은 것이다.
- 결정성: 모든 순위 규칙은 고정된 식과 상수다. 같은 색인이면 같은 결과다.
- §4.2.9의 "일반 문서 벡터는 바뀌지 않는다"는 원인7·8로 바뀐다. 사용자가 이번 지시로 검색 품질을 우선했으므로 이 줄을 고친다. 일반 문서는 한 번 다시 임베딩된다(임베딩 캐시는 내용이 같은 입력만 살린다).
- 리랭커와 형태소 분석기(Kiwi)는 평가 세트로 이번 단계 효과를 본 뒤 정한다(조사 권고7·11).

### 10.4 단계와 수용 기준

1. 단계A(색인 그대로): 원인1·2·3·4·6. 수용: wiki 기본 모드 recall@5와 MRR이 기준선보다 높고, 상위 5개가 서로 다른 문서이며, 세션 recall@5가 낮아지지 않는다. 기존 테스트 통과.
2. 단계B(키워드 표): 원인5. 수용: 제목 질문 recall@5가 0.95 이상.
3. 단계C(일반 문서 벡터): 원인7·8, 세션 창 96단어. 수용: wiki 의역 질문 recall@5가 단계B보다 높다. 색인 결정성 테스트 통과.
4. 단계마다 보고서 `docs/design/reports/2026-11-search-quality.md`에 같은 평가 세트 결과를 쌓는다.

### 10.5 단계C에서 정한 것

- `wiki/` 아래 정리 페이지와 `wiki/sources/` 페이지는 `wiki-page-window-v1`로 조각 낸다. 생성된 보기(`wiki/index.md`, `wiki/maps/`), 로그, `wiki/` 밖 파일은 지금의 일반 조각기를 쓴다.
- 본문 창: 공백 토큰 160개 이하, 40개 미만이면 앞 창에 붙인다. personal Vault에서 160단어일 때 512 모델 토큰을 넘는 창이 0%다.
- 템플릿 절(Claim Evidence, Sources, Related 등)은 `template` 조각이다. 키워드 검색만 읽고 벡터 입력에서 뺀다.
- 페이지 카드(`page_card`): frontmatter의 제목, 별칭, 요약, 태그와 파일 이름만 모은 조각 하나. 생성 텍스트가 없다(원칙1). 키워드와 벡터 모두 읽는다. 본문을 다시 만들거나 인용하는 곳은 `page_body_chunks`로 카드를 뺀다: MCP 문서 리소스, recall 본문, 본문 토큰 수, 기억 출처 읽기, 문맥 확장.
- 탐색 페이지는 `document_kind=hub`로 표시한다. 순위는 아직 이 표시를 읽지 않는다. 문서 단위 결과(단계A)로 허브 페이지가 상위를 여러 칸 차지하는 문제는 사라졌고, 가중치는 평가 세트로 효과를 확인한 뒤 정한다.
- 이 브랜치에서 만든 Graph Home은 카드 위치가 작업 중에 바뀌었으므로 다시 색인해야 한다.

### 10.6 단계A·B에서 정한 것

- 단계A 순위 규칙(`retrieval/search/candidate_ranking.py`):
  - knowledge 모드 역할 가중치: canonical 1.0, source 0.8. 다른 모드에는 가중치가 없다.
  - 문서 점수: 최고 조각 점수 + 0.1 × 다음 2개 조각 점수의 합.
  - 접기: knowledge 모드에서 `supersedes`/`superseded_by` 사슬만 접는다. 다른 Vault에 `content_hash`가 같은 문서는 범위에서 먼저 나온 Vault의 것 하나만 남긴다.
  - 한국어 질의: 낱말 끝 조사·어미 하나를 떼고(남는 앞부분 2글자 이상), 3글자 이상 한글은 앞부분 일치로 찾는다.
- 단계B 키워드 표(`sqlite-keyword-v3`):
  - 열: path, section, title, aliases, frontmatter(tags, summary, 교환 메타), text.
  - `bm25()` 열 가중치: title·aliases 10, path 5, 나머지 1. SQLite FTS5 문서의 열 가중치 예시와 같은 크기로 미리 정했고 평가 질문에 맞추지 않았다.
  - 저장된 버전이 다르면 `vg index`가 같은 DB의 문서·조각으로 키워드 표를 다시 채운다. 다시 임베딩하지 않는다.
- 제목 일치 신호: 질의가 제목·별칭과 같으면 1위, 2단어 이상 제목이 질의 안에 통째로 있으면 2위인 순위 목록 하나로 보고 RRF(k=60, 가중치 1.0)로 문서당 한 번 더한다. 제목이 없으면 파일 이름을 쓴다.
- 세션 창 크기 재확인(단계A·B·C 적용 뒤): 96단어는 recall@5 0.64, MRR 0.50, 512 초과 창 55개다. 160단어는 0.71, 0.40, 608개다. recall@5 차이는 14문항 중 1문항이고 목표6(512 초과 1% 이하)을 지키므로 96단어로 정한다.
- all 모드의 결정·방법 질문(8문항)은 기대 페이지가 상위 20 밖이다. 같은 주제의 원문·spec·보고서가 위에 온다. 모든 모드에 역할 가중치(1.0/0.8/0.6)를 주는 안과 결과 단위마다 후보 조각 수를 3개로 묶는 안을 재 보았으나 둘 다 이 질문들을 상위 20에 올리지 못했고 다른 값이 떨어져 넣지 않았다. 기본 knowledge 모드에서는 이 질문들이 3~10위다.
