# 세션 기록 임베딩과 조각 단위 조사

조사일: 2026-11-05. 측정은 이 Mac의 실제 파일로 했고, 내용은 읽지 않고 구조와 크기만 셌다. 측정 스크립트는 `python3 -I`로 실행했고 저장소에 넣지 않았다. 확인하지 못한 내용은 "추정"으로 표시했다.

## 1. 원본 형식

### 발견1. Claude Code 기록(`$HOME/.claude/projects/<프로젝트>/<session_id>.jsonl`)

- 이 Mac에는 380개 파일, 1.8GB가 있다. 한 줄이 JSON 객체 하나다.
- 서브에이전트 대화는 `<session_id>/subagents/agent-<id>.jsonl`에 따로 있고, 옆에 `.meta.json`, `.prefix.json`이 있다. 가장 큰 세션(본 파일 18.8MB)의 서브에이전트 파일은 72개, 58MB로 본 파일보다 3배 크다.
- 레코드 `type` 종류(18.8MB 세션 기준): `assistant` 1,458, `user` 897, `api-request` 758, `queue-operation` 534, `attachment` 319, `system` 211, 그 밖에 `last-prompt`, `mode`, `permission-mode`, `ai-title`, `custom-title`, `agent-name`, `file-history-snapshot`, `api-request-blob`, `cost-state`, `pr-link`, `relocated` 등. 예전 형식의 `summary` 레코드는 이 파일들에 없었다.
- `message.content` 블록 종류: assistant는 `text`, `thinking`, `tool_use`, user는 문자열, `text`, `tool_result`. tool_result를 담은 user 레코드에는 같은 결과가 `toolUseResult` 필드로 한 번 더 들어 있다.
- `thinking` 블록은 669개 도구 호출 대비 452개가 있지만 내용이 거의 비어 있다(전체의 0.1% 이하). 생각 내용은 기록에 남지 않는다고 본다(추정, `thinkingDisplay` 필드가 있음).
- 압축(compaction): user 레코드의 `isCompactSummary: true`가 압축 요약 본문이다. 18.8MB 세션에서 8건, 72KB였다. `compactMetadata`, `logicalParentUuid`, `summarizedTurnPromptUuids` 필드도 보인다.
- 사람 입력이 아닌 user 레코드: `isMeta: true`(스킬 본문, 명령 안내 등)와 `<`로 시작하는 태그 감싼 텍스트(명령, 작업 알림, 시스템 알림)가 있다.
- 순서를 다시 만드는 값: `uuid`, `parentUuid`(대화 트리), `logicalParentUuid`(압축 경계를 넘는 부모), `sessionId`, `timestamp`(ISO, ms), `isSidechain`, `agentId`, `promptId`, `requestId`, `message.id`, `toolUseID`/`sourceToolAssistantUUID`(도구 호출과 결과 연결), `turnPosition`.

### 발견2. 바이트 구성(3개 세션)

| 세션 크기 | 사람이 직접 쓴 user 텍스트 | assistant 텍스트 | 태그 감싼 user | isMeta user | 압축 요약 | tool_use 입력 | tool_result(+중복) | attachment·api-request 등 메타 |
|---|---|---|---|---|---|---|---|---|
| 18.8MB | 0.03% | 1.1% | 2.6% | 1.7% | 0.4% | 4.2% | 13.2% | 약 45% |
| 4.1MB | 표 생략 | 1.0% | | | | 1.9% | 7.7% | 약 57% |
| 2.2MB | 0.03% | 0.6% | 0.1% | 2.3% | 0 | 2.2% | 13.7% | 약 52% |

- 사람과 assistant의 대화 텍스트는 원본 바이트의 1~4%다. 나머지는 도구 입출력, 첨부, API 요청 메타다.
- 4.1MB 세션의 user 텍스트 분류는 첫 스크립트에서 나누지 않았다(user 텍스트 합계 3.4%).

### 발견3. Codex 기록(`$HOME/.codex/sessions/YYYY/MM/DD/rollout-<시각>-<id>.jsonl`)

- 127개 파일, 352MB가 있다. 최상위 필드는 `type`, `payload`, `timestamp`, `ordinal`, `metadata`다. `ordinal`이 줄 순서를 준다.
- `type` 종류: `session_meta`(id, session_id, cwd, git, cli_version, base_instructions 등), `turn_context`, `response_item`(payload.type = `message`(role user/assistant/developer), `reasoning`, `function_call`, `function_call_output`, `custom_tool_call`, `custom_tool_call_output`, `agent_message`), `event_msg`(`item_completed`, `token_count`, `task_started`, `task_complete` 등), `compacted`, `token_usage_record`, `world_state`.
- `reasoning`은 `encrypted_content`와 `summary`만 있어 본문을 읽을 수 없다.
- 2.4MB 파일에서 `event_msg:item_completed`가 69%, 도구 출력이 11%, user/assistant `message`는 1.4%였다. 1.3MB 파일에서는 `compacted` 한 줄이 15%였다.
- vault-builder는 Codex 기록을 캡처하지 않는다(`session_capture.py`에 codex 언급 없음).

## 2. vault-builder의 변환 (`$HOME/workspace/vault-builder/tools/wiki/lib/`)

- 입력: 훅 JSON의 `transcript_path`와 같은 폴더의 `<session_id>/subagents/*.jsonl` (`session_capture.py:86-115`). 트리거는 `PreCompact`, `SessionEnd`, `manual` (`session_capture.py:312`).
- 남기는 것: `type`이 user/assistant인 레코드의 `text` 블록과 `tool_use`의 도구 이름만 (`session_capture.py:172-221`).
- 버리는 것: `isMeta` user, thinking, 도구 입력, tool_result, 이미지, 나머지 모든 레코드 타입 (`session_capture.py:179-182`, `204-205`). 태그 감싼 user 텍스트(명령, 작업 알림)는 남는다.
- 정렬: uuid로 중복을 없애고 timestamp, 파일 순서로 정렬한다. `parentUuid` 트리는 쓰지 않는다 (`session_capture.py:101-115`).
- 렌더링: 턴마다 `## <timestamp> <role>` 또는 `## <timestamp> subagent <agent_id> <role>` 제목, 본문, `Tools: a, b` 한 줄 (`session_capture.py:527-541`). 비밀값은 정규식으로 가린다 (`session_capture.py:277`).
- 파트 분할: 크기가 아니라 캡처 시점으로 나눈다. 이전 최고 파트의 frontmatter `last_turn_uuid`를 커서로 삼아 그 뒤 턴만 새 파일 `raw/sessions/claude-code/<첫 턴 날짜>-<session_id>-part<N>.md`에 쓴다 (`session_capture.py:117-136`, `482-524`, `647`). 기존 파트 파일은 고치지 않고, `body_sha256`으로 본문 변경을 검사한다.
- 원본 jsonl은 Vault 어디에도 복사하지 않는다. 턴별 uuid도 본문에 남기지 않고 frontmatter의 첫/마지막 uuid만 남는다 (`session_capture.py:543-560`).

### 발견4. 지금 md 파일의 실제 구성(이 Mac, 22개 파트 파일, 5.1MB)

- 턴 제목 블록 16,346개 중 12,945개(79%)가 본문 없이 `Tools: ...` 한 줄뿐이다.
- 11,473개(70%)가 서브에이전트 턴이다.
- 본 에이전트에서 텍스트가 있는 턴은 1,865개뿐이다.
- 사람이 쓴 user 메시지로 시작하는 교환(user 메시지 + 다음 user 메시지 전까지의 assistant 텍스트)은 171개다. 공백 토큰 기준 중앙값 514, 상위 10% 5,883, 최대 20,534, 합계 32.5만이다. 256을 넘는 교환이 119개다. 서브에이전트 텍스트는 18.2만 토큰이다.

## 3. vault-graph의 지금 조각 방식

- 제목 블록을 만나면 조각을 끊는다 (`src/vault_graph/indexing/ingestion/document_chunking.py:118-119`). 그래서 세션 md는 턴 하나가 조각 하나가 되고, `Tools: Bash` 같은 1~5토큰 조각이 대부분이다. 이것이 15,273조각, 평균 13~104토큰의 원인이다.
- 토큰 수는 공백으로 나눈 개수다 (`document_chunking.py:227-228`). 한국어 어절 1개는 모델 토큰 여러 개가 되므로 256 공백 토큰이 e5의 512 토큰 한도를 넘을 수 있다(추정).
- 임베딩 텍스트는 `Section path: <제목>` + 본문이다 (`document_chunking.py:139-145`). 세션에서는 제목이 timestamp와 role이라 의미 없는 숫자가 임베딩에 들어간다.
- 조각 id는 `stable_id("chunk", CHUNKER_VERSION, vault_id, path, boundary_key)`이고 (`document_normalizer.py:51-60`), boundary_key는 섹션 경로, 블록 내용, 같은 내용의 출현 순번으로 만든다 (`document_chunking.py:211-224`, `markdown_parser.py:340-350`, `440-449`). 위치 정보는 markdown 줄 번호와 문자 오프셋이다 (`markdown_parser.py:418-428`).
- 파트 파일이 한 번 쓰이면 바뀌지 않으므로, 지금 방식에서도 세션이 자라며 기존 조각 id가 바뀌는 일은 없다. 새 턴은 새 파트 파일로 들어온다.

## 4. 조각 단위 비교

| 단위 | 의미 검색 | 키워드 검색과 위치 | 조각 수(지금 데이터) | 문제 |
|---|---|---|---|---|
| 레코드(턴)마다 (지금) | 나쁨. 짧은 조각, 도구 이름만 있는 조각이 상위를 차지 | 줄 위치는 정확 | 약 15k | 도구 전용 조각이 79% |
| 턴마다, 도구 전용 턴 제외 | 보통. assistant 답만 있고 질문 맥락이 없음 | 정확 | 약 1.9k(본) + 서브에이전트 | 짧은 "확인했습니다" 류가 남음 |
| 교환(사람 질문 + 답, 도구 접기) | 좋음. 질문과 답이 한 조각 | 교환 범위 줄 위치 | 171 교환, 창 나누면 약 1.5~2k | 긴 교환(p90 5.9k 토큰)은 창으로 나눠야 함 |
| 교환 안 고정 창(질문 첫 줄을 머리말로 반복) | 좋음 | 창마다 줄 범위 | 약 1.5~2k(추정) | 창 경계가 문장 중간에 올 수 있음 |
| 미끄러지는 창(겹침) | 약간 좋음 | 같은 줄이 여러 조각에 나와 키워드 결과 중복 | 1.5~2배 | 결과 중복, 근거 표시 혼란 |
| 세션/교환 요약 | 질문형 회상에 가장 좋음 | 요약은 원문 위치가 없음 | 교환당 1 | LLM 생성이 필요하고 결정적이지 않음. vault-graph가 Vault에 쓰면 경계 규칙 위반 |

- 결론: 기본 단위는 "교환 안의 고정 창"이 맞다. 겹침은 쓰지 않는다. 키워드 검색 결과 중복을 피하고, 지금의 무겹침 정책(`document_chunking.py:86`)과 같다.
- 요약은 vault-builder가 Vault의 wiki 페이지로 만들 때만 쓴다. vault-graph가 만들지 않는다(AGENTS.md 경계 규칙).

### 추가만 되는 세션에서 조각 id가 안정되려면

- 파트 파일 단위로 조각을 만들면 된다. 파트 파일은 바뀌지 않으므로 id가 이동하지 않는다.
- 교환이 두 파트에 걸치면 각 파트에서 따로 조각을 만든다. 다음 파트의 첫 조각에는 질문이 없으므로, 머리말에 "이전 파트에서 이어짐"과 세션 id만 넣는다. 질문 텍스트를 끌어오면 앞 파트에 의존하게 되어 id가 흔들린다.
- 원본 jsonl을 직접 색인한다면 id는 `session_id + 교환 시작 user uuid + 창 번호`로 만들어야 한다. 바이트 오프셋이나 줄 번호는 압축과 재기록 때 흔들릴 수 있다(추정). 마지막 교환은 아직 자라는 중이므로 "닫힌 교환"(다음 사람 메시지가 온 교환)만 색인한다.

## 5. 임베딩 모델 v3 후보

| 모델 | 크기/차원 | 최대 토큰 | 라이선스 | 한국어 근거 | fastembed |
|---|---|---|---|---|---|
| multilingual-e5-small (지금) | 118MB int8, 384d | 512 | MIT | 한국어 7과제 NDCG@10 0.671 (기존 조사) | 사용자 등록, 동작 확인 |
| multilingual-e5-base | 278M 파라미터, 768d | 512 | MIT | KURE 표 NDCG@10 0.632 | 기본 목록에 없음, 사용자 등록 필요(추정) |
| multilingual-e5-large | 2.24GB, 1024d | 512 | MIT | 0.664 (KURE 표), 0.722 (기존 조사) | 기본 목록 |
| bge-m3 | 568M, 2.27GB fp32, 1024d | 8192 | MIT | 0.687 (KURE 표) | 기본 목록 없음. dense만 사용자 등록 가능. sparse 출력은 fastembed가 지원하지 않음 |
| KURE-v1 (bge-m3 한국어 미세조정) | 0.6B, 1024d | 8192 | MIT | 0.695 (KURE 표, 1위) | ONNX 변환 필요(추정) |
| snowflake-arctic-embed-l-v2.0 | 570MB int8, 1024d | 8192 | Apache-2.0 | 0.682 (KURE 표) | 사용자 등록 동작 확인. 전체 재색인은 끝나지 않음(40GB) |
| snowflake-arctic-embed-m-v2.0 | 약 305M, 768d(MRL 256 가능) | 8192 | Apache-2.0 | 한국어 표 없음 | ONNX 있음, 사용자 등록 필요. 크기/토큰은 기억에 의존(추정) |
| gte-multilingual-base | 약 305M, 768d(128~768 가변) | 8192 | Apache-2.0 | 0.640 (KURE 표) | `trust_remote_code` 필요, ONNX 여부 확인 못함 |
| jina-embeddings-v3 | 570M, 1024d | 8192 | CC-BY-NC | 0.653 (KURE 표) | 기본 목록에 있으나 비상업 라이선스라 제외 |
| nomic-embed-text-v2-moe | 475M MoE, 768d | 512 | Apache-2.0 | 한국어 근거 못 찾음 | 확인 못함(추정: 미지원) |

- 희소 검색: fastembed의 희소 모델은 `Qdrant/bm25`, `bm42-all-minilm-l6-v2-attentions`, `Splade_PP_en_v1`이고 SPLADE는 영어 전용이다. bge-m3 희소 출력은 fastembed에 없다. vault-graph는 이미 SQLite 키워드 색인이 있으므로 (`src/vault_graph/storage/local/sqlite_keyword_index.py`) 학습형 희소 벡터를 더할 이유가 약하다.
- 비용: 지난 측정에서 e5-small 26k조각이 약 14분(830초), 상주 메모리 21.2GB였고 arctic-l은 메모리 사용량 40GB로 스왑이 나서 1시간 55분 안에 끝나지 않았다(`docs/specs/2026-11-04-embedding-model-selection/spec.md:236-237`). 세션 조각이 15k에서 약 2~3k로 줄면 전체 조각이 약 13k가 되어, 같은 모델 기준 시간이 절반쯤으로 준다(추정). 768d 모델(e5-base, arctic-m)은 e5-small의 약 2.5~3배 연산이라(추정) 재색인이 e5-small 지금 수준과 비슷해진다.
- 메모리 21GB는 배치 256에 긴 조각이 섞여 패딩이 커진 결과로 본다(추정). 조각 길이를 모델 토큰 기준으로 자르고 배치를 32~64로 줄이면 줄어든다(추정, 측정 필요).

## 6. 권장 설계

### 결정1. 무엇을 저장하나

- Vault에는 지금처럼 vault-builder가 쓴 md 파트 파일만 둔다. vault-graph는 원본 jsonl을 읽지도 복사하지도 않는다. 원본은 1.8GB, 대화 텍스트는 1~4%이고 비밀값 가림이 없으며, 경계 규칙상 vault-graph가 `raw/`에 쓸 수 없다.
- vault-builder 쪽 요청(별도 작업): 턴 제목에 uuid를 넣거나(`## <ts> <role> <uuid8>`), 도구 전용 assistant 턴을 앞 텍스트 턴의 `Tools:` 줄로 합치는 것. 두 번째만으로 md 블록 수가 약 79% 준다.
- 정규화 jsonl은 만들지 않는다. md에 이미 role, timestamp, agent, 본문이 있고 frontmatter `schema: vault-session/v1`로 형식을 알 수 있다.

### 결정2. 무엇을 임베딩하나

- 포함: 사람 user 메시지, 본 에이전트 assistant 텍스트, 압축 요약(vault-builder가 남기는 경우).
- 제외: `Tools:`만 있는 턴(키워드 색인에는 교환 메타로 남김), 태그 감싼 user 텍스트(작업 알림, 명령 출력).
- 서브에이전트: 본 대화와 섞지 않고 `agent_id`별 교환으로 따로 조각 낸다. 서브에이전트 턴이 70%라 섞으면 본 대화가 묻힌다. 검색 점수에서 본 대화보다 낮게 둘지는 측정 후 정한다.
- tool_result, thinking은 md에 없으므로 고려하지 않는다.

### 결정3. 조각 단위와 id

- 새 조각기 `session-exchange-v1`을 `schema: vault-session/v1` 파일에만 쓴다. 다른 md는 `document-block-window-v2` 그대로다.
- 교환 = 사람 user 턴 하나 + 다음 사람 user 턴 전까지의 같은 agent 턴. 교환 안에서 모델 토큰 기준 약 400 이하의 고정 창으로 나누고 겹치지 않는다. 창 크기 기준은 공백 토큰이 아니라 모델 토크나이저 토큰으로 바꾼다.
- 임베딩 텍스트 머리말: `Session: <project> <날짜> part<N>` + `Question: <교환 첫 user 메시지 앞 200자>`. timestamp 제목은 넣지 않는다.
- id: `stable_id("chunk", "session-exchange-v1", vault_id, path, 교환 첫 턴 제목, 같은 제목 출현 순번, 창 번호)`. 파트 파일이 바뀌지 않으므로 세션이 자라도 기존 id는 그대로다.

### 결정4. 키워드 검색과 위치

- 키워드 색인도 같은 교환 창 조각을 쓴다. 조각 수가 줄어 "Bash"만 맞는 결과가 사라진다.
- `source_locators`는 창에 들어간 턴들의 markdown 줄 범위를 그대로 쓴다 (`markdown_parser.py:418-428` 형식). 인용과 `vg-source://` 해석은 파일 경로와 줄이 유지되므로 바뀌지 않는다.
- 도구 이름은 조각 메타(`tools: Bash×5, Edit×2`)로 키워드 색인에만 넣어 "어느 세션에서 Edit 했나" 검색을 남긴다.

### 결정5. 모델

- v3 기본은 e5-small을 유지하고, 세션 조각을 바꾼 뒤 다시 잰다. 조각 품질 문제가 모델 문제보다 크다(조각 79%가 도구 이름).
- 다음 후보는 KURE-v1 또는 bge-m3 dense(한국어 1, 2위, MIT, 8192 토큰)와 arctic-embed-m-v2.0(Apache, 768d, 크기 절반)이다. 조각이 13k로 준 뒤 측정 대상으로 둔다.
- 학습형 희소 벡터는 넣지 않는다. SQLite 키워드 색인이 그 역할을 한다.

### 결정6. 이전 경로

1. `vault-session/v1` 판별과 `session-exchange-v1` 조각기를 추가한다. 다른 파일의 조각 id는 바뀌지 않는다.
2. 세션 파일만 재색인한다. 세션 조각 id, 벡터, 키워드 행이 모두 바뀌므로 이전 세션 조각을 가리키던 인용은 끊긴다.
3. `tests/benchmarks/measure_vault_search_parity.py`의 세션 관련 기대값을 다시 만든다. 세션 질의 세트(짧은 한국어 질문)를 따로 추가해 전후 회상률을 비교한다.
4. 측정 결과를 보고 모델 후보(결정5)를 바꿀지 정한다.

### 위험

- 위험1. 세션 조각 id가 모두 바뀌어, 이미 저장된 기억이나 인용이 가리키던 세션 근거가 열리지 않는다.
- 위험2. 교환 경계 판단(사람 메시지인지 태그 감싼 알림인지)이 vault-builder 렌더 형식에 의존한다. vault-builder가 형식을 바꾸면 교환이 잘못 나뉜다. `schema` 버전으로 막아야 한다.
- 위험3. 서브에이전트를 따로 두면, 서브에이전트만 아는 사실(조사 결과)이 본 대화 질의에서 덜 나온다.
- 위험4. 모델 토큰 기준 창으로 바꾸면 조각기가 토크나이저에 의존하게 되어, 모델을 바꿀 때 조각 id까지 바뀔 수 있다. 피하려면 창 크기를 보수적인 공백 토큰 수(예: 160)로 정하고 토크나이저는 검사에만 쓴다.

## 출처

- fastembed 지원 모델: https://qdrant.github.io/fastembed/examples/Supported_Models/ — 다국어 dense 기본 목록에 bge-m3, gte-multilingual, arctic-m-v2.0이 없고, 희소 모델은 bm25, bm42, 영어 SPLADE뿐이다.
- KURE-v1: https://huggingface.co/nlpai-lab/KURE-v1 — bge-m3 기반 한국어 미세조정, MIT. 한국어 검색 평균표에서 KURE-v1 > bge-m3 > arctic-l-v2.0 > e5-large > jina-v3 > gte-multilingual-base > e5-base 순이다.
- gte-multilingual-base: https://huggingface.co/Alibaba-NLP/gte-multilingual-base — 약 305M, 768d 가변, 8192 토큰, Apache-2.0, 희소 가중치도 낼 수 있으나 `trust_remote_code`가 필요하다.
- snowflake-arctic-embed-m-v2.0: https://huggingface.co/Snowflake/snowflake-arctic-embed-m-v2.0 — Apache-2.0, ONNX 태그 있음. 파라미터와 한국어 점수는 페이지에서 확인하지 못했다.
- 기존 조사: `docs/specs/2026-11-04-embedding-model-selection/research/model-candidates.md`, `measurement-and-data.md`.
