# 세션 공통 형식과 임베딩 방식 조사

조사일: 2026-11-06. 질문7(공통 세션 형식), 질문8(임베딩 방식)에 답하기 위한 조사다. 앞선 조사 `research/session-embedding.md`(이하 "앞 조사")와 spec §4.2, §9.1을 전제로 한다. 원본 jsonl은 `python3 -I` 스크립트로 레코드 종류와 키 이름만 셌고 내용은 읽지 않았다. 스크립트는 저장소에 넣지 않았다. 확인하지 못한 내용은 "추정"으로 표시했다.

## 1. 원본에서 새로 확인한 구조

앞 조사 발견1~3에 더해, 공통 형식을 정하는 데 필요한 필드를 확인했다(Claude Code 3개 파일, Codex 3개 파일).

- 발견5. Claude Code user 레코드에 `turnOrigin`(`human`, `task_notification`, `peer`, `sdk`)과 `origin.kind`가 있다. 사이드체인·메타·도구 결과를 뺀 user 레코드 4,116개 중 3,906개(95%)에 이 필드가 있고, 그중 2,462개가 `human`이다. 필드가 없는 210개(옛 버전 기록으로 추정)는 앞 조사의 "`<`로 시작하지 않음" 규칙으로 판별해야 한다. 그래서 사람 턴 판별은 렌더된 md 텍스트가 아니라 adapter가 원본 필드로 해야 정확하다. `promptSource`(`typed`, `queued`, `sdk`, `system`, `suggestion_accepted`)도 있다.
- 발견6. Claude Code `tool_use.input` 키는 도구마다 고정이다. `Edit`/`Write`/`Read`는 `file_path`, `Bash`는 `command`·`description`, `WebFetch`는 `url`, `WebSearch`/`ToolSearch`는 `query`, `Agent`는 `subagent_type`·`description`·`prompt`. 그래서 "건드린 파일", "실행한 명령"은 LLM 없이 결정적으로 뽑을 수 있다.
- 발견7. 도구 결과의 성공 여부: user 레코드의 `tool_result.is_error`(한 파일에서 487건 중 10건 true)와 `toolUseResult`(`interrupted`, `returnCodeInterpretation`, `filePath`, `bashEditDiff` 등). 결과 본문 없이도 오류 여부와 오류 대상은 남길 수 있다.
- 발견8. Claude Code 기타: `system.subtype`(`compact_boundary`, `turn_duration`, `stop_hook_summary`, `away_summary`, `local_command`), `attachment.type`(`edited_text_file` 77건 등, 대부분 `total_tokens_reminder`·`deferred_tools_record` 같은 잡음), `ai-title`(Claude Code가 만든 세션 제목), `continued-in`(`continuedInSessionId`, 이어진 세션), 서브에이전트 `.meta.json`의 `agentType`·`description`·`toolUseId`(본 세션의 Agent 호출과 연결).
- 발견9. Codex `event_msg:item_completed`의 `item.type`이 정리된 구조를 준다: `UserMessage`, `AgentMessage`, `CommandExecution`(`command`, `cwd`, `exit_code`, `status` completed/failed, `duration`), `FileChange`(`changes`가 경로를 키로 한 dict, 값은 `type`·`unified_diff`·`move_path`), `McpToolCall`(`server`, `tool`, `status`), `SubAgentActivity`(`agent_thread_id`), `ContextCompaction`, `Plan`. `response_item`보다 이쪽이 adapter 입력으로 쉽다(추정: 모든 Codex 버전에 있는지 확인 못함). `session_meta`에는 `git.branch`·`commit_hash`, `parent_thread_id`가 있다. `turn_id`와 `task_started`/`task_complete`/`turn_aborted`가 교환 경계와 결과를 준다.
- 발견10. 규모: 이 Mac의 Claude Code 본 에이전트 사람 턴은 약 2,500개다(위 2,462 + 휴리스틱 57). 즉 본 대화 교환이 약 2.5k개다. Codex는 3개 파일에 `UserMessage` 43개라 전체 1~2k개로 추정한다. 서브에이전트 교환은 세지 않았다.

## 2. 공통 형식 비교 (질문1)

| 기준 | A. markdown (`vault-session/v1`, 지금) | B. 정규화 JSONL (턴 또는 교환당 한 줄) | C. markdown + 구조화 메타(교환 제목에 id, 숨은 메타 줄) |
|---|---|---|---|
| Vault/Obsidian에서 읽기 | 좋음. 단 블록 79%가 `Tools:` 한 줄(앞 조사 발견4) | 나쁨. 긴 JSON 한 줄 | 좋음. 도구 전용 턴을 앞 답의 행동 목록으로 접음 |
| 추가만 하는 성장 | 파트 파일 단위로 됨 (`session_capture.py:482-524`) | 줄 추가로 자연스러움 | 파트 파일 단위로 됨 |
| 안정 id | frontmatter의 첫/끝 uuid만 (`session_capture.py:545-560`) | 레코드마다 uuid | 교환·턴 제목에 uuid 앞 8자, 메타 줄에 전체 uuid |
| 회상에 필요한 정보 | 본문, 도구 이름만 | 본문, 도구 대상, 오류, 결과까지 무손실에 가까움 | B와 같은 필드를 요약 줄로 |
| 비밀값 가림 | 본문에만 (`session_capture.py:277`, `537`) | 필드별로 가능(명령, 경로, 오류 줄) | 필드별로 가능 |
| 크기 | 22파트 5.1MB | 본문 + 도구 대상 + 오류 첫 줄: 원본의 약 5~8%(추정) | B보다 약간 작음(키 이름 없음) |
| 파싱 | 제목 정규식. 사람 턴 판별이 `<` 휴리스틱 | `json.loads` 한 줄씩, 가장 쉬움 | 제목 정규식 + 메타 줄 key=value |
| 결정적 위치 | markdown 줄 범위 (`markdown_parser.py:418-428`) | JSON 줄 번호. 사람이 열면 읽기 어려움 | markdown 줄 범위, 교환 id로 범위 확정 |
| git diff | 새 파일만 추가, 좋음 | 줄 추가, 하지만 한 줄이 길어 리뷰 어려움 | 새 파일만 추가, 좋음 |
| vg 색인 | 지금 리더 그대로 | `.jsonl` 리더가 없음 (`document_readers.py` 등록부). FTS가 JSON 문법을 색인 | 지금 markdown 리더 그대로 |

### 결정7. 두 층으로 나눈다

- 기계용 정본: adapter가 원본 jsonl을 정규화 JSONL(`vg-session-jsonl/1`)로 바꾼다. Vault 밖 export 폴더에 둔다. 손실이 가장 적고 파싱이 쉬워 다시 렌더링하는 기준이 된다.
- 사람용·검색용: 정규화 JSONL에서 결정적으로 렌더링한 markdown(`vault-session/v2`, 형식 C)을 Vault에 넣는다. 읽기, git diff, 줄 위치, 지금 FTS·조각기 경로가 모두 markdown을 전제로 하기 때문이다.
- A를 그대로 두지 않는 이유: 사람 턴 판별(발견5), 도구 대상·오류(발견6·7), 턴 uuid가 md에 없어 조각기가 휴리스틱에 의존한다(앞 조사 위험2).
- B를 Vault 검색 대상으로 쓰지 않는 이유: Obsidian에서 읽을 수 없고, 새 리더와 새 위치 형식이 필요하며, FTS에 JSON 키가 섞인다.

### 2.1 정규화 JSONL 스키마 `vg-session-jsonl/1`

한 파일 = 세션 하나. 첫 줄은 `session`, 이후 `exchange`와 `turn`이 교환 순서대로 온다. 모든 줄에 `schema`, `kind`가 있다.

| kind | 필드 |
|---|---|
| session | `session_id`, `agent`(`claude-code`/`codex`), `agent_version`, `adapter`(`claude-code/1`), `project`, `cwd`, `git_branch`, `git_commit`, `parent_session_id`(Claude `continued-in`, Codex `parent_thread_id`), `title`(`ai-title`, 생성 텍스트 표시), `started_at`, `ended_at`, `source_paths`(export 안 상대 경로), `source_sha256` |
| exchange | `exchange_id`(= 첫 사람 턴 uuid, Codex는 `turn_id`), `seq`, `agent_scope`(`main` 또는 `subagent:<agent_id>`), `subagent_type`, `parent_tool_use_id`(서브에이전트를 부른 Agent 호출), `started_at`, `ended_at`, `closed`(다음 사람 턴이나 세션 끝이 왔는가), `prompt_source`, `tools`(이름→횟수), `files_touched`(경로 목록, 이름순), `commands`(앞 160자, 가림 후), `errors`(개수), `outcome` |
| turn | `turn_id`(uuid), `parent_id`, `exchange_id`, `role`(`user`/`assistant`), `turn_kind`(`human`, `assistant_text`, `tool_only`, `notification`, `meta`, `compact_summary`), `at`, `agent_id`, `sidechain`, `text`(가림 후), `actions`: [{`tool`, `call_id`, `target`(경로·명령 앞부분·url·질의), `ok`, `error_head`(오류 첫 줄 200자, 가림 후)}] |

- `outcome`은 결정적 열거값이다: `answered`(마지막 턴이 assistant 텍스트), `tool_error_unresolved`(마지막 행동이 실패), `interrupted`(`toolUseResult.interrupted`, Codex `turn_aborted`), `open`(닫히지 않음). LLM 판단을 넣지 않는다.
- 넣지 않는 것: tool_result 본문, thinking/reasoning(비어 있거나 암호화, 앞 조사 발견1·3), attachment, api-request, token 기록.
- 원본 필드 대응

| 공통 필드 | Claude Code | Codex |
|---|---|---|
| 사람 턴 | `type:user`, `turnOrigin:human` 또는 `origin.kind:human`, 없으면 `<` 휴리스틱, `isMeta`·`tool_result` 제외 | `item_completed` `UserMessage`(또는 `response_item:message` role user, `developer` 제외) |
| assistant 텍스트 | `type:assistant` `text` 블록 | `AgentMessage` |
| 행동 | `tool_use`(name, input의 `file_path`/`command`/`url`/`query`) | `CommandExecution.command`, `FileChange.changes` 키, `McpToolCall.server/tool` |
| 성공 여부 | `tool_result.is_error`, `toolUseResult.interrupted` | `exit_code`, `status` |
| 서브에이전트 | `subagents/agent-<id>.jsonl`, `.meta.json` `agentType`·`toolUseId` | `SubAgentActivity.agent_thread_id`, `spawn_agent` 호출 |
| 압축 요약 | `isCompactSummary:true` | `compacted.message`(추정: 요약 본문) |
| 순서 | `parentUuid`, `timestamp` | `ordinal`, `turn_id` |

### 2.2 markdown `vault-session/v2` 렌더링

```
---
schema: vault-session/v2
renderer: vg-session-md/2.0
source_schema: vg-session-jsonl/1
agent: claude-code
session_id: ...
part: 3
first_exchange_id: ...
last_exchange_id: ...
(v1의 project, cwd, collected_at, trigger, redactions, body_sha256 유지)
---

## X 2026-11-05 10:02 · 1a2b3c4d
<!-- vg:exchange id=<uuid> scope=main tools=Bash:5,Edit:2 errors=1 outcome=answered -->

### user · 10:02 · 1a2b3c4d
(사람 메시지)

### assistant · 10:03 · 9f8e7d6c
(답 본문)

- Edit `src/a.py`
- Bash `pytest -q` → 실패: (오류 첫 줄)
```

- 교환이 `##`, 턴이 `###`이다. 도구 전용 assistant 턴은 바로 앞 텍스트 턴 아래 행동 목록 한 줄로 접는다. 블록 수가 앞 조사 기준 약 79% 줄어든다.
- `<!-- vg:exchange ... -->`는 Obsidian 읽기 화면에서 보이지 않고, 조각기는 이 줄로 교환 id와 메타를 읽는다. 조각기는 이 줄을 창 본문과 임베딩 입력에서 뺀다.
- 서브에이전트 교환은 본 대화 교환 뒤가 아니라 파일 끝 `## Subagent <agent_id> · <type>` 절로 모은다. 본 대화를 읽는 흐름을 끊지 않는다.
- 파트 파일에는 닫힌 교환만 쓴다. 열린 마지막 교환은 다음 캡처나 세션 끝에서 쓴다. 그래서 v1의 "이어진 교환"(spec §4.2.3-2)이 사라지고 교환이 파일 사이에 걸치지 않는다.

### 2.3 버전 규칙

- `schema: vault-session/vN`: 조각기가 읽는 구조가 바뀔 때만 올린다(제목 단계, 메타 줄 문법). 조각기는 이 값으로 고른다(spec §4.2.2).
- `renderer: vg-session-md/2.M`: 필드 추가처럼 v2 조각기가 그대로 읽는 변경이면 M만 올린다.
- `vg-session-jsonl/N`: 정본 스키마. 필드 추가는 그대로, 의미 변경은 N을 올린다. 줄마다 `schema`를 넣어 옛 export도 읽는다.
- adapter 버전(`claude-code/1`)은 session 줄에 남긴다. 원본 형식이 바뀌면 adapter만 올린다.
- 조각 id는 교환 id(uuid)로 만들어 렌더러 버전과 무관하게 한다(4절).

## 3. 산출물 위치 (질문2)

| 산출물 | 위치 | 누가 쓰나 | 성격 |
|---|---|---|---|
| 원본 export | 사용자 지정 경로(Vault 밖), `raw/<agent>/<session_id>/`에 jsonl과 subagents, meta를 그대로 복사 | vg export | 원본 사본. 비밀값 가림 없음 |
| 정규화 JSONL | 같은 export 경로 `normalized/<agent>/<session_id>.jsonl` | vg adapter | 원본에서 다시 만들 수 있음. 가림 적용 |
| 세션 md v2 | Vault `raw/sessions/<agent>/...` | Vault 도구 | 검색 대상. 한 번 쓰면 바뀌지 않음 |
| 파생 색인(조각, FTS, 벡터) | Graph Home 세대 | vg 색인 | 지우고 다시 만듦 |
| LLM 파생 텍스트(요약, 예상 질문, 맥락 줄) | Graph Home, 세대 밖 캐시(임베딩 캐시와 같은 위치) | vg 색인(선택) | 키 = 교환 본문 해시 + 모델 + 프롬프트 버전. 다시 만들 수 있으나 비쌈 |

- 경계: vg는 Vault 파일을 직접 쓰지 않는다(`AGENTS.md:3-20`). 지금 Vault 도구 중 `ingest-source`는 이미 `raw/` 아래 있는 파일만 받고 세션 경로는 거부한다(`vault-builder/tools/wiki/lib/ingest.py:34-45`). `sessions capture`는 원본 jsonl 경로만 받는다(`vault-builder/tools/wiki/cli.py:209-224`). 그래서 md v2를 넣으려면 vault-builder에 새 입력이 필요하다. 예: `sessions capture --normalized <jsonl>`(Vault가 렌더링) 또는 `sessions import <md>`(vg가 렌더링, Vault가 형식·가림·파트 번호를 검사).
- 권장: Vault가 렌더링하는 `--normalized` 쪽. md 형식의 주인이 Vault 도구에 남고, vg는 "언제, 어떤 정규화 파일"만 정한다. 지금 capture 경계(`AGENTS.md:15-17`)와 같은 모양이다. §9.1 질문3(L1~L3 관리를 vg로)과 충돌하는지는 spec에서 정해야 한다.
- 원본 export는 가림이 없으므로 export 경로가 git 저장소나 클라우드 동기화 폴더 안이면 경고하고, 파일 권한을 사용자 전용으로 둔다.

## 4. 임베딩 방식 (질문3)

### 4.1 방법 비교

| 방법 | LLM 필요 | 근거 | 결정성 | 비용(교환 1k개, 추정) |
|---|---|---|---|---|
| 교환 단위 창 + 머리말(질문 앞 200자) | 아니오 | 앞 조사 4절. 질문과 답이 한 조각 | 결정적 | 임베딩만 |
| 하이브리드 FTS + dense, RRF | 아니오 | 이미 있음: `candidate_ranking.py:12-55`, k=60, keyword/vector 가중 1.0 | 결정적 | 없음 |
| 부모-자식(작게 찾고 교환으로 돌려줌) | 아니오 | 창으로 찾고 결과에는 교환 전체 줄 범위를 보여 줌 | 결정적 | 없음 |
| 결정적 메타 필드(파일, 명령, 도구, 오류) FTS 색인 | 아니오 | 발견6·7. "그 파일 고친 세션" 질의 | 결정적 | 없음 |
| late chunking | 아니오(긴 문맥 임베딩 모델 필요) | 문서 전체를 한 번에 인코딩한 뒤 토큰 벡터를 조각별로 평균. e5-small 512 토큰에서는 의미 없음 | 결정적 | 8k 모델에서 문서당 1회. fastembed가 토큰 벡터를 주는지 확인 못함 |
| multi-vector(ColBERT류) | 아니오 | 토큰별 벡터, 정밀하나 저장량이 수십 배 | 결정적 | Chroma 백엔드 변경 필요(추정) |
| 맥락 검색(조각마다 50~100토큰 맥락 생성) | 예 | Anthropic: 상위 20 실패율 35% 감소, BM25까지 49%, 재순위 67% | 같은 모델·프롬프트·캐시면 재현 | 창 2~3k개 × 약 3초 = 2~3시간 |
| 교환 요약 + 원문 이중 색인 | 예 | 질문형 회상에 강함(앞 조사 4절) | 위와 같음 | 교환당 약 4초 → 약 70분 |
| doc2query(교환당 예상 질문 3개) | 예 | 질문과 문서의 어휘 차이를 메움. 한국어 질의와 영어 코드 대화 사이에 특히 유효(추정) | 위와 같음 | 요약과 한 호출로 묶으면 추가 비용 작음 |

- 비용 가정(추정, 측정 안 함): Mac Studio에서 MLX 4bit 7~8B 모델, 입력 처리 초당 약 500~1,000토큰, 생성 초당 약 40~60토큰. 교환당 입력 약 1.5k토큰, 출력 약 100토큰이면 3~4초다. 3B급이면 절반쯤이다. 지금 규모(교환 약 2.5k + Codex 1~2k)는 처음 한 번 약 3~5시간, 이후에는 새 교환만 처리한다.
- 교환 머리말(세션, 프로젝트, 질문 앞부분)이 이미 맥락 검색이 LLM으로 만드는 "이 조각이 어디서 왔나"의 상당 부분을 결정적으로 준다. 그래서 LLM 맥락 줄의 추가 이득은 일반 문서보다 작다(추정, 측정 필요).

### 결정8. 단계별 적용

- 1단계, LLM 없음(기본): `session-exchange-v2` 조각기. 교환 안 무겹침 창, 머리말 `Session/Project/Question`, 메타 줄의 파일·명령·도구·오류를 FTS `frontmatter` 열(`sqlite_keyword_index.py:38-47`)에 넣고 임베딩 입력에서는 뺀다. 검색 결과는 창으로 찾고, 같은 교환의 창이 여러 개 맞으면 하나로 묶어 교환 줄 범위를 돌려준다. 결정적 검색의 기준선이 된다.
- 2단계, 로컬 LM(선택, 설정으로 켬): 교환마다 한 번 호출해 한국어 요약 1~3문장과 예상 질문 3개를 만든다. 둘을 `derived` 조각으로 따로 색인한다(FTS 별도 표 또는 `source_role: derived`, 별도 벡터). 맥락 줄은 2단계 측정에서 이득이 확인될 때만 더한다.
- 3단계, 보류: late chunking, multi-vector. 임베딩 모델 재선정(§9.1 질문5) 뒤에 다시 본다.

### 결정9. 결정적 검색을 지키는 규칙

1. LLM 텍스트는 원문 창을 바꾸지 않는다. 원문 창의 `text`, 조각 id, `source_locators`, 임베딩 입력은 2단계를 켜도 바이트 단위로 같다.
2. `derived` 조각은 위치로 교환 전체 줄 범위를 가지되, 인용 본문으로 쓰지 않는다. 결과에서 근거를 열면 원문 교환이 열린다.
3. RRF에 신호 종류 `derived`를 더하고 가중치를 keyword/vector보다 낮게 둔다(시작값 0.5). `derived` 신호는 교환의 첫 창 조각 id로 합쳐 같은 교환이 두 번 나오지 않게 한다.
4. `vg search --no-derived`(또는 결정성 시험 모드)에서는 `derived`를 빼고, 측정1과 결정성 시험은 이 모드로 돌린다. 2단계 결과는 캐시가 같으면 재현되지만, 캐시를 지우면 바뀔 수 있으므로 결정성 계약에서 뺀다.
5. LLM 산출물은 Vault에 쓰지 않는다. 사람이 쓸 만하다고 판단한 요약은 `remember`(publish-draft) 경로로만 Vault에 들어간다.

## 5. 평가 (질문4)

- 측정1 벤치마크(`tests/benchmarks/measure_vault_search_parity.py:8-10`, `161`)는 상위 5개 결과 문서 경로로 판정한다. 세션은 한 파트 파일에 교환이 여러 개라 "맞는 파일, 틀린 교환"도 적중으로 센다. 회귀 확인용으로만 쓰고, 세션 품질 판정에는 부족하다.
- 세션 질의 세트를 따로 만든다(spec A-7). 형식: `{"id", "question", "expected_exchanges": [exchange_id], "kind"}`. `kind`는 `decision`(왜 그렇게 정했나), `how`(어떻게 고쳤나), `file`(어느 세션에서 그 파일을 바꿨나), `error`(그 오류를 어떻게 풀었나), `paraphrase`(본문과 다른 말로 묻기). 한국어 질의 40~60개, 사람이 기대 교환을 고른다. 세트는 개인 세션 내용을 담으므로 저장소 밖(Graph Home 또는 사용자 경로)에 둔다.
- 지표: 교환 단위 recall@5, recall@10, MRR. 같은 교환의 여러 창은 한 번만 센다. 보조로 `kind`별 recall, 결과 상위 10개 중 서브에이전트 교환 비율, 재색인 시간·최대 RSS(spec §4.2.6).
- 비교 단계: (a) v1 md + `document-block-window-v2`(지금), (b) v1 md + `session-exchange-v1`, (c) v2 md + `session-exchange-v2` 1단계, (d) (c) + 2단계 요약·질문, (e) (d) + 맥락 줄. 앞 단계보다 recall@5가 오르지 않는 단계는 넣지 않는다.
- 결정성 확인: 같은 Vault를 두 번 색인해 조각 id, 창 본문, 위치, `--no-derived` 결과 순서가 같은지 본다.

## 6. 이전 경로 (질문5)

1. vault-builder가 `vg-session-jsonl/1` 입력과 `vault-session/v2` 렌더러를 받는다. 기존 v1 파일은 그대로 둔다(바뀌지 않는 파일이라는 약속, `session_capture.py:482-524`).
2. vg export와 Claude Code adapter를 만든다. 아직 원본이 남아 있는 세션(Claude Code는 기본 30일 보관, spec 질문1 배경)은 export 후 v2로 다시 렌더링할 수 있다.
3. 같은 세션의 v1과 v2가 둘 다 있으면 검색 결과가 중복된다. 선택지: (a) Vault 도구가 v2를 쓴 세션의 v1 파트를 `raw/sessions/.../superseded/`로 옮김(Vault 도구 작업, vg는 하지 않음), (b) vg 조각기가 frontmatter `session_id`가 같은 v2 파일이 있으면 v1 파일을 색인에서 뺌. (b)는 Vault 파일을 건드리지 않아 경계에 맞지만, v1에만 있던 교환(원본이 이미 지워진 구간)을 잃지 않도록 교환 id 범위로 겹치는 부분만 빼야 한다. v1에는 턴 uuid가 첫/끝만 있어 정확히 겹침을 판단하기 어렵다(추정: timestamp 범위로 대체).
4. 원본이 없는 옛 v1 파일은 `session-exchange-v1`(spec §4.2.3)로 계속 색인한다. `document-block-window-v2`는 세션 파일에 더 이상 쓰지 않는다.
5. 조각 id가 바뀌어 전환 전 세션 근거 id는 열리지 않는다(앞 조사 위험1, spec §4.2.5). wiki 페이지가 `raw/sessions/<파일>` 경로로 건 근거는 파일이 남으므로 유지된다. 3(a)로 파일을 옮기면 이 경로 근거도 끊기므로 3(b)를 권한다.

### 위험

- 위험5. 원본 export에 비밀값이 그대로 남는다. export 경로가 동기화 폴더면 밖으로 나간다.
- 위험6. Claude Code·Codex 원본 형식은 공개 계약이 아니다. `turnOrigin`, `item_completed` 같은 필드가 바뀌면 adapter가 사람 턴을 잘못 고른다. adapter 버전과 원본 `version`/`cli_version`별 시험 파일이 필요하다.
- 위험7. 2단계 요약이 원문에 없는 내용을 만들 수 있다. 결정9-2로 인용에서는 막지만, 검색 순위에는 영향을 준다.
- 위험8. md v2의 숨은 메타 줄을 사람이 Obsidian에서 고치면 `body_sha256` 검사가 실패한다. 이는 v1과 같은 동작이다.

## 출처

- Anthropic, Contextual Retrieval (2024): https://www.anthropic.com/news/contextual-retrieval — 문서 전체와 조각을 LLM에 주고 조각마다 50~100토큰 맥락을 만들어 임베딩과 BM25 앞에 붙인다. 상위 20 검색 실패율(기준 5.7%)이 맥락 임베딩으로 35%, BM25를 더해 49%, 재순위까지 67% 줄었다. 프롬프트 캐시를 쓰면 문서 토큰 100만 개당 약 1.02달러다.
- Günther et al., Late Chunking (2024): https://arxiv.org/abs/2409.04701 — 긴 문맥 임베딩 모델로 문서 전체를 먼저 인코딩하고, 조각 경계에 맞춰 토큰 벡터를 평균해 조각 벡터를 만든다. 조각이 문서 맥락을 담는다(기억 기준, 이번에 페이지 재확인 안 함).
- Nogueira et al., Document Expansion by Query Prediction (doc2query, 2019): https://arxiv.org/abs/1904.08375 — 문서마다 예상 질문을 생성해 문서에 붙여 색인하면 BM25 검색이 좋아진다(기억 기준).
- Cormack et al., Reciprocal Rank Fusion (SIGIR 2009): https://dl.acm.org/doi/10.1145/1571941.1572114 — 여러 순위 목록을 `1/(k+rank)` 합으로 합친다. vg는 k=60을 이미 쓴다(`candidate_ranking.py:12`).
- Khattab & Zaharia, ColBERT (2020): https://arxiv.org/abs/2004.12832 — 토큰마다 벡터를 두고 질의 토큰별 최대 유사도를 더하는 multi-vector 방식(기억 기준).
- 코드: `$HOME/workspace/vault-builder/tools/wiki/lib/session_capture.py:258-277`(가림), `527-570`(v1 렌더링), `src/vault_graph/storage/local/sqlite_keyword_index.py:38-47`(FTS 열), `src/vault_graph/retrieval/search/candidate_ranking.py:12-55`(RRF), `src/vault_graph/project/code/source_evidence_reader.py:90`(`vg-source://`는 저장소 코드 파일용이고 Vault 문서 위치는 경로와 줄 범위다).
