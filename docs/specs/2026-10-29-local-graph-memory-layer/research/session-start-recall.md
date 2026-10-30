# 세션 시작 회상 리서치: 시장 사례와 vault-graph 제안

- 작성일: 2026-10-30
- 대상 질문: spec 질문6(세션 시작 회상의 내용과 예산, S3), 4.2.3, A-10
- 조사 방법: 각 제품의 공식 문서, 저장소 README, 공식 블로그를 웹에서 읽었다. 공식 문서가 막혔거나(ChatGPT 도움말은 403) 제3자 자료만 있는 항목은 `[미확인]`으로 표시했다. 출처는 9절에 모았다.

## 1. 요약

1. 시장 제품은 세 갈래로 나뉜다. (가) 작은 핵심 기억을 항상 전문으로 넣는다(Letta 메모리 블록, ChatGPT saved memories, Cursor Always 규칙, CLAUDE.md). (나) 세션 시작에 목록(index)만 넣고 본문은 도구로 가져가게 한다(Claude Code `MEMORY.md`, claude-mem, Letta Code 파일 트리). (다) 세션 시작에는 거의 넣지 않고 첫 질문이 오면 검색해서 넣는다(Mem0 Claude Code 플러그인, Cognee, Honcho의 턴별 결론, Zep).
2. 질문 없이 고르는 신호는 거의 모든 제품에서 같다. 프로젝트 범위, 최근성, 고정(pin), 유형(결정·규칙·요약)이다. 사용 빈도를 쓰는 제품은 ChatGPT(최근성과 빈도로 "top of mind" 결정)와 Cognee(피드백 가중치)뿐이다.
3. 예산은 작다. Honcho 플러그인 1,500토큰, claude-mem 50개 목록 약 800토큰(문서 예시), Mem0 자동 회상 5개·4,000자, Supermemory 5~10개, Cognee 9,000자, Claude Code `MEMORY.md` 200줄·25KB. Claude Code 훅 출력 자체가 문자열당 10,000자로 잘린다.
4. "어떤 기억이 쓰였는가"를 기록하는 제품은 드물다. Cognee만 주입 항목에 태그(`m1`, `m2`)를 붙이고 에이전트에게 사용한 태그를 적게 해 적중률 보고서를 만든다. 나머지는 사람의 직접 검토(목록 보기·삭제·고정)에 기댄다.
5. 이력은 "지우지 않고 무효 표시"가 주류다. Graphiti/Zep은 사실마다 유효 기간을 두고 끝난 사실을 "더 이상 유효하지 않음"으로 표시한다. Supermemory는 새 버전을 만들고 옛 버전을 `isLatest=false`로 남긴다. Mem0는 ADD/UPDATE/DELETE 이력을 남긴다. Letta Code는 git 커밋으로 남긴다.
6. vault-graph 추천(옵션1): 1,500토큰 안에 "고정 핵심 전문(작게) + 프로젝트 기억 목록(한 줄씩, ID·날짜·상태·토큰 비용) + 최근 무효화 알림 + 가져오는 방법 한 줄"을 넣는다. 본문은 에이전트가 ID로 가져간다. 주입·조회 기록은 Graph Home의 별도 사용 기록에 남기고, Vault 쪽 고정·정리는 검토 목록으로만 제안한다.

## 2. 제품별 조사

표의 "시작 주입"은 세션이 열릴 때 질문 없이 들어가는 것, "필요 시"는 도구나 검색으로 가져오는 것이다.

### 2.1 비교표

| 제품 | 시작 주입 | 필요 시 | 질문 없이 고르는 방법 | 예산 |
|---|---|---|---|---|
| Claude Code CLAUDE.md | 작업 디렉터리 위쪽 CLAUDE.md 전문, 경로 조건 없는 규칙 | 하위 디렉터리 CLAUDE.md, `paths` 조건 규칙 | 사람이 쓴 파일, 디렉터리 위치 | 파일당 4MiB까지 전문. 200줄 이하 권장 |
| Claude Code auto memory | `MEMORY.md` 앞 200줄 또는 25KB | 주제 파일(`*.md`) | 목록 파일 앞부분. 에이전트가 목록을 짧게 유지 | 200줄/25KB |
| Claude Code SessionStart 훅 | 훅 표준 출력 또는 `additionalContext` | 없음 | 훅이 정함 | 문자열당 10,000자. 넘으면 파일로 빼고 앞 2,000자만 보임 |
| claude-mem | 최근 관찰 목록(ID, 시각, 유형, 제목, 토큰 수)과 최근 세션 요약 | `search` → `timeline` → `get_observations` 3단계 | 프로젝트(cwd 이름) + 최근순. 관찰 50개, 요약 10개 | 문서 예시 50개 ≈ 800토큰 |
| Honcho (claude-honcho) | 사용 안내문, 세션 장기 요약, peer card | 턴마다 의미 검색 결론 주입, `chat`·`search` 도구 | peer card(사용자 속성 목록)와 요약은 질문과 무관하게 고정 | `sessionContextTokens` 1,500, 결론 최대 15개 |
| Mem0 (Claude Code 플러그인) | 없음. 첫 프롬프트가 20자 이상이면 그것으로 검색해 최대 5개 | `search_memories`(기본 3개, 최대 20) | 질문 없이는 고르지 않음 | 검색당 4,000자(1,000~10,000) |
| Letta 메모리 블록 | 모든 블록 전문(매 턴) | archival memory 의미 검색 | 사람·에이전트가 블록에 넣은 것 | 블록마다 문자 수 한도 |
| Letta Code (MemFS) | 루트(옛 `system/`) 파일 전문 + 파일 트리 + 각 파일 frontmatter 설명 | 나머지 파일을 에이전트가 읽음 | 고정 폴더 위치 | 저장소 5MiB(Free) |
| Zep / Graphiti | 사용자 요약 + 최근 메시지와 관련된 사실·엔티티 | 사용자 정의 검색 | 최근 메시지 4개를 질의로 사용. 사용자 요약은 항상 | 예시 `limit=10` |
| basic-memory | 핵심 서버는 없음. Claude Code 플러그인이 진행 중 작업과 최근 노트로 브리핑 `[미확인]` | `search_notes`, `build_context`, `recent_activity(timeframe)` | 최근 변경 기간(예: 3일) | 명시 없음 |
| ChatGPT | saved memories(항상 고려), 채팅 기록에서 얻은 요약 | 과거 채팅 참조 | 최근성과 주제 빈도로 "top of mind" 유지 `[미확인: 2차 자료]` | 명시 없음 |
| Cursor | Always 규칙 전문. Memories는 2.1부터 관리 UI 제거, 규칙으로 내보내기 권장 `[미확인: 포럼]` | Agent Requested 규칙(설명을 보고 에이전트가 고름), glob 규칙 | 사람이 정한 적용 방식 | 규칙당 500줄 이하 권장 |
| Supermemory | 사용자 프로필(static 장기 사실 + dynamic 최근 맥락, 날짜 붙음) | 검색 | 프로필이 자동 압축 | `maxProfileItems` 5(Claude Code), Cursor 10 |
| Cognee (Claude Code 플러그인) | 설정과 "MEMORY.md보다 Cognee를 우선" 안내만 | 매 프롬프트 그래프 회상 | 질문 없이는 고르지 않음 | 총 9,000자, 구절당 1,200자 |

### 2.2 제품별 메모

1. Claude Code(공식 기능). CLAUDE.md는 사람이 쓴 지시, auto memory는 에이전트가 쓴 학습 내용이다. 둘 다 세션마다 들어간다. auto memory는 `MEMORY.md`를 "한 줄에 한 기억" 목록으로 쓰고 상세는 주제 파일로 보낸다. 한도에 가까우면 Claude Code가 줄이라고 알리고, 넘으면 다시 쓰라고 오류를 낸다. 사용 관리: `/memory`로 파일을 열어 사람이 고친다. 화면에 "Recalled 2 memories" 같은 표시가 나온다. 이력: 없음. 일반 파일이다.
2. claude-mem. SessionStart는 startup·clear·compact에서 돌고 resume·continue에서는 돌지 않는다. 목록 줄마다 토큰 수를 보여 에이전트가 가져올 비용을 판단하게 한다. 관찰 유형 9종(결정, 문제-해결, 바뀐 것 등)을 아이콘으로 표시한다. 사용 추적·감쇠·대체 처리는 문서에 없다.
3. Honcho. `session.context(tokens=…)`가 요약과 최근 메시지를 예산 안에 섞어 돌려준다. `peer_target`을 주면 peer card와 representation이 붙는다. `include_most_frequent`로 자주 나온 결론을 넣을 수 있다. 결론은 LLM 추론(deriver)으로 만든다. 사용 기록 기능은 문서에서 찾지 못했다.
4. Mem0 / OpenMemory. 세션 시작에 질문 없이 넣지 않는다. 대신 첫 프롬프트를 질의로 쓴다. 이력: 기억마다 `old_memory`, `new_memory`, `event`(ADD/UPDATE/DELETE), 원인 메시지, 시각을 남기는 history API가 있다. `expiration_date`가 지나면 지우지 않고 검색에서 숨긴다. `immutable` 기억은 수정 대신 삭제 후 재추가만 허용한다. OpenMemory 대시보드의 active/paused/archived 상태와 접근 로그는 제3자 이미지 설명에서만 확인했다 `[미확인]`. OpenMemory 코드는 현재 mem0 저장소 main에서 찾지 못했다.
5. Letta. 블록은 매 턴 프롬프트 앞에 들어가고, 블록마다 `description`과 문자 한도가 있다. `read_only` 블록은 에이전트가 못 고친다. archival memory는 고정할 수 없고 검색으로만 가져온다. Letta Code는 기억을 git 저장소의 Markdown 파일(frontmatter 포함)로 바꿨다. 파일 트리와 설명이 늘 보이고, 본문은 필요할 때 연다. 모든 편집이 커밋되어 이력이 남는다. 백그라운드 subagent가 대화를 돌아보며 기억을 정리하고(sleeptime), 큰 정리 전에는 백업한다.
6. Zep / Graphiti. 사실(그래프 간선)마다 `valid_at`·`invalid_at`(현실에서 참인 기간)과 `created_at`·`expired_at`(시스템이 안 시각)을 둔다. 모순되는 새 사실이 오면 옛 사실을 지우지 않고 무효로 표시한다. 문맥 블록은 사실 옆에 "날짜 범위: 시작 - present"를 붙이고, 끝난 사실은 지금 유효하지 않다고 모델에 알린다. 이 방식이 vault-graph의 claim 상태 표시와 가장 가깝다.
7. basic-memory. Markdown 파일 + SQLite 색인 + wiki 링크 그래프라는 점에서 vault-graph와 구조가 가장 비슷하다. 질문 없이 쓰는 도구는 `recent_activity(timeframe)`와 `build_context(memory://…)`다. 로컬 판에는 이력 기능이 없고 git을 권한다.
8. ChatGPT. saved memories와 채팅 기록 참조 두 층이다. 자동 기억 관리는 최근성과 빈도로 우선순위를 정하고, 사용자가 특정 기억을 올리거나 내릴 수 있다고 2차 자료가 전한다 `[미확인]`. 임시 채팅은 기억을 읽지도 쓰지도 않는다. 주입 방식은 공개 문서에 없다.
9. Cursor. 규칙 4종(Always, glob, Agent Requested, Manual)은 "질문 없이 무엇을 넣는가"를 사람이 정하게 한다. Agent Requested는 설명만 보이고 본문은 에이전트가 고를 때 들어가므로 목록 방식의 한 형태다. Memories는 2.1에서 UI가 빠졌고 규칙으로 내보내기를 권했다 `[미확인: 포럼 직원 답변]`. 자동 기억이 사람이 관리하는 규칙으로 흡수된 사례다.
10. Supermemory. 프로필 항목은 대부분 기억 ID를 갖고 있어 항목 하나를 바로 잊게 할 수 있다. 오래된 기억을 합친 항목은 `aggregated_` ID를 쓴다. 기억을 수정하면 새 버전을 만들고 옛 버전은 `isLatest=false`로 남긴다. 관계는 updates(대체), extends(보강), derives(추론)다. 일시적 사실은 만료 시각에 잊는다.
11. Cognee. 주입 기억에 `m1`, `m2` 태그를 달고, 에이전트에게 답 끝에 사용한 태그를 적게 한다. 프롬프트마다 회상·저장 개수를 머리글로 보이고 `last_recall.json`에 남긴다. `/cognee-report`가 로컬 로그와 대화 기록으로 적중률, 지연, 부담을 계산한다. 피드백 가중치를 그래프 노드·간선에 저장해 다음 검색 순위에 반영한다(`improve()`).

## 3. 발견

- 발견1 질문 없는 시작 주입은 "작은 고정 핵심 + 목록"이 표준이다. 전문을 많이 넣는 제품은 사람이 내용을 직접 관리하는 경우(CLAUDE.md, Letta 블록, Cursor Always)뿐이다. 자동으로 쌓이는 기억은 목록으로 넣고 본문은 나중에 가져가게 한다(claude-mem, `MEMORY.md`, Letta Code).
- 발견2 질문 없이 가장 많이 쓰는 신호는 프로젝트 범위와 최근성이다. 고정(pin)은 사람이 정한다. 사용 빈도는 ChatGPT와 Cognee만 쓴다.
- 발견3 1,500토큰은 시장 범위 안이다. Honcho 기본값과 같고, claude-mem의 50개 목록(약 800토큰)보다 크다. Claude Code 훅 10,000자 한도 안에도 들어간다. 다만 한글은 글자당 토큰 비율이 영어와 달라 글자 수 상한을 따로 두어야 한다(Cognee는 9,000자 상한).
- 발견4 "주입됨"과 "실제로 쓰임"을 나눠 기록한 공개 사례는 Cognee뿐이다. 에이전트에게 사용 태그를 적게 하는 방식은 매 응답 토큰을 쓰고, 에이전트가 빠뜨릴 수 있다. 도구 호출(ID로 본문 가져오기)은 프로그램이 직접 관찰할 수 있어 더 믿을 만하다.
- 발견5 오래된 기억을 현재 사실처럼 넣는 문제를 제품들은 두 방법으로 막는다. 무효·만료된 것은 기본 검색에서 뺀다(Mem0 만료, Supermemory `isLatest`). 넣을 때는 날짜 범위나 날짜를 같이 보여 모델이 판단하게 한다(Zep, Supermemory dynamic 항목).
- 발견6 resume 세션에는 다시 넣지 않는 제품이 있다(claude-mem). 이미 대화 기록에 있으므로 중복이다. compact 뒤에는 다시 넣는다.
- 발견7 사람의 검토 경로가 항상 있다. 목록 보기, 고치기, 지우기, 고정·해제가 기본이다(`/memory`, ChatGPT 설정, Supermemory 항목별 forget, Letta `/memory`).
- 발견8 vault-graph는 이미 다른 제품이 LLM으로 만드는 것을 사람이 검증한 Vault로 갖고 있다. 결정, 열린 질문, claim 상태(stated/inferred/contested/deprecated/superseded), 근거(raw)가 그것이다. 그래서 LLM 없이도 Zep 수준의 "현재/무효" 구분을 할 수 있다. 부족한 것은 고정 표시와 기억 유형(규칙·교정)을 담는 frontmatter다(의존5).

## 4. vault-graph 제안

전제: vault-graph는 LLM을 부르지 않는다(결정7). 쓰기는 Graph Home, Vault 쓰기는 publish-draft 경유만 한다. 세션 시작 회상은 검색과 임베딩 모델을 열지 않는다(S3).

### 4.1 무엇을 넣는가

출력은 네 구획이고 이 순서로 예산을 쓴다. 예산을 다 쓰면 뒤 구획의 줄을 줄이고, 줄인 개수를 끝에 적는다.

| 구획 | 형식 | 내용 | 예산 목표 |
|---|---|---|---|
| A 고정 핵심 | 전문, 항목당 1~3줄 | 고정 표시된 규칙·교정·현재 결정 | 최대 400토큰 |
| B 기억 목록 | 한 줄 목록 | 열린 질문, 최근 결정, 최근 변경 | 나머지 대부분(약 850토큰) |
| C 변경 알림 | 한 줄 목록 | 지난 주입 이후 무효·대체된 항목 | 최대 150토큰 |
| D 사용 안내 | 고정 문장 1~2줄 | 본문을 가져오는 방법 | 약 50토큰 |

1. 구획A 고정 핵심. 대상은 Vault frontmatter에 고정 표시가 있는 항목이다. 이 필드는 아직 없으므로 의존5(`vault-memory/v1`)에 `pin: true`와 `memory_kind: rule|correction|decision|preference`를 요청한다. 그 전에는 구획A를 비우고 그 예산을 구획B로 넘긴다. vault-graph가 내용을 보고 규칙인지 추측하지 않는다.
2. 구획B 기억 목록. 줄 형식은 다음과 같다.
   `- [m:3f2a] 결정 · 2026-10-28 · stated · 세션 시작 회상은 검색을 부르지 않는다 (wiki/decisions/x.md, ~180t)`
   ID, 유형, 마지막 변경 날짜, 상태, 제목, Vault 상대 경로, 본문 추정 토큰 수를 넣는다. 토큰 수는 claude-mem처럼 가져올 비용을 알려준다. Vault가 둘 이상이면 Vault 이름을 경로 앞에 붙인다(위험2).
3. 구획C 변경 알림. 지난번 이 프로젝트에 주입했던 항목 중 그 뒤 `superseded`·`deprecated`가 된 것을 "옛 제목 → 새 제목(날짜)" 한 줄로 보인다. 에이전트가 이전 세션이나 Claude Code auto memory에서 옛 내용을 기억하고 있을 때 바로잡는 용도다. 사용 기록(4.2)이 없으면 "최근 14일 안에 대체된 항목"으로 대신한다.
4. 구획D 사용 안내. "본문은 `vg memory get m:3f2a` 또는 MCP `memory_get(ids)`로 가져온다" 한 줄이다. 기존 MCP 도구 11개 중 ID로 본문을 돌려주는 도구가 있는지는 확인하지 않았다 `[미확인]`. 없으면 `memory_get`이 12번째(remember 포함 13번째) 도구가 된다.

질문 없이 고르는 신호와 우선순위:

1. 범위: `cwd` → `vault-map.json` → 연결된 Vault와 프로젝트(4.2.2). 프로젝트 범위 밖 항목은 고정 표시가 있어도 넣지 않는다.
2. 상태: `stated`는 그대로, `inferred`는 "추정"으로 표시, `contested`는 "논쟁 중"으로 표시하고 구획B에만 넣는다. `stale`·`deprecated`·`superseded`는 구획B에 넣지 않는다(기존 `STALE_STATUSES`).
3. 고정: 구획A로 간다.
4. 최근성: 구획B 안에서는 마지막 변경 날짜 내림차순.
5. 새로움: 지난 주입 뒤 바뀐 항목을 위로 올린다. 사용 기록이 있을 때만 쓴다.
6. 사용 이력: 4.2의 "주입 대비 조회" 점수로 순서를 조금 조정한다. 최근성보다 앞서지 않게 한다. 근거는 발견2다. 사용 빈도를 크게 쓰면 이미 자주 본 것만 계속 들어간다.
7. 다양성: 유형별 상한을 둔다(열린 질문 최대 8, 결정 최대 10, 최근 변경 최대 8). 숫자는 시작값이고 측정으로 조정한다 `[가정]`.

예산:

1. 기본 1,500토큰을 유지한다. 근거는 발견3과 `recall.sh` 넘김 전후 크기 일치다.
2. 글자 수 상한 9,000자를 따로 둔다. Claude Code 훅 출력이 문자열당 10,000자를 넘으면 파일로 빠지고 앞 2,000자만 보이기 때문이다. 둘 중 먼저 닿는 한도에서 멈춘다.
3. `--max-tokens`로 바꿀 수 있다. 8,000토큰(context pack 기본값)은 권하지 않는다. 10,000자 한도를 넘기 쉽다.

SessionStart `source`별 동작:

| source | 동작 | 이유 |
|---|---|---|
| `startup`, `clear` | 전체 출력 | 새 문맥 |
| `compact` | 전체 출력 | 압축으로 앞부분이 사라짐 |
| `resume`, `fork` | 구획C만(바뀐 것이 있을 때), 없으면 종료 코드 3 | 이전 주입이 대화 기록에 남아 있음(발견6) |

### 4.2 사용 관리

목표는 두 가지다. 어떤 기억이 들어갔고 실제로 쓰였는지 남기는 것, 그리고 그 기록으로 순서를 고치고 사람에게 정리 후보를 보이는 것이다.

1. 기록 위치: Graph Home 아래 `usage/` 디렉터리에 append-only JSON Lines로 남긴다. 색인과 분리하고, 지워도 검색 결과가 바뀌지 않는다. Vault에는 쓰지 않는다.
2. 기록 사건:
   - `injected`: 세션 시작 회상이 낸 항목 ID, 구획, `session_id`, 프로젝트, 시각.
   - `fetched`: `memory_get`·`vg memory get`·검색 결과에서 본문을 연 항목 ID와 `session_id`.
   - `superseded_seen`: 구획C로 알린 항목.
3. "쓰임"의 정의: 같은 `session_id`에서 `injected` 뒤 `fetched`가 있으면 쓰인 것으로 본다. 에이전트에게 사용 태그를 적게 하는 Cognee 방식은 1차에 넣지 않는다. 매 응답 토큰이 들고 누락을 검사할 방법이 없다(발견4). n차에서 `raw/sessions/` 대화 기록을 색인할 때 응답 본문의 `m:` ID 언급을 세는 방식은 추가로 검토할 수 있다. 대화 기록에 훅 출력이 남는지는 확인하지 않았다 `[미확인]`.
4. 되먹임(ranking): 항목별 `주입 수`, `조회 수`를 집계한다. 최근 N회(기본 10회) 주입되고 한 번도 조회되지 않은 항목은 구획B 안에서 한 단계 내린다. 내리기만 하고 빼지는 않는다. 기억 자체를 지우거나 상태를 바꾸지 않는다.
5. 사람 검토: `vg memory review`(읽기 전용)가 세 목록을 보인다.
   - 고정 후보: 여러 세션에서 반복 조회된 항목.
   - 정리 후보: 오래 주입됐지만 조회되지 않은 항목, 오래된 열린 질문.
   - 모순 후보: `superseded`인데 최근에도 조회된 항목, 근거(raw)가 wiki 쪽보다 새로운 항목.
   고정·상태 변경은 사람이 결정하고 Vault 검증 도구(publish-draft, remember)로만 반영한다. vault-graph는 Vault frontmatter를 직접 고치지 않는다.

이 절은 spec과 충돌한다. 4.2.3은 세션 시작 회상을 읽기 전용으로 두고 "Graph Home에 파일을 만들지 않는다(VG-MOD INV-02)"고 적었다. `injected` 기록은 이 조건을 깬다. 질문9로 사용자 결정을 받아야 한다(6절).

### 4.3 이력과 오래됨

1. 현재로 넣는 것: `stated`, `inferred`(추정 표시), `contested`(논쟁 중 표시). 모든 줄에 마지막 변경 날짜를 붙인다(Zep·Supermemory와 같은 이유, 발견5).
2. 현재로 넣지 않는 것: `stale`·`deprecated`·`superseded` 문서. 1차는 문서 단위, claim 단위 제외는 n차-1이다. claim 단위 전까지는 문서는 현재인데 그 안의 claim 하나가 `superseded`인 경우를 놓친다. 이 한계를 구획D 아래 한 줄로 적지 않고 spec 위험 항목에 남긴다.
3. 대체 관계 보이기: 구획C에서 "옛 → 새(날짜)"를 보인다. 본문을 가져올 때(`memory_get`)는 해당 문서의 claim 표에서 상태가 바뀐 줄을 "이전 값, 바뀐 날짜, 대체한 문서"로 같이 돌려준다. Vault claim 표에 대체 대상과 날짜 열이 있는지는 확인하지 않았다 `[미확인]`. 없으면 문서 frontmatter의 `supersedes`·`superseded_by`를 의존5에 요청한다.
4. 오래됨 표시: 열린 질문이 90일 넘게 바뀌지 않았으면 "오래됨 N일"을 붙인다. 근거 raw 파일이 wiki 문서의 마지막 변경보다 새로우면 "근거가 더 새로움"을 붙인다. 두 표시 모두 항목을 빼지 않고 판단을 에이전트와 사람에게 넘긴다. 90일은 시작값이다 `[가정]`.
5. 버전 저장: vault-graph가 기억 버전을 따로 저장하지 않는다. Vault가 git 저장소라면 git 이력이 원본 이력이다 `[미확인: Vault의 git 사용 여부]`. vault-graph는 색인 시점의 상태만 갖는다.

## 5. 옵션 비교

### 옵션1 (추천) 고정 핵심 + 목록 + 변경 알림, 사용 기록 포함

- 내용: 4.1~4.3 전체.
- 장점: 1,500토큰 안에 30개 안팎 항목을 보여 에이전트가 무엇이 있는지 안다. 본문은 필요할 때만 쓴다. 대체 알림으로 오래된 기억을 바로잡는다. 사용 기록으로 측정과 정리가 가능해진다.
- 단점: `memory_get` 도구와 사용 기록이 새로 필요하다. INV-02 예외가 필요하다. 목록만 보고 에이전트가 본문을 열지 않으면 결정 내용이 문맥에 들어가지 않는다. 구획A(전문)가 이를 일부 막지만 의존5 전에는 비어 있다.

### 옵션2 지금 S3 그대로: 세 섹션 전문, 사용 기록 없음

- 내용: 열린 질문, 최근 결정, 최근 변경을 전문(요약 줄)으로 1,500토큰 안에 넣는다. 읽기 전용.
- 장점: 가장 작은 변경이다. INV-02를 지킨다. `recall.sh`와 형태가 비슷하다.
- 단점: 들어가는 항목 수가 적다(전문이라 10개 안팎 `[가정]`). 무엇이 쓰였는지 모르므로 예산과 선택 기준을 측정으로 고칠 수 없다. 대체 알림이 없다.

### 옵션3 시작에는 목록만, 첫 프롬프트에서 검색 주입(UserPromptSubmit)

- 내용: SessionStart는 옵션1의 구획B·D만 넣는다. 첫 사용자 프롬프트가 오면 그 문장으로 vault-graph 검색을 돌려 상위 3~5개 본문을 넣는다(Mem0, Cognee, Honcho 방식).
- 장점: 질문과 맞는 본문이 들어가 관련도가 가장 높다.
- 단점: 프롬프트마다 검색 지연이 생기고 임베딩 모델을 연다. S3의 "검색을 부르지 않는다"는 SessionStart에 대한 것이지만 훅 범위가 넓어진다. vault-builder 훅(의존1)에 새 이벤트가 필요하다. 1차 범위를 넘는다.

추천 근거: 옵션1이 발견1·3·5를 모두 반영하고, 옵션2의 측정 불가 문제를 푼다. 옵션3은 측정1 결과로 검색 품질이 확인된 뒤 n차로 미룬다. 사용 기록(INV-02 예외)을 받아들이지 않으면 옵션1에서 4.2를 빼고 구획C를 "최근 14일 대체"로 운영할 수 있다(옵션1-읽기전용).

## 6. 결정이 필요한 질문

- 질문9 세션 시작 회상과 `memory_get`이 Graph Home `usage/`에 사용 기록을 쓰는 것을 INV-02의 예외로 허용할 것인가. 허용하면 4.2 전체가 가능하다. 거부하면 옵션1-읽기전용이 된다.
- 질문10 Vault 기억 frontmatter(의존5)에 `pin`, `memory_kind`, `supersedes`·`superseded_by`를 요청할 것인가. 요청하지 않으면 구획A는 계속 비고 대체 알림은 상태 값과 날짜만으로 만든다.
- 질문11 resume 세션에서 회상을 넘길 것인가(4.1 표). 넘기면 종료 코드 3이 되어 훅이 `recall.sh`로 넘어가지 않도록 vault-builder 분기(의존1)가 `source`를 봐야 한다.

## 7. 수용 확인 (A-10 대체안)

옵션1 기준이다. 옵션1-읽기전용이면 A-10c·A-10d를 뺀다.

- A-10a fixture Vault와 map으로 `source=startup` 입력을 주면 종료 코드 0, 표준 출력에 구획 A(비어 있으면 제목 없이 생략), B, C(해당 없으면 생략), D 순서의 Markdown이 나온다. 추정 토큰 수가 `--max-tokens`(기본 1,500) 이하이고 글자 수가 9,000자 이하다.
- A-10b 구획B의 모든 줄에 ID, 유형, 날짜, 상태, 제목, Vault 상대 경로, 추정 토큰 수가 있다. `stale`·`deprecated`·`superseded` 문서는 구획B에 없다. `inferred`·`contested` 항목은 각각 "추정", "논쟁 중" 표시가 있다. 프로젝트 범위 밖 문서는 없다.
- A-10c fixture에서 직전 주입 항목 하나를 `superseded`로 바꾸고 다시 색인한 뒤 실행하면 구획C에 "옛 → 새(날짜)" 줄이 정확히 하나 나온다.
- A-10d 실행 뒤 Graph Home `usage/`에 `injected` 사건이 출력 항목 수만큼 추가된다. Vault 파일 바이트와 Graph Home의 색인 파일 바이트는 실행 전후로 같다. `memory_get(m:…)` 호출 뒤 `fetched` 사건이 하나 추가된다.
- A-10e `source=resume`이고 바뀐 것이 없으면 표준 출력이 비고 종료 코드가 3이다.
- A-10f 예산을 300토큰으로 낮추면 구획A·C가 먼저 남고 구획B가 줄며, 끝에 "N개 생략"이 적힌다.
- A-10g 임베딩 제공자나 벡터 저장소를 만들면 실패하는 대역으로도 A-10a가 통과한다.
- A-10h (수동) 실제 Vault에서 연속 20회 실행 p95가 2초 이하다. 실제 Claude Code 세션에서 `/context`에 훅 출력이 잘리지 않고 들어간 것을 확인한다.
- A-10i (수동, 2주 운영 뒤) `vg memory review`가 고정 후보·정리 후보·모순 후보를 낸다. 주입 대비 조회 비율을 측정1 보고서에 적는다. 이 비율이 예산 조정의 근거다.

## 8. spec에 반영할 곳

1. 4.2.3: 구획 구조, 줄 형식, `source`별 동작, 글자 수 상한 9,000자를 추가한다. 읽기 전용 문장은 질문9 답에 따라 고친다.
2. S3: "열린 질문, 최근 결정, 최근 변경 전문" → "고정 핵심 + 목록 + 대체 알림, 1,500토큰·9,000자".
3. A-10: 7절의 A-10a~A-10i로 바꾼다.
4. 의존5 요청 내용에 질문10의 필드를 더한다.
5. 새 n차 항목: 첫 프롬프트 검색 주입(옵션3), 대화 기록 기반 사용 집계.

## 9. 출처

공식 문서와 저장소:

- Claude Code memory: https://code.claude.com/docs/en/memory
- Claude Code hooks (SessionStart, 10,000자 한도): https://code.claude.com/docs/en/hooks
- claude-mem progressive disclosure: https://docs.claude-mem.ai/progressive-disclosure
- claude-mem hooks: https://docs.claude-mem.ai/hooks-architecture.md
- Honcho get context: https://honcho.dev/docs/v3/documentation/features/get-context.md
- Honcho 소개: https://honcho.dev/docs/
- claude-honcho 플러그인: https://github.com/plastic-labs/claude-honcho
- Mem0 Claude Code 연동: https://docs.mem0.ai/integrations/claude-code
- Mem0 history API: https://docs.mem0.ai/api-reference/memory/history-memory.md
- Mem0 만료: https://docs.mem0.ai/platform/features/expiration-date
- Mem0 update(immutable): https://docs.mem0.ai/api-reference/memory/update-memory.md
- Letta memory blocks: https://docs.letta.com/guides/agents/memory-blocks
- Letta archival memory: https://docs.letta.com/guides/agents/archival-memory
- Letta Code memory: https://docs.letta.com/letta-code/memory
- Letta MemFS: https://docs.letta.com/letta-code/memfs
- Letta context repositories 블로그: https://www.letta.com/blog/context-repositories
- Zep context types: https://help.getzep.com/context-types
- Zep facts: https://help.getzep.com/facts
- Zep advanced context block: https://help.getzep.com/advanced-context-block-construction
- Graphiti: https://github.com/getzep/graphiti
- basic-memory: https://github.com/basicmachines-co/basic-memory
- Cursor rules: https://cursor.com/docs/context/rules
- Supermemory user profiles: https://supermemory.ai/docs/user-profiles.md
- Supermemory graph memory: https://supermemory.ai/docs/concepts/graph-memory
- claude-supermemory: https://github.com/supermemoryai/claude-supermemory
- Supermemory Cursor 연동(maxMemories 10): https://supermemory.ai/docs/integrations/cursor.md
- Cognee 개요: https://docs.cognee.ai/core-concepts/overview
- Cognee Claude Code 연동: https://docs.cognee.ai/integrations/claude-code-integration
- Cognee improve: https://docs.cognee.ai/core-concepts/main-operations/improve
- Cognee feedback: https://docs.cognee.ai/guides/feedback-system.md

2차 자료(`[미확인]` 항목의 근거):

- ChatGPT Memory FAQ(접속 403, 검색 요약으로만 확인): https://help.openai.com/en/articles/8590148-memory-faq
- ChatGPT 기억 우선순위 포럼 글: https://community.openai.com/t/how-does-chatgpt-decide-which-memories-to-retrieve/1385823
- Cursor Memories 2.1 UI 제거 포럼: https://forum.cursor.com/t/custom-modes-and-memories-gone-in-2-1/143744 , https://forum.cursor.com/t/are-my-memories-gone/144057
- basic-memory Claude Code 플러그인 목록 페이지: https://skillselion.com/skills/basicmachines-co/basic-memory/plugins/claude-code
- OpenMemory UI(제3자 이미지): https://hub.docker.com/r/skpassegna/openmemory-ui

확인하지 못한 것:

1. ChatGPT의 실제 주입 방식과 우선순위 계산식.
2. OpenMemory의 상태(active/paused/archived)와 접근 로그. 현재 mem0 저장소에서 코드를 찾지 못했다.
3. basic-memory Claude Code 플러그인의 SessionStart 내용(공식 문서 미확인).
4. Claude Code 대화 기록(JSONL)에 SessionStart 훅 출력이 남는지.
5. vault-graph 기존 MCP 도구 중 ID로 본문을 돌려주는 도구가 있는지, Vault claim 표에 대체 대상·날짜 열이 있는지.
