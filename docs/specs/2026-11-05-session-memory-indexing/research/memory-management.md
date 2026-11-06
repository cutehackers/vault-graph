# Research: L1→L2→L3 기억 관리 방식 (질문7, 질문8)

작성 2026-11-06. vault-graph 코드는 `abc77e7` 기준, 다른 저장소는 `vault-builder:` 접두어를 붙였다(`vault-builder` `1cc04a8` v3.0.0). 사람 홈 폴더는 `$HOME`으로 적는다. 코드나 원문으로 확인하지 못한 내용은 "추정"으로 표시했다.

전제(spec §9.1): L1·L2·L3 관리는 vg가 맡고, Vault는 저장소(ingest, update, query와 검증)다. `share_untagged`는 Vault별 설정이다. 임베딩 모델은 범위 밖이다. 앞선 조사 `research/memory-layers.md`의 부품·발견 코드를 그대로 쓴다.

## 1. 지금 쓸 수 있는 재료

| 코드 | 사실 | 근거 |
|---|---|---|
| 재료1 | L1은 Claude Code가 쓴다. 저장소마다 폴더 하나, `MEMORY.md`는 한 줄짜리 목록이고 앞 200줄 또는 25KB만 세션 시작 때 읽힌다. 주제 파일은 필요할 때 읽는다. L1 파일은 transcript 정리 주기에서 빠진다 | https://code.claude.com/docs/en/memory (auto memory 절) |
| 재료2 | Vault `ingest-source`는 `raw/` 안의 파일만 받는다. 세션 파일은 source page를 만들지 않고 `raw/sessions/` 경로를 claim 근거로 바로 인용한다 | `vault-builder:tools/wiki/lib/ingest.py:24-53` |
| 재료3 | Vault 규칙: 같은 출처의 새 진술은 모순이 아니라 대체다. 옛 claim 행을 `superseded`로 두고 새 행을 날짜와 함께 더한다. 독립 출처끼리 다를 때만 `contested`와 검토 항목을 쓴다 | `vault-builder:docs/agent/OPERATING-SCHEMA.md:192-200` |
| 재료4 | 기억 frontmatter: `memory_schema: vault-memory/v1`, `pin`, `memory_kind`(rule, correction, decision, preference), `status: retired`와 `retired_reason`·`retired_at`. 페이지 공통 `confidence`(low·medium·high) | `vault-builder:tools/wiki/lib/memory_fields.py:1-71`, `OPERATING-SCHEMA.md:321-356` |
| 재료5 | vg 쓰기: `remember`는 `project`·`tags` 없이 `confidence: medium` draft를 만든다. `retire_memory`에 대체 페이지를 주면 `deprecated`와 `superseded_by`를 쓴다 | `src/vault_graph/operation/memory/memory_drafts.py:33-72`, `:106-128` |
| 재료6 | vg 회상은 사용 기록에 `injected`와 `fetched` 이벤트를 남긴다. 한 기억이 주입만 되고 한 번도 열리지 않았는지 셀 수 있다 | `src/vault_graph/context/pack/recall.py:140-155`, `:216-223` |
| 재료7 | vg에는 MCP prompt 등록부가 있다. 에이전트에게 정해진 작업 순서를 주는 통로로 쓸 수 있다 | `src/vault_graph/interface/mcp/mcp_prompts.py:87-120` |
| 재료8 | Vault L3 생성은 `project`가 있는 페이지만, 교정은 `tags`로 고른다. 1,500토큰, 섹션당 750토큰 | `vault-builder:tools/wiki/lib/maps.py:55-56`, `:255-305` |
| 재료9 | Vault `memory-cleanup` 스킬은 L1을 `raw/imports/claude-memory/<project>--<stem>--<sha8>.md`로 복사하고 ingest, draft, publish 한다. 상태 파일 없이 `raw_sha256`로 반영 여부를 판정한다 | `vault-builder:.agents/skills/memory-cleanup/SKILL.md:24-46` |

## 2. 선행 사례와 vg에 주는 뜻 (질문7)

| 코드 | 사례 | 핵심 (내 말로 요약) | vg에 주는 뜻 |
|---|---|---|---|
| 사례1 | Claude Code auto memory, https://code.claude.com/docs/en/memory | 에이전트가 세션 중에 스스로 쓰는 짧은 노트. 목록 파일만 항상 읽고 상세는 필요할 때 읽는다. 기계 한 대에만 있다 | L1은 "빠른 쓰기 버퍼"로 두고 vg는 읽기만 한다. 세션 시작 주입은 목록처럼 짧게, 상세는 검색으로 미룬다 |
| 사례2 | Anthropic memory tool, https://platform.claude.com/docs/en/agents-and-tools/tool-use/memory-tool | 저장은 클라이언트 쪽. 작업 전에 기억 폴더를 먼저 보게 하고, 오래 안 읽힌 파일은 주기적으로 지우라고 권한다. 여러 세션 개발에서는 진행 기록과 기능 목록을 정해진 파일로 두고 세션 끝마다 갱신하는 방식을 권한다 | 오래 안 쓰인 기억을 정리 대상으로 삼는 근거(재료6). L3에 "진행 중인 일" 섹션을 두는 근거 |
| 사례3 | MemGPT, https://arxiv.org/abs/2310.08560 / Letta, https://docs.letta.com/ | 문맥 안 core memory, 검색하는 대화 기록, 장기 저장의 세 층. 층 이동은 에이전트 도구 호출. Letta 현재 문서는 "dreaming"(백그라운드 하위 에이전트가 최근 대화를 검토해 기억을 정리)을 단계 수나 compaction 시점에 돌린다 | L1≈core, `raw/sessions/`≈대화 기록, L2≈장기. 정리는 대화 밖 별도 실행이 품질에 좋다. vg는 LLM이 없으므로 "정리 작업 꾸러미"를 만들고 에이전트가 따로 처리한다 |
| 사례4 | mem0, https://arxiv.org/abs/2504.19413 | 새 대화에서 후보 사실을 뽑고, 후보마다 비슷한 기존 기억 10개를 찾아 LLM이 ADD·UPDATE·DELETE·NOOP 중 하나를 고른다. 전체 문맥 대비 지연·토큰 90% 이상 절감(LoCoMo) | 판단 단위는 "후보 1개 + 비슷한 기존 페이지 k개". 네 동작을 `remember`·`update_memory`·`retire_memory`·건너뜀에 대응한다. 비슷한 페이지 찾기는 vg가 결정적으로 한다 |
| 사례5 | Zep/Graphiti, https://arxiv.org/abs/2501.13956, https://github.com/getzep/graphiti | 사실마다 사건 시간(유효 시작·끝)과 시스템 시간(기록·만료)을 따로 둔다. 모순되면 지우지 않고 옛 사실의 유효 끝을 새 사실의 시작으로 닫는다. 원문 episode가 출처로 남는다. 요약(community)은 그래프에서 다시 만드는 파생물이다 | Vault의 claim 행 대체(재료3)가 같은 모델이다. 사건 시간은 근거 세션 날짜, 시스템 시간은 Vault git 기록. L3 목록은 파생물로 둔다 |
| 사례6 | A-MEM, https://arxiv.org/abs/2502.12110 | 새 노트에 설명·키워드·태그를 붙이고, 비슷한 기존 노트와 링크를 만들며, 새 노트가 옛 노트의 설명을 고치게 한다 | 쓰기 때 `related` 링크를 채우게 한다. 옛 노트 자동 수정은 검증 경로를 우회하므로 따르지 않는다 |
| 사례7 | Generative Agents, https://arxiv.org/abs/2304.03442 | 회상 점수 = 최근성(마지막 회상 뒤 지수 감쇠 0.995/시간) + 중요도(생성 때 LLM이 1~10) + 관련도(임베딩 유사도). 최근 사건 중요도 합이 150을 넘으면 reflection으로 상위 요약을 만든다 | 최근성은 "마지막으로 열린 때" 기준이 좋다(재료6). 요약(L3)은 일정 양이 쌓일 때 다시 만든다 |
| 사례8 | LangMem, https://langchain-ai.github.io/langmem/concepts/conceptual_guide/ | 의미·일화·절차 기억을 나눈다. 대화 중 즉시 쓰기(지연 증가)와 대화 뒤 백그라운드 쓰기(지연 없음, 더 깊은 분석)를 구분한다. 여러 레코드 묶음(collection)과 현재 상태 한 문서(profile)를 구분한다 | L2 페이지는 collection, L3 brief는 profile이다. 사용자가 직접 말한 교정은 즉시, 세션 증류는 대화 뒤에 한다 |
| 사례9 | Cognee, https://docs.cognee.ai/core-concepts/overview | 데이터 추가 → 그래프화 → 기존 기억 보강(세션 기억을 장기 그래프로 옮기는 단계 포함) → 검색의 파이프라인. 단계 세부는 이번에 확인하지 못했다(추정) | "세션 → 장기" 이동을 별도 단계로 두는 구성이 일반적이다 |
| 사례10 | LongMemEval, https://arxiv.org/abs/2410.10813 | 정보 추출, 여러 세션 추론, 시간 추론, 지식 갱신, 답하지 않기 다섯 능력을 잰다. 세션을 작은 단위로 나눠 저장, 사실로 키 확장, 시간 조건으로 검색 범위 좁히기가 효과가 있었다 | 평가 축 다섯 개를 그대로 빌린다. 세션 조각(spec §4.2)에 "뽑힌 사실"을 검색 키로 더하는 방식이 근거를 얻는다 |
| 사례11 | LoCoMo, https://arxiv.org/abs/2402.17753 | 평균 300턴, 최대 35세션 대화. 긴 대화의 시간·인과 추적이 약하다 | 시간 질문("X 전에 뭘 정했나")을 평가 세트에 넣는다 |
| 사례12 | MemoryAgentBench, https://arxiv.org/abs/2507.05257 (ICLR 2026) | 정확 검색, 실행 중 학습, 장거리 이해, 선택적 잊기(옛 사실을 새 사실로 바꾸기)를 잰다. 선택적 잊기는 모든 방식이 약했고 multi-hop에서 7%까지 떨어졌다 | 가장 약한 곳이 "대체된 기억을 안 쓰기"다. vg 평가의 1순위 지표로 둔다 |

종합: 품질을 가르는 것은 (1) 무엇을 쓸지 고르는 기준, (2) 쓰기 전 기존 기억과의 비교, (3) 지우지 않는 대체와 회상에서의 확실한 제외, (4) 쓰기와 정리를 대화 밖에서 하는 것이다. 사례4·5·12가 가장 직접적이다.

## 3. 제안: vg 기억 관리 방식 (질문7)

### 3.1 역할

| 코드 | 일 | 맡는 쪽 | 이유 |
|---|---|---|---|
| 역할1 | 후보 찾기, 비슷한 기존 페이지 찾기, 충돌 후보 표시, 정리 대상 점수, L3 목록 투영, 회상 | vg (결정적, LLM 없음) | 색인과 사용 기록을 가진 곳이 vg다. 원칙1을 지킨다 |
| 역할2 | 기억할 가치 판단, 문장 작성, ADD·UPDATE·RETIRE·건너뜀 결정, `basis` 결정 | 세션 안 에이전트(Claude) | 지금 쓸 수 있는 가장 강한 판단자다. 원칙1 그대로 |
| 역할3 | 검증, 저장, 검토 대기열, 원본 복사 | Vault 도구 | 전제 |
| 역할4 | 추론 기억 승인, 충돌 결정 | 사람 | 품질 우선 |

로컬 LM은 이번 설계에 넣지 않는다. 판단 품질은 세션 안 Claude가 작은 로컬 모델보다 높다(추정, 4B~8B급 모델 기준). 로컬 LM이 이득을 낼 수 있는 곳은 쌓인 `raw/sessions/`에서 "기억할 만한 교환"을 미리 거르는 일 하나다. 이것은 품질이 아니라 에이전트 토큰 비용을 줄인다. 3.9의 평가 세트에서 결정적 거르기보다 재현율이 분명히 높을 때만 선택 기능으로 더한다(4.3 규칙 문장 후보).

### 3.2 무엇을 잡는가

- 잡을 것(우선순위 순): 사용자 교정과 작업 규칙, 결정과 그 이유, 되돌린 시도와 실패 원인, 프로젝트 고유 사실(경로, 명령, 계약), 열린 일, 사용자 선호.
- 잡지 않을 것: 코드나 git 기록에서 다시 알 수 있는 것, 일회성 디버깅 출력, 비밀값.
- 쓰는 시점 두 가지(사례8):
  - 즉시: 사용자가 직접 말한 교정·규칙·결정. 에이전트가 세션 중 `remember`(`basis: stated`)로 쓴다. 지금과 같다.
  - 대화 뒤: L1 노트와 세션 원문 증류. 3.3의 정리 작업으로 한다.

### 3.3 추출과 증류: 정리 작업 꾸러미

vg가 결정적으로 "정리 작업 꾸러미"를 만들고, 에이전트가 항목마다 판단해 기존 쓰기 도구로 처리한다(사례3·4).

1. 후보 찾기(vg):
   - L1: 프로젝트 L1 폴더의 노트 중 sha256이 연결 Vault `raw/imports/claude-memory/` 문서의 `raw_sha256`과 같지 않은 것. 판정은 `memory-scan`과 같은 규칙(재료9).
   - 세션: 색인된 세션 조각 중 어떤 `wiki/` 페이지도 근거로 인용하지 않은 것. 교환 단위(spec §4.2.3 `session-exchange-v1`)로 묶는다. 결정적 거르기로 순서를 정한다: 사람 턴에 교정 신호가 있는 교환, 결정 단어가 있는 교환, 도구 실패 뒤 방향을 바꾼 교환을 앞에 둔다. 거르기 규칙은 추정이며 3.9 평가로 고친다.
2. 비교 재료 붙이기(vg): 후보마다 같은 프로젝트 범위에서 비슷한 기존 페이지 상위 k개(키워드+벡터, k=5 제안), 각 페이지의 status·`superseded_by`·근거 날짜.
3. 판단(에이전트): 후보마다 하나를 고른다.
   - 새 사실이면 `remember`.
   - 기존 페이지를 보강하거나 같은 출처의 새 진술이면 `update_memory`. 옛 claim은 대체로 남긴다(재료3).
   - 페이지 전체가 바뀌면 `retire_memory(replaced_by=...)`.
   - 가치 없으면 건너뜀. 건너뛴 후보는 꾸러미에 "검토함"으로 남겨 다시 올라오지 않게 한다(4.4 위험1).
4. `basis` 규칙: 근거 원문에 사용자 자신의 말이 있고 에이전트가 그 문장을 인용하면 `stated`, 나머지는 `inferred`(검토 대기열). 품질 우선이라 경계 사례는 `inferred`로 둔다.
5. 근거: L1은 Vault로 복사한 사본 경로, 세션은 `raw/sessions/...` 경로와 교환 위치.

시작 방법: 세션 시작 회상에 "정리 대기" 한 줄(spec D3)과 MCP prompt `curate_memory`(재료7). 사용자가 원할 때 "기억 정리해"로 시작한다. 훅 안에서는 하지 않는다(훅에는 LLM이 없고 시간 제한이 있다).

### 3.4 중복, 병합, 모순

- 쓰기 전 비교는 3.3의 2·3단계가 한다(사례4). 같은 sha256의 L1 노트는 다시 올리지 않는다.
- 이미 쌓인 중복은 Vault `merge scan`(`vault-builder:tools/wiki/lib/merge.py:29-63`)의 제목·별칭 비교에 더해, vg가 같은 프로젝트에서 임베딩 유사도가 높은 페이지 쌍을 정리 꾸러미에 "병합 후보"로 올린다. 병합 판단은 에이전트, 실행은 `update_memory` + `retire_memory(replaced_by)`.
- 모순: 같은 출처의 새 진술은 대체(재료3). 출처가 다르거나 선후가 불분명하면 `inferred`로 올려 사람이 고르게 한다. vg가 Vault `review create --type contradiction`을 직접 부르는 길은 만들지 않는다(쓰기 길을 늘리지 않음).

### 3.5 시간 유효성과 대체

- 모델은 사례5의 두 시간이다. 사건 시간은 claim 행 날짜(근거 세션·L1 노트 날짜), 시스템 시간은 frontmatter `updated`와 Vault git 기록.
- 회상과 L3는 status `superseded`·`deprecated`·`retired`와 `superseded` claim 행을 넣지 않는다. 페이지 단위는 이미 한다(`recall.py:43`, `:457-460`). claim 행 단위 제외는 `docs/SPEC.md` 가치5의 남은 일(n차-1)이고 이 설계의 1순위 품질 작업이다(사례12).
- 새 frontmatter 필드는 제안하지 않는다. claim 행 날짜와 `superseded_by`로 충분하다.

### 3.6 신뢰도와 사람 검토

- `stated` + 사용자 문장 인용 → `confidence: high`, 바로 발행.
- `inferred` → 검토 대기열. 승인 전에는 회상·검색에 없다(지금 규칙). 승인되면 `medium`.
- 검토 부담을 줄이려고 정리 꾸러미 한 번의 `inferred` 제안 수에 상한을 둔다(예: 10개, 추정). 세션 시작 구획D가 대기 수를 이미 알린다.

### 3.7 감쇠, 정리, 요약

- 정리 후보 점수(vg, 결정적): 고정이 아니고, 최근 N일(예: 90일) 동안 `injected`는 있는데 `fetched`가 0이거나 둘 다 0, 근거로 가리키는 코드 경로나 심볼이 등록 저장소에서 사라진 것. 코드 신호는 vg 코드 투영(M11)이 있어 가능하다. 점수는 정리 꾸러미에 "폐기 후보"로만 올리고, 폐기는 에이전트가 `retire_memory`로 하고 사람이 확인한다. 자동 폐기는 하지 않는다.
- 회상 순위: 지금 최신순을 "최근성(마지막 fetched 기준) + 범위 일치 + 종류 가중치(교정·규칙 > 결정 > 기타)"로 바꾸는 것을 제안한다. 중요도 점수는 LLM이 필요해 쓰지 않는다(사례7과 다른 점).
- L3 요약은 4절의 두 부분으로 나눈다. 목록 부분은 매 회상 때 색인에서 다시 만든다. 서술 부분(brief)은 정리 작업 끝에 에이전트가 바뀐 결정이 있을 때만 고친다(사례7의 "쌓이면 요약").

### 3.8 회상

| 구획 | 내용 | 예산(제안) |
|---|---|---|
| 구획A | 고정 기억 | 400 (지금) |
| 구획L3 | 프로젝트 brief 앞부분 + 열린 일·현재 결정·교정 목록 | 500 |
| 구획B | 범위 안 나머지 기억, 3.7 순위 | 남은 예산 |
| 구획C·D | 대체·폐기 알림, 검토 대기 수, 정리 대기 한 줄 | 150 + 30 |

- 총 1,500토큰은 유지한다. 범위는 `page_in_project` + `share_untagged`(spec D1, §9.1).
- L1과 겹침: `MEMORY.md`는 Claude Code가 따로 넣는다. 현재 L1 노트와 sha256이 같은 사본만 근거로 가진 L2 페이지는 구획B에서 뒤로 미룬다(제안).
- 필요할 때 찾기: `search_vault`, `build_context_pack`, `summarize_project_memory`. 질문 기반 회상(가치4 n차-8)은 이 spec 범위 밖.

### 3.9 품질 측정

- 평가 세트: 이 사용자의 프로젝트 2~3개에서 질문 40개 안팎을 사람이 만든다. 축은 사례10 다섯 개 + 코딩 전용 둘(프로젝트 섞임, 대체된 결정 사용).
- 자동 지표(사용 기록과 색인만으로 계산):
  - 지표1 대체·폐기 기억 주입 수. 목표 0.
  - 지표2 다른 프로젝트 기억 주입 비율(`share_untagged` false Vault 기준). 목표 0.
  - 지표3 주입 대비 fetched 비율. 회상 정밀도의 대리값(추정 지표).
  - 지표4 `inferred` 제안 승인율. 낮으면 추출 기준이 느슨하다.
  - 지표5 정리 대기 나이(가장 오래된 미반영 L1·세션). 
  - 지표6 병합 후보 수 추이.
- 평가 세트 실행: 질문마다 회상 텍스트와 `build_context_pack` 결과에 정답 페이지가 있는지 결정적으로 본다. 답변 채점에 LLM은 쓰지 않는다.

## 4. L3와 계층 이동 로직의 위치 (질문8)

### 4.1 비교

| 기준 | (a) vg 파생 투영만 | (b) vg가 L3 페이지를 Vault에 씀 | (c) 혼합: 목록은 vg 투영, brief는 Vault 페이지 |
|---|---|---|---|
| 규칙 수 | 하나(vg) | 하나(vg) | 목록 하나(vg) + brief는 판단물 |
| Obsidian만 쓰는 사용자 | L3를 못 본다 | 본다 | brief를 본다. 목록은 Vault `maps`가 있으면 본다 |
| `recall.sh` 대체 경로 | 읽을 것이 없다 | 읽는다 | brief를 읽는다 |
| 여러 Vault 합친 요약 | 된다 | 쓰는 Vault에 다른 Vault 내용이 들어간다. team Vault에 personal 내용이 새는 위험 | 목록은 합쳐서, brief는 프로젝트 기본 저장 Vault 하나에 |
| Vault 변경량 | 0 | 발행마다 생성 페이지 커밋 | brief가 바뀔 때만 |
| 경계 | 바뀌지 않음 | 기계 생성물을 Vault에 씀(원칙2와 어긋남: 파생물이 원본에 섞임) | 판단된 내용만 기존 쓰기 길로 |
| 신선도 | 매 회상 계산 | 쓰기 뒤 재생성 필요 | 목록은 매번, brief는 정리 때 |

### 4.2 권고: (c) 혼합

1. 목록(열린 일, 현재 결정, 교정·규칙)은 결정적으로 다시 만들 수 있는 파생물이다. Vault에 쓸 이유가 없고, 쓰면 Vault마다 다른 범위와 커밋 소음이 생긴다. vg가 회상·`summarize_project_memory` 시점에 색인에서 계산한다. 저장소를 새로 두지 않는다.
2. brief(목표, 현재 구조, 지금 지켜야 할 제약, 다음 단계 요약)는 판단물이고 사람이 Obsidian에서 읽고 고칠 가치가 있다. 프로젝트 기본 저장 Vault의 `wiki/projects/<project>.md`(경로 제안, Vault 스키마에 project 종류가 필요한지 확인 필요, 추정)에 에이전트가 `remember`/`update_memory`로 쓴다. 기존 쓰기 길 그대로다.
3. 계층 이동 로직(후보 찾기, 비교 재료, 정리 점수)은 vg 안 읽기 전용 코드다. 쓰기는 M18과 Vault 도구로만 한다.
4. Vault `maps build`의 프로젝트 요약(재료8)은 이주 중 대체 경로로 두고, `recall.sh`가 brief를 읽게 된 뒤 끈다(5절).

규칙 한 줄로 정리하면: "vg는 기계가 만든 내용을 Vault에 쓰지 않는다. Vault에는 에이전트나 사람이 판단한 내용만 Vault 도구로 들어간다."

## 5. 경계 문장 변경안 (질문 3번)

### 5.1 `AGENTS.md` Project Boundary

`AGENTS.md:9` "There are three such paths:"를 "There are four such paths:"로 바꾸고 4번을 더한다.

```text
4. `import-source`: to keep a Claude Code auto memory note (L1) as evidence,
   Vault Graph runs the Vault's `import-source <note> --into raw/imports/claude-memory/`
   (name is a proposal). The Vault command copies the bytes and registers the
   source page. Vault Graph never copies the file itself and never edits,
   moves, or deletes L1 files.
```

`AGENTS.md:19-20`을 다음으로 바꾼다.

```text
Search, indexing, watch, and recall never run write paths. Indexing may run
read-only Vault commands (`memory-scan --json`, `review list --json`) and keep
their results in Graph Home. Vault Graph never writes to `raw/` itself.
Vault Graph never writes machine-generated content (summaries, lists, scores)
to a Vault. Only content an agent or a person judged goes through paths 1, 2, and 4.
```

### 5.2 `docs/SPEC.md` 원칙

- 원칙1(`docs/SPEC.md:59`) 뒤에 한 문장: "기억 관리에서 vault-graph는 판단 재료(후보, 비슷한 기존 페이지, 대체·폐기 후보, 정리 점수)를 결정적으로 만들고, 무엇을 기억·수정·폐기할지는 호출한 에이전트가 정한다."
- 원칙4(`:62`) "구현된 길은 세 가지다"를 "네 가지"로 바꾸고 "Claude Code 자동 기억 노트의 보존은 Vault `import-source`"를 더한다.
- §4 읽는 대상(`:100-104`)에 더한다: "Claude Code 자동 기억 폴더 `$HOME/.claude/projects/<key>/memory/`(`CLAUDE_CONFIG_DIR`·`autoMemoryDirectory` 설정을 따른다). 읽기만 한다."
- §2 역할 분담 표 "LLM" 행(`:77`)의 Vault 칸 "정리 스킬에서 쓴다"를 "Vault-only 대체 경로의 정리 스킬에서 쓴다"로 바꾼다.
- 선택 로컬 LM(지금은 넣지 않음, 3.9 측정에서 이득이 확인될 때만 원칙1에 더할 문장): "예외: 사용자가 켠 경우에 한해, 로컬에서 도는 작은 언어 모델로 세션 교환의 정리 우선순위만 매길 수 있다. 이 점수는 꾸러미 순서만 바꾸고 기억 내용, `basis`, 쓰기 여부를 정하지 않는다. 모델 파일은 사용자가 지정하고 vault-graph는 내려받지 않는다."

### 5.3 vault-builder 요청 (spec §4.5에 더할 것)

- 요청S8 `import-source`: `raw/` 밖 파일을 정해진 `raw/imports/<kind>/` 이름으로 바이트 그대로 복사하고 `ingest-source`까지 하는 결정적 명령. 같은 sha256이면 아무것도 만들지 않는다. 근거: `ingest-source`가 `raw/` 밖 경로를 거부한다(재료2).
- 요청S9 brief 페이지 종류와 경로 규칙, `recall.sh`가 brief를 읽기.
- 요청S4(범위 규칙)는 `share_untagged`로 내용이 바뀐다.

## 6. 바뀌거나 없어지는 vault-builder 구성과 이주 순서 (질문 4번)

| 코드 | 구성 | 결과 | 이유 |
|---|---|---|---|
| 이주1 | `memory-cleanup` 스킬 (`vault-builder:.agents/skills/memory-cleanup/SKILL.md`) | Vault-only 대체 경로로 동결. 새 기능 없음 | 판단 흐름이 vg 정리 꾸러미로 옮긴다. vg 없는 사용자를 위해 남긴다 |
| 이주2 | `memory_scan.py` (`vault-builder:tools/wiki/lib/memory_scan.py:209-303`) | 유지. vg가 색인 때 `memory-scan --json`을 읽기 전용으로 실행해 결과를 쓴다 | 반영 판정 규칙이 한 곳에 남는다(memory-layers 발견7 일부 해소) |
| 이주3 | `maps build` 프로젝트 요약 (`maps.py:255-305`) | 이주 중 유지, 범위 규칙만 맞춤. `recall.sh`가 brief로 옮긴 뒤 생성 중단 | 목록은 vg 투영이 대신한다 |
| 이주4 | `recall.sh` (`vault-builder:tools/vault_migration/assets/project-memory/scripts/recall.sh`) | 유지, 읽는 곳을 brief 페이지로 바꿈 | vg 실패 때의 대체 경로(결정10) |
| 이주5 | `/project-memory` 스킬 | vg가 있으면 `summarize_project_memory`를 쓰도록 안내를 바꾸고, 없으면 지금처럼 `recall.sh` | 같은 질문에 두 답이 나오지 않게 한다 |
| 이주6 | `vault_hooks.py` (`vault-hooks/vault_hooks.py:131-164`) | 유지 | 이미 vg를 먼저 부르고 실패 때만 대체 경로로 간다 |

이주 순서(각 단계 뒤에도 vg 경로와 `recall.sh` 경로 둘 다 회상을 낸다):

1. 단계1 vg: `remember`에 `project`와 `tags`(spec D2), `page_in_project` + `share_untagged`(D1). vault-builder: 요청S4. 회상 소스는 그대로.
2. 단계2 vg: 회상 구획L3(목록 투영)을 더한다. 실패하면 구획L3만 빠지고 나머지는 그대로 나온다.
3. 단계3 vault-builder: 요청S8 `import-source`. vg: L1 읽기 어댑터, 색인 때 `memory-scan` 결과 저장, 정리 대기 한 줄(D3).
4. 단계4 vg: 정리 꾸러미 MCP 도구와 `curate_memory` prompt, `import-source` 실행 경로. `memory-cleanup`은 그대로 쓸 수 있다.
5. 단계5 평가 세트로 지표1~6을 잰다. 지표1·2가 0이 아니면 다음 단계로 가지 않는다.
6. 단계6 brief 페이지를 처음 쓴다. vault-builder: 요청S9로 `recall.sh`가 brief를 읽는다. 그 뒤 `maps build` 프로젝트 요약 생성을 끄고 `memory-cleanup`을 대체 경로로 문서화한다.

## 7. vg 모듈 배치 (질문 5번)

새 영역은 없다. 가져오기 방향은 `docs/ARCHITECTURE.md:199-216` 표 안에서 허용된 것만 쓴다.

| 일 | 위치 | 비고 |
|---|---|---|
| 범위 규칙 `page_in_project(frontmatter, project_id, share_untagged)` | M10 `context/memory/` | spec D1. M08이 가져온다(허용) |
| L3 목록 투영 | M10 `context/memory/project_memory.py` 확장 | 회상과 MCP가 같은 함수를 쓴다(memory-layers 발견1 해소) |
| 정리 후보·비교 재료·정리 점수 | M10 새 파일 `context/memory/memory_candidates.py` | M05 검색을 가져올 수 있다(허용). 코드 경로 소멸 신호는 M10이 M11을 못 가져오므로 `interface/composition/`에서 합친다 |
| 회상 구획L3, 정리 대기 줄, 순위 변경 | M08 `context/pack/recall.py`, `recall_backlog.py` | spec D3 |
| L1 폴더 읽기 | `interface/composition/adapters/auto_memory_reader.py` | spec D3 |
| `memory-scan` 결과 읽기·저장 | `interface/composition/adapters/` 새 어댑터 + Graph Home `memory/` | 색인 실행 때만 |
| `import-source` 요청·포트 | M18 `operation/memory/` (`memory_requests.py`, `memory_ports.py`) | 실행은 `interface/composition/adapters/vault_publish_cli.py` 옆 어댑터 |
| MCP 도구 `list_memory_candidates`(읽기), `import_auto_memory`(쓰기) | `interface/mcp/mcp_tools.py`, `mcp_memory_tools.py` | 이름은 제안 |
| MCP prompt `curate_memory` | `interface/mcp/mcp_prompts.py` | 재료7 |
| 평가 실행 | `tests/` 아래 평가 세트 + CLI 진입점 여부는 미정 | 추정 |
| 선택 로컬 LM | 넣지 않음. 넣게 되면 `storage/interfaces/` 포트 + `interface/composition/adapters/` 구현 | 5.2 조건 |

## 8. 위험과 열린 점

- 위험1 건너뛴 후보가 매번 다시 올라온다. "검토함" 기록을 어디 둘지 정해야 한다. Graph Home에 두면 지워도 다시 만들 수 있지만 다시 만들 때 같은 후보가 다시 올라온다.
- 위험2 `stated` 판정이 넓으면 검토 없이 틀린 기억이 발행된다. 지표4와 사람 표본 검토로 확인한다.
- 위험3 brief 페이지 경로·종류가 Vault 스키마에 없으면 publish-draft가 거부한다(추정, 요청S9로 확인).
- 위험4 L1 폴더 위치는 `autoMemoryDirectory`, `CLAUDE_CODE_PROJECT_DIR_NAME` 설정으로 바뀔 수 있다(재료1). 어댑터가 이 설정을 따라야 0개로 잘못 세지 않는다.
- 위험5 claim 행 단위 대체 제외(3.5)가 안 되면 페이지 안의 옛 결정이 회상에 남는다. 사례12가 보인 가장 약한 지점이다.
