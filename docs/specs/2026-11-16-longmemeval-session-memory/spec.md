# LongMemEval 방법으로 세션 검색과 기억 품질 올리기

<!-- bake: index -->
| ID | title | status | relations | covered by | area | hash | tasks |
|---|---|---|---|---|---|---|---|
| I1 | 원문 창은 바이트 단위로 같다 |  | basis X6, X10 | A3 | global | ac598858 | 6-time-columns.md, 15-facts-index.md |
| I2 | 검색 시점에는 모델을 부르지 않는다 |  | basis X10 | A15 | global | 2d2374a9 | 14-fact-extractors.md, 17-fact-worker.md |
| I3 | 결과는 원 세션 교환을 가리킨다 |  | basis X2, X10 | A18 | 검색 | ad8a6998 | 16-facts-search.md |
| I4 | 한 검색에서 세션 하나는 결과 하나다 |  | basis X1, X4 | A1 | 검색 | 0059fc43 | 1-session-fold.md |
| I5 | 날짜 인자가 없으면 지금과 같다 |  | basis X7 | A6 | 검색 | 1705699f | 7-date-filter.md |
| I6 | 사실 키가 없거나 빼는 모드면 지금과 같다 |  | basis X10 | A18 | 검색 | 17231e43 | 16-facts-search.md |
| I7 | vault-graph는 Vault 파일을 직접 쓰지 않는다 |  | basis X9, X10, X11 | A19 | global | e58d0c5b | 17-fact-worker.md |
| I8 | 수집 훅은 사실 추출을 기다리지 않는다 |  | basis X9 | A12 | 수집 | ff209635 | 18-hook-facts.md |
| I9 | 추출용 Claude 세션은 기억에 닿지 않는다 |  | basis X9, X12 | A13, A14 | 수집 | bcdad32a | 14-fact-extractors.md, 18-hook-facts.md |
| D1 | A → C → B 순서로 구현하고, C는 B 뒤에 개정해 잰다 | decided | basis X3, X5, X24, D30, D31 | A21 | global | bb1f6254 | 4-measure-a.md, 11-measure-c.md, 22-measure-b.md |
| D2 | 같은 세션의 교환은 가장 높은 교환 결과에 접는다 | decided | basis X1, X2, I4 | A1 | 검색 | aacb69b0 | 1-session-fold.md |
| D3 | 세션 키는 Vault 안의 `<agent>:<session_id>`다 | proposed | basis X4 | A1 | 검색 | 8b868d3f | 1-session-fold.md |
| D4 | 접힌 결과는 가장 높은 교환의 점수와 자리를 그대로 쓴다 | proposed | basis X2; depends D2 | A1 | 검색 | 4f990a43 | 1-session-fold.md |
| D5 | 붙는 교환은 근거 참조만, 결과마다 3개까지다 | proposed | basis X2, I3; depends D2 | A2 | 검색 | a5bbf8e6 | 1-session-fold.md |
| D6 | 세션 단위 결과를 기본 동작으로 한다 | decided | basis X1, X3, X5; depends D2, D24 | A4 | 검색 | 167a0f1b | 2-session-default.md |
| D7 | LongMemEval 실행기는 기존 채점을 두고 서로 다른 세션 수를 더 적는다 | proposed | basis X3, X5 | A5 | 측정 | 374f295c | 3-lme-session-count.md |
| D8 | 교환마다 시작·끝 시각을 메타데이터 저장소에 색인한다 | proposed | basis X6, I1 | A3, A7 | 색인 | b58cbf05 | 6-time-columns.md |
| D9 | 범위 안 후보는 후보 단계에서 따로 모은다 | proposed | basis X6, X7, I5, D30, D31; depends D8 | A6 | 검색 | 46d508d6 | 7-date-filter.md, 23-c-event-dates.md |
| D10 | 날짜 인자는 `since`·`until`, `YYYY-MM-DD`, 양 끝 포함, 이 컴퓨터 시간대다 | decided | basis X7, X8 | A8 | 검색, 인터페이스 | 9229092a | 7-date-filter.md, 9-cli-date-args.md |
| D11 | 날짜 범위를 주면 날짜 없는 결과는 범위 밖 결과와 같이 뒤로 간다 | decided | basis X6, X7, D31; depends D9 | A6 | 검색 | 15e1bb54 | 7-date-filter.md, 23-c-event-dates.md |
| D12 | MCP 도구 설명이 상대 날짜를 오늘 기준 날짜로 바꿔 넘기라고 알린다 | decided | basis X7, D31 | A9 | 인터페이스 | 93da2eb4 | 8-mcp-date-args.md, 23-c-event-dates.md |
| D13 | CLI는 `--when` 날짜 표현 하나를 고정 규칙으로 푼다 | proposed | basis X14, X15, X17 | A8 | 인터페이스 | 035122fe | 5-date-expression.md, 9-cli-date-args.md |
| D14 | CLI에 Haiku 상대 날짜 해석을 이번에는 더하지 않는다 | decided | basis X14, X15, X16, X17, X18, I2; depends D13 | A10 | 인터페이스 | 427cc23d | 5-date-expression.md |
| D30 | 범위 판정은 교환 시각과 그 교환 사실의 사건 날짜를 함께 쓴다 | decided | basis X24, X25, D8, D21; depends D8, D28 | A6 | 검색 | 8a7619ed | 23-c-event-dates.md |
| D31 | 범위 안 결과를 먼저 채우고 남은 칸은 범위 밖 결과로 채운다 | decided | basis X24, D9, D30, I5; depends D9, D30 | A6 | 검색 | 035207bb | 23-c-event-dates.md |
| D15 | LongMemEval의 C 측정은 같은 규칙 해석기를 질문 날짜 기준으로 쓴다 | proposed | basis X8, X15; depends D13 | A11 | 측정 | 068b43b3 | 10-lme-date-rules.md |
| D16 | 수집 뒤 분리된 사실 작업자 하나가 Graph Home 대기열을 처리한다 | proposed | basis X9, I8 | A12 | 수집 | f733cd55 | 17-fact-worker.md, 18-hook-facts.md |
| D17 | Claude CLI 추출기는 로그인된 Claude Code로 돌고 자식 세션은 훅을 건너뛴다 | decided | basis X9, X12, I2, I9 | A13 | 수집 | 62bb9f2a | 14-fact-extractors.md |
| D18 | 추출기는 설정으로 고르고, 차이가 작을 때만 기본값을 로컬로 바꾼다 | proposed | basis X13 | A17, A22 | 수집, 설정 | 49c31d16 | 13-facts-config.md, 22-measure-b.md |
| D19 | 사실 추출은 기본으로 켜져 있고 `vg facts off`로 끈다 | decided | basis X13; depends D18 | A17, A25 | 설정, 측정 | aed3b1a7 | 13-facts-config.md, 19-lme-facts-args.md |
| D20 | 추출 결과는 교환 내용 해시로 Graph Home에 캐시한다 | proposed | basis X11, X13 | A16 | 수집, 측정 | d29ba3b5 | 17-fact-worker.md, 19-lme-facts-args.md |
| D21 | 사실은 줄마다 원 교환으로 접히는 키 하나로, 원문과 같은 무게로 색인한다 | decided | basis X1, X10, I1, I3, I6, X26, X27, X28, X29, X30, D23; depends D2, D28 | A18 | 색인, 검색 | c3a7334a | 16-facts-search.md, 24-fact-expansion-key.md |
| D22 | 원칙 문장을 사실 첨부 하나만 허용하도록 좁게 고친다 | decided | basis X10, I2, I7 | A20 | global | 146a8ac0 | 20-principle-text.md |
| D23 | B는 시범 20문항으로 먼저 재고, 그 뒤 multi-session·temporal-reasoning 문항으로 넓힌다 | decided | basis X5, X13, X26, X30, X31; depends D20 | A22 | 측정 | da13573a | 22-measure-b.md |
| D24 | 부분마다 세 관문을 넘어야 들인다 | proposed | basis X5, 2026-11-13-cross-encoder-rerank:D17; depends D1 | A21 | 측정 | 29403845 | 4-measure-a.md, 11-measure-c.md, 22-measure-b.md |
| D25 | vault-builder: Vault 명령 `sessions attach-facts`를 더한다 | decided | basis X11, I7 | A23 | vault-builder | a6296784 | 12-vault-builder-track.md |
| D26 | vault-builder: 첨부는 세션 part 파일 옆 `<part 이름>.facts.md`다 | decided | basis X4, X11 | A23 | vault-builder | d0fc44b6 | 12-vault-builder-track.md |
| D27 | vault-builder: 첨부 명령은 원 part 파일과 맞을 때만 쓴다 | decided | basis X11; depends D25, D26 | A23 | vault-builder | e1e4dbb8 | 12-vault-builder-track.md |
| D28 | vault-builder 계약: vault-graph는 `vault-session-facts/v1` 첨부를 이렇게 읽는다 | proposed | basis X4, X6, I1, D21; depends D26 | A18 | vault-builder, 색인 | b2890542 | 15-facts-index.md, 24-fact-expansion-key.md |
| D29 | vault-builder task는 별도 세션이 하고, 이 세션은 결과를 기다려 B를 통합한다 | decided | basis X11; depends D25, D26, D27, D28 | A24 | vault-builder, global | f3d8e06f | 21-b-integration.md |
| F1 | 한 세션이 여러 Vault에 있다 |  | basis D3 | A1 |  | 984c30b4 | 1-session-fold.md |
| F2 | 세션 파일에 `agent`나 `session_id`가 없다 |  | basis D3 | A1 |  | 597c4149 | 1-session-fold.md |
| F3 | 한 세션에서 맞은 교환이 상한보다 많다 |  | basis D5 | A2 |  | f5efea57 | 1-session-fold.md |
| F4 | 교환의 시각을 하나도 읽을 수 없다 |  | basis D8, D11 | A7 |  | 312536e0 | 6-time-columns.md |
| F5 | 날짜 인자가 틀렸다 |  | basis D10, D13 | A8 |  | dec1dfae | 5-date-expression.md, 8-mcp-date-args.md, 9-cli-date-args.md |
| F6 | 범위 안 결과가 `limit`보다 적거나 없다 |  | basis D9, D11 | A6 |  | fd8d5e19 | 7-date-filter.md |
| F7 | 추출기를 쓸 수 없다 |  | basis D16, D17, D18 | A16 |  | 3e35d1e8 | 17-fact-worker.md |
| F8 | 추출 출력이 스키마와 다르거나 없는 교환을 가리킨다 |  | basis D17, D21 | A16 |  | a5a72f8f | 17-fact-worker.md |
| F9 | Vault에 사실 첨부 명령이 없거나 거부한다 |  | basis D20, D25, D27 | A16 |  | 6de4a82e | 17-fact-worker.md |
| F10 | 여러 세션이 동시에 끝나거나 작업자가 죽는다 |  | basis D16 | A12 |  | 9730692f | 17-fact-worker.md, 18-hook-facts.md |
| F11 | 추출용 Claude 세션이 훅을 부른다 |  | basis D17 | A13, A14 |  | cf308491 | 14-fact-extractors.md, 18-hook-facts.md |
| F12 | 사실 조각만 맞고 원 교환의 창이 색인에 없다 |  | basis D21, D28 | A18 |  | 7f7ce33e | 16-facts-search.md |
| F13 | 기존 설치가 올린 뒤부터 Claude 호출을 시작한다 |  | basis D19 | A17 |  | 7059415b | 13-facts-config.md, 18-hook-facts.md |
| R1 | layer-1 세션 정답이 교환 단위면 접기가 recall을 떨어뜨릴 수 있다 |  | basis X5, D2, D5 |  |  | c22052e5 |  |
| R2 | `build_context_pack`이 붙은 근거마다 본문을 읽으면 토큰이 늘 수 있다 |  | basis D5 |  |  | e636cfdc |  |
| R3 | 벡터 저장소가 조각 id 집합으로 싸게 거르지 못할 수 있다 |  | basis D9 |  |  | 2a708d39 |  |
| R4 | LongMemEval 시각은 시간대가 없어 자정 근처 날짜가 하루 밀릴 수 있다 |  | basis X8, D10 |  |  | 45e369cd |  |
| R5 | C의 LongMemEval 효과는 작을 수 있다 |  | basis X14, D15 |  |  | 03e714b7 |  |
| R6 | 자식 `claude -p` 세션의 훅 동작을 확인하지 않았다 |  | basis X12, D17 |  |  | 4f35a4cd |  |
| R7 | B 측정 시간과 사용량 한도가 추정보다 클 수 있다 |  | basis X13, D23 |  |  | 4875e938 |  |
| R8 | 기준선 실패 분류가 A의 효과를 작게 보일 수 있다 |  | basis X3, D1, D4, D6 |  |  | 241d1fc7 |  |
| R9 | 한국어 세션에서 사실 품질과 날짜 규칙을 재지 못한다 |  | basis X17, D13, D17 |  |  | ad1e4c17 |  |
| A1 | 한 세션은 결과 하나이고 나머지 교환은 근거로 붙는다 |  | covers D2, D3, D4, I4, F1, F2 |  |  | c8bee8a5 | 1-session-fold.md |
| A2 | 붙는 교환은 참조만이고 3개까지다 |  | covers D5, F3 |  |  | fa6d4a8c | 1-session-fold.md |
| A3 | 원문 창, 조각 id, 임베딩 입력이 바뀌지 않는다 |  | covers I1, D8 |  |  | 9dfe2593 | 6-time-columns.md, 15-facts-index.md |
| A4 | 세션 단위 결과는 인자 없이 기본으로 동작한다 |  | covers D6 |  |  | fd8746c3 | 2-session-default.md |
| A5 | LongMemEval 실행기가 서로 다른 세션 수를 적고 기존 채점은 같다 |  | covers D7 |  |  | 1705fe07 | 3-lme-session-count.md |
| A6 | 범위 안 결과가 먼저 오고, 엄격 모드는 범위 밖을 넣지 않으며, 범위가 없으면 지금과 같다 |  | covers D9, D11, D30, D31, I5, F6 |  |  | 0a4a94e9 | 7-date-filter.md, 23-c-event-dates.md |
| A7 | 교환 시각은 정한 순서로 읽고, 못 읽으면 비운다 |  | covers D8, F4 |  |  | 3aea14e8 | 6-time-columns.md |
| A8 | 날짜 인자와 `--when` 규칙이 정한 형식대로 동작한다 |  | covers D10, D13, F5 |  |  | 1fd926e8 | 5-date-expression.md, 8-mcp-date-args.md, 9-cli-date-args.md |
| A9 | MCP 검색 도구 셋이 날짜 인자와 설명을 갖는다 |  | covers D12 |  |  | 8b409fc7 | 8-mcp-date-args.md, 23-c-event-dates.md |
| A10 | CLI 날짜 해석은 모델을 부르지 않는다 |  | covers D14 |  |  | b505ff3e | 5-date-expression.md |
| A11 | LongMemEval 실행기가 질문 날짜로 범위를 넘길 수 있다 |  | covers D15 |  |  | 5d9bc725 | 10-lme-date-rules.md |
| A12 | 수집 훅은 작업 파일만 두고 기다리지 않으며 작업자는 하나다 |  | covers D16, I8, F10 |  |  | fc2faca4 | 18-hook-facts.md |
| A13 | Claude 추출기는 정한 명령으로만 돌고 자식 세션은 훅을 건너뛴다 |  | covers D17, I9, F11 |  |  | 3216e3ac | 14-fact-extractors.md, 18-hook-facts.md |
| A14 | 실제 Claude Code에서 추출용 세션이 Vault에 남지 않는다 |  | covers I9, F11 |  |  | 5a04eb1c | 21-b-integration.md |
| A15 | 검색, 색인, 회상은 모델을 부르지 않는다 |  | covers I2 |  |  | f9b10fbc | 17-fact-worker.md |
| A16 | 작업자는 실패를 기록하고 캐시로 다시 부르지 않는다 |  | covers D20, F7, F8, F9 |  |  | 32245f7c | 17-fact-worker.md |
| A17 | 추출기 설정과 켜고 끄기가 정한 대로 동작한다 |  | covers D18, D19, F13 |  |  | a85325bd | 13-facts-config.md, 18-hook-facts.md |
| A25 | 테스트와 LongMemEval 실행기는 실제 추출기를 부르지 않는다 |  | covers D19 |  |  | ba627286 | 17-fact-worker.md, 19-lme-facts-args.md |
| A18 | 사실 키는 원 교환을 돌려주고 빼는 모드에서는 지금과 같다 |  | covers D21, D28, I3, I6, F12 |  |  | c8a3ac70 | 16-facts-search.md, 24-fact-expansion-key.md |
| A19 | 사실 첨부는 Vault 명령으로만 쓰고 수집한 Vault에 간다 |  | covers I7 |  |  | a42532bd | 17-fact-worker.md |
| A20 | 원칙 문장이 승인된 문장으로 바뀐다 |  | covers D22 |  |  | a1696d78 | 20-principle-text.md |
| A21 | A, C, B 각각이 세 관문을 넘는다 |  | covers D1, D24 |  |  | 5ee43a63 | 4-measure-a.md, 11-measure-c.md, 22-measure-b.md |
| A22 | B 측정은 정한 범위에서 두 추출기를 같은 문항으로 비교한다 |  | covers D23, D18 |  |  | 6d7ea051 | 22-measure-b.md |
| A23 | vault-builder: 첨부 명령이 정한 형식과 검증을 따른다 |  | covers D25, D26, D27 |  |  | 327f21da | 12-vault-builder-track.md |
| A24 | B 통합은 vault-builder 결과를 받은 뒤 실제 명령으로 돈다 |  | covers D29 |  |  | a9aa4b28 | 21-b-integration.md |
| X19 | 기준선 recall은 꺼짐 0.773, 켜짐 0.800이다 |  | basis X20 |  |  | 9c46207c |  |
| X20 | 마지막 10~11문항은 vault-builder 원본이 바뀌어 다시 돌렸다 |  |  |  |  | 71efbc90 |  |
| X21 | 상위 5개 결과에 서로 다른 세션은 평균 2.8개뿐이다 |  | basis X19 |  |  | 3d7aac2e |  |
| X22 | multi-session과 temporal-reasoning 실패의 가장 큰 원인은 같은 세션 교환의 칸 차지와 6~30위다 |  | basis X21, X14 |  |  | af3d48ac |  |
| X23 | 층1·층2 기준선은 벡터를 새로 만든 Graph Home 사본에서 쟀다 |  |  |  |  | 1a9c08a8 |  |
| X24 | 세션 날짜로만 거른 C는 LongMemEval에서 나빠졌다 |  | basis X14, X19 |  |  | 07ac8050 |  |
| X25 | 논문은 세션 날짜가 아니라 LLM이 뽑은 사건 날짜로 값을 색인해 거른다 |  |  |  |  | 4824d9e3 |  |
| X26 | 사실이 있는 40문항에서 가중치 0.5는 거의 효과가 없고 1.0 이상에서 오른다 |  | basis X22 |  |  | 16ce6819 |  |
| X27 | 논문에서는 사실을 원문과 한 키로 합칠 때가 따로 색인해 순위를 합칠 때보다 훨씬 낫다 |  |  |  |  | 3272c2d7 |  |
| X28 | 문서 확장은 일반 기법이고, 생성 문장의 잡음을 줄이면 더 낫다 |  |  |  |  | a1b2bab3 |  |
| X29 | 가중치를 두는 순위 합치기는 자기 데이터로 맞출 수 있을 때만 쓰고 기본은 같은 무게다 |  |  |  |  | 91d53cdc |  |
| X30 | 교환마다 사실을 묶은 확장 키 하나는 사실마다 키 하나보다 나빴다 |  | basis X26, X27, I1 |  |  | f9bab07a |  |
| X31 | 이번 B·C 측정은 표본이 작고 논문 조건과 다르다 |  | basis X25, X27 |  |  | ad2d04f9 |  |
| X14 | 날짜 범위 표현은 127문항 중 27문항이다 |  |  |  |  | 19ef6844 |  |
| X15 | 27문항의 표현은 모두 고정 규칙으로 풀린다 |  | basis X14 |  |  | 33ba8b78 |  |
| X16 | 규칙으로 풀 수 없는 상대 날짜 표현은 0개다 |  | basis X15 |  |  | 7baefdc5 |  |
| X17 | 한국어 날짜 표현은 이 데이터에 없다 |  |  |  |  | e43503b9 |  |
| X18 | Haiku 호출 지연은 아직 재지 않았다 |  |  |  |  | 821419be |  |
| X1 | 지금 결과 단위는 세션 교환 하나다 |  |  |  |  | 077b0388 |  |
| X2 | 교환 사본 접기가 "추가 근거" 선례다 |  |  |  |  | d1e7875a |  |
| X3 | LongMemEval 채점은 상위 5개 결과를 자른 뒤 세션을 센다 |  |  |  |  | 5a220701 |  |
| X4 | 세션 하나는 파일 여러 개일 수 있고, 묶음 키가 이미 있다 |  |  |  |  | 0d07c758 |  |
| X5 | 층1·층2와 LongMemEval 측정 도구 |  | basis 2026-11-13-cross-encoder-rerank:X15, 2026-11-13-cross-encoder-rerank:X16, 2026-11-13-cross-encoder-rerank:X18 |  |  | fed49d30 |  |
| X6 | 세션 날짜는 창 텍스트에 없고 거를 수 있는 열도 없다 |  |  |  |  | 1d1a3bcb |  |
| X7 | 검색 요청과 MCP 검색 도구에 날짜 인자가 없다 |  |  |  |  | 4d2d6af1 |  |
| X8 | LongMemEval 변환은 세션 날짜를 교환 시각으로 쓰고 질문 날짜는 버린다 |  |  |  |  | 22798a02 |  |
| X9 | 수집 훅의 시간 제한과 분리 프로세스 선례 |  |  |  |  | e91246c8 |  |
| X10 | 바꿔야 하는 원칙 문장 |  |  |  |  | 62bca349 |  |
| X11 | vault-builder에는 사실 첨부 명령이 없고 세션 파일은 바뀌면 안 된다 |  |  |  |  | 8d85d151 |  |
| X12 | Claude Code CLI 플래그 |  |  |  |  | 9642ba1c |  |
| X13 | B 측정 규모 |  |  |  |  | def7cba8 |  |
<!-- bake: index end -->

## 1. Problem

LongMemEval(arXiv 2410.10813v2)은 세션을 교환 단위로 색인하되 결과를 세션 단위로 모으고(Table 3 recall@5: 교환 0.582, 세션 0.706), 사실 키를 덧붙이고, 시간 질문을 날짜 범위로 좁히면 기억 검색이 좋아진다고 보고한다. vault-graph에는 셋 다 없다.

1. 결과 한 칸이 교환 하나라(X1), 한 세션의 교환 여러 개가 상위 5칸을 차지해 다른 정답 세션이 밀린다(X3). [가정] 이전 분석에서 layer-1 세션 질문의 상위 5개 서로 다른 세션 수는 재정렬 꺼짐 3.53, 켜짐 3.25였다. 원본은 사라졌다.
2. 세션 날짜는 창 텍스트, 저장소 열, 검색 인자 어디에도 없어 날짜로 좁힐 수 없다(X6, X7).
3. 원문과 다른 말로 묻는 질문은 원문 창에만 기댄다. 사실을 뽑는 단계도, Vault에 둘 길도 없다(X10, X11).
4. arctic-m 기준선(재정렬 꺼짐·켜짐 150문항, 실패 분류)은 진행 중이고 `research/baseline.md`에 적힌다.

확인 방법: 커밋 `de31b57`의 소스와 측정 도구, vault-builder `tools/wiki/cli.py`를 읽었다(`research/repository.md`). 날짜 표현 수는 상위 세션이 셌다(`research/relative-dates.md`). 실행하거나 잰 것은 없다.

## 2. Intent

사용자는 LongMemEval의 방법으로 세션 검색과 기억 품질을 올리고, A(세션 단위 결과) → C(날짜 범위) → B(사실 키) 순서로 하기로 정했다(2026-11-16).

1. 세션 질문의 상위 결과가 서로 다른 세션으로 채워지고 토큰 예산은 지킨다.
2. 에이전트가 "지난주"를 날짜로 넘기면 그 기간 세션만 찾는다. CLI도 날짜로 좁힐 수 있다.
3. 수집이 끝난 세션에서 Claude Code 로그인으로 날짜 붙은 사실을 뽑아 Vault 도구로 세션 옆에 두고, 검색은 사실을 원 세션을 찾는 열쇠로만 쓴다. API 키는 쓰지 않는다.
4. 각 부분은 LongMemEval 유형별, layer-1 세션 recall(dev·test), layer 2로 재서 나빠지지 않을 때만 들인다.
5. 사실 첨부의 Vault 쓰기 길은 vault-builder 저장소의 별도 세션이 구현하고, 이 세션은 그 결과를 기다려 B를 통합한다.
6. [가정] 검색 시점에는 모델 호출이 없다(사용자가 고친 원칙 문장 "검색 시점에는 LLM이 없다").

## 3. Non-goals

1. 96단어 창 매칭, 조각 경계, 임베딩 입력 변경.
2. 세션 전체 본문을 결과에 싣는 일.
3. 사실을 기억 내용(답, 요약)으로 돌려주는 일.
4. LongMemEval의 답 생성 단계. 검색 recall만 잰다.
5. "며칠 전", "어느 것이 먼저" 같은 날짜 비교 추론(X14).
6. 사실의 검토 대기열과 wiki 발행.
7. vault-builder 코드를 이 worktree에서 고치는 일.
8. 다른 에이전트(Codex 등) 세션의 사실 추출.
9. README에 vault-graph가 토큰을 쓰게 되는 경우를 정리하는 일. 사용자가 backlog로 남겼다(2026-11-16).

## 4. Design

기준선(`research/baseline.md`)과 비교해 A, C, B를 하나씩 들인다.

A. 세션 단위 결과(`retrieval/search/evidence_result_assembly.py`):

1. `resolve_results`에서 `_fold_exchange_copies` 뒤에 `_fold_session_exchanges`를 둔다. 같은 Vault, 같은 세션 키의 교환을 가장 높은 교환에 접고 나머지를 `_ParentGroup.session_exchanges`에 둔다.
2. `_result_for_group`은 자신, 사본, 같은 세션 교환 순으로 근거를 붙이고 정보 경고 `session_exchanges_attached`를 단다.
3. 접기는 slice와 재정렬 앞이라 칸이 비면 기존 refill이 후보를 더 모은다.
4. `longmemeval_run`은 상위 5개의 서로 다른 세션 수를 더 적는다.

C. 날짜 범위:

1. 교환 조각마다 시작·끝 시각을 `chunks` 표 새 열에 둔다. 메타데이터만 다시 색인하고 벡터는 다시 만들지 않는다.
2. `SearchRequest`에 `since`, `until`을 더하고 후보 단계에서 거른다.
3. MCP `search_vault`, `ask_vault`, `build_context_pack`에 같은 인자를 더하고 설명으로 에이전트에게 날짜 계산을 맡긴다. `vg search`는 `--since`, `--until`, 규칙으로 푸는 `--when`을 받는다.
4. `longmemeval_convert`가 `question_date`를 읽고, `longmemeval_run`이 같은 규칙으로 범위를 넘기는 선택 인자를 받는다.

B. 사실 키:

1. `vg hook capture`가 수집을 마치면 Graph Home `facts/queue/`에 작업 파일을 두고 분리 작업자를 띄운다.
2. 작업자는 캐시에 없는 교환만 추출기 포트 `FactExtractor`(Claude CLI 기본, `llama-server`)에 넘긴다.
3. 작업자는 Vault 도구의 새 명령으로 첨부를 쓴다.
4. 색인은 사실 하나를 원 교환 `parent_key`를 가진 `derived` 조각 하나로 만든다. 결과는 원 교환이다.
5. 원칙 문장(SPEC 원칙1·4, AGENTS.md Project Boundary, SPEC B-2 (5))을 고친다.

vault-builder 저장소 쪽은 area `vault-builder` 블록이 task이고 이 worktree에서 구현하지 않는다.

### I1. 원문 창은 바이트 단위로 같다
- by: 사람 (brief A "96단어 창 매칭은 그대로", SPEC B-2 (1))
- area: global
- basis: X6, X10

세션 원문 창의 `text`, 조각 id, `source_locators`, 임베딩 입력은 바뀌지 않는다. 날짜와 사실은 새 열과 새 조각으로만 더한다.

### I2. 검색 시점에는 모델을 부르지 않는다
- by: 사람 (brief "바꿔야 하는 원칙 문장": "검색 시점에는 LLM이 없다")
- area: global
- basis: X10

검색, 색인, 회상, MCP 검색 도구는 Claude CLI나 `llama-server`를 부르지 않는다. 모델 호출은 사실 작업자 안에서만 한다.

### I3. 결과는 원 세션 교환을 가리킨다
- by: 사람 (brief B "사실을 기억 내용으로 돌려주지 않는다", SPEC B-2 (2))
- area: 검색
- basis: X2, X10

결과의 첫 근거와 발췌는 세션 원문 교환이다. 사실 텍스트는 발췌, 제목, 근거 경로가 되지 않는다.

### I4. 한 검색에서 세션 하나는 결과 하나다
- by: 사람 (brief A "결과 칸을 세션 단위로 채운다")
- area: 검색
- basis: X1, X4

세션 키가 있는 교환은 Vault마다 세션 키 하나에 결과 하나다. 근거 참조는 접기 전과 같고 붙는 자리만 바뀐다. 근거 상한으로 잘린 교환만 예외다.

### I5. 날짜 인자가 없으면 지금과 같다
- by: 가정 (brief C의 선택 인자에서 도출)
- area: 검색
- basis: X7

`since`, `until`, `--when`이 없으면 후보, 순서, 경고, `stage_trace`가 변경 전과 같다.

### I6. 사실 키가 없거나 빼는 모드면 지금과 같다
- by: 사람 (SPEC B-2 (4))
- area: 검색
- basis: X10

첨부가 없는 Vault나 사실 조각을 빼는 모드의 결과는 B 전과 같다. 결정성 시험과 비교 측정은 이 모드로도 돈다.

### I7. vault-graph는 Vault 파일을 직접 쓰지 않는다
- by: 사람 (brief B "Vault 도구가 … 첨부 파일로 쓴다")
- area: global
- basis: X9, X10, X11

첨부는 Vault 도구 명령만 쓰고, Vault는 그 세션을 수집한 Vault다. 세션 원문 파일은 고치지 않는다.

### I8. 수집 훅은 사실 추출을 기다리지 않는다
- by: 사람 (brief B "훅은 25초 제한")
- area: 수집
- basis: X9

훅은 작업 파일을 쓰고 프로세스를 띄울 뿐이다. 수집 결과와 종료 코드는 B 전과 같다.

### I9. 추출용 Claude 세션은 기억에 닿지 않는다
- by: 사람 (brief B "자식 세션에서 … 캡처도 recall도 하지 않게")
- area: 수집
- basis: X9, X12

추출용 `claude -p` 세션에서 `vg hook capture`는 수집하지 않고 `vg hook session-start`는 회상하지 않는다.

## 5. Decisions

### D1. A → C → B 순서로 구현하고, C는 B 뒤에 개정해 잰다
- by: 사람 (brief 목표, 2026-11-16; C 개정 승인 2026-11-16 "제안방향으로 합니다")
- status: decided
- area: global
- basis: X3, X5, X24, D30, D31

A는 LLM이 없고 측정 문제(X3)에 바로 닿는다. B는 사용량과 vault-builder 변경이 필요해 마지막이다. 앞 부분의 측정 결과가 다음 부분의 기준선이다. 세션 날짜로만 거른 첫 C는 LongMemEval에서 나빠졌으므로(X24) C는 B의 사건 날짜를 쓰도록 고치고(D30, D31) B 시범 문항과 같이 잰다.

### D2. 같은 세션의 교환은 가장 높은 교환 결과에 접는다
- by: 사람 (brief A "2번째 이후 교환은 … 추가 근거로 접는다")
- status: decided
- area: 검색
- basis: X1, X2, I4

`_fold_session_exchanges`가 사본 접기(X2)와 같은 방식으로 낮은 교환을 `session_exchanges`에 옮긴다. 경고는 붙은 교환 수를 적는다.

### D3. 세션 키는 Vault 안의 `<agent>:<session_id>`다
- by: 가정 (X4의 기존 세션 묶음 키)
- status: proposed
- area: 검색
- basis: X4

수집마다 part 파일이 늘어 문서 단위로는 한 세션이 여러 칸이 된다. 기존 `session_group_key`로 part들을 묶는다. 키가 없는 파일은 교환마다 결과다.

### D4. 접힌 결과는 가장 높은 교환의 점수와 자리를 그대로 쓴다
- by: 가정 (X2와 같은 규칙)
- status: proposed
- area: 검색
- basis: X2
- depends: D2

점수를 더하면 긴 세션이 올라 문서 검색과 순위가 섞인다. 합산은 기준선에서 근거가 보이면 다시 정한다.

### D5. 붙는 교환은 근거 참조만, 결과마다 3개까지다
- by: 사람 (brief A "토큰 예산은 지킨다"); 가정 (상한 3)
- status: proposed
- area: 검색
- basis: X2, I3
- depends: D2

붙는 교환은 경로와 교환 줄 범위뿐이고 발췌는 가장 높은 창 하나다. 상한을 넘은 수는 경고에 적는다.

### D6. 세션 단위 결과를 기본 동작으로 한다
- by: 사람 (spec gate 2026-11-16 결과 단위 질문의 답: "권장안으로 정합니다")
- status: decided
- area: 검색
- basis: X1, X3, X5
- depends: D2, D24

모드로 두면 에이전트가 고를 근거가 없고 측정과 실제 사용이 달라진다. 세션 교환에만 닿아 layer 2는 거의 안 바뀐다고 본다. D24 관문을 못 넘으면 들이지 않는다.

### D7. LongMemEval 실행기는 기존 채점을 두고 서로 다른 세션 수를 더 적는다
- by: 가정 (brief A "현재 측정 문제"에서 도출)
- status: proposed
- area: 측정
- basis: X3, X5

`recall_all_at_5`, `recall_any_at_5` 정의는 그대로다. 문항별 서로 다른 세션 수를 `results.jsonl`, 유형별 평균을 `summary.json`에 더한다.

### D8. 교환마다 시작·끝 시각을 메타데이터 저장소에 색인한다
- by: 사람 (brief C "각 세션의 날짜를 색인한다"); 가정 (교환 단위, 읽는 순서)
- status: proposed
- area: 색인
- basis: X6, I1

읽는 순서는 교환 메타 줄 `started`·`ended`, frontmatter `first_turn_at`, 파일 이름 날짜(그날 하루)다. 교환 단위라 여러 날 세션도 맞게 거른다. 스키마 판을 올려 메타데이터만 다시 색인한다.

### D9. 범위 안 후보는 후보 단계에서 따로 모은다
- by: 가정 (결과 단계에서 거르면 후보가 범위 밖으로 찰 수 있다); 개정 2026-11-16(D31)
- status: proposed
- area: 검색
- basis: X6, X7, I5, D30, D31
- depends: D8

메타데이터 저장소가 범위 안 조각 id(D30)를 주고, 키워드·벡터 검색이 그 안에서 범위 안 결과를 만든다. 하루라도 겹치면 범위 안이다. 후보 수 공식과 refill은 그대로다. 이 결과를 어떻게 쓰는지는 D31이다.

### D10. 날짜 인자는 `since`·`until`, `YYYY-MM-DD`, 양 끝 포함, 이 컴퓨터 시간대다
- by: 사람 (spec gate 2026-11-16: "이대로, 날짜 없는 결과 빼기")
- status: decided
- area: 검색, 인터페이스
- basis: X7, X8

CLI는 `--since`, `--until`이다. 한쪽만 줘도 된다. 사용자의 "지난주"는 사용자 달력 기준이므로 저장한 UTC 시각을 이 컴퓨터 시간대로 바꿔 비교한다.

### D11. 날짜 범위를 주면 날짜 없는 결과는 범위 밖 결과와 같이 뒤로 간다
- by: 사람 (spec gate 2026-11-16: "이대로, 날짜 없는 결과 빼기"; C 개정 승인 2026-11-16로 D31의 앞세우기가 대신한다)
- status: decided
- area: 검색
- basis: X6, X7, D31
- depends: D9

wiki 페이지처럼 날짜 없는 결과는 범위 안 결과 뒤에 온다. `date_unknown_excluded` 경고는 엄격 모드(D31)에서만 붙는다.

### D12. MCP 도구 설명이 상대 날짜를 오늘 기준 날짜로 바꿔 넘기라고 알린다
- by: 사람 (brief C, 추가 지시 1 "MCP 경로는 호출 에이전트가 날짜 범위를 채운다")
- status: decided
- area: 인터페이스
- basis: X7, D31

세 도구 설명에 "상대 표현은 오늘 날짜로 `since`·`until`을 계산해 넘기고 질의에서는 뺀다"는 문장과 예시 하나를 더한다. 범위는 대화한 시기나 사건이 일어난 시기 모두 가리킬 수 있고, 범위 안 결과가 먼저 오고 나머지가 뒤에 온다고 적는다(D31). MCP 경로는 날짜 표현을 해석하지 않는다.

### D13. CLI는 `--when` 날짜 표현 하나를 고정 규칙으로 푼다
- by: 사람 (brief C "CLI에서는 … 규칙으로 해석한다"); 가정 (`--when`, 한국어 규칙)
- status: proposed
- area: 인터페이스
- basis: X14, X15, X17

규칙은 명시 날짜·월, X15의 영어 표현, 한국어 기본 표현("지난주", "5월에", "N일 전", "지난달")을 오늘 기준 범위로 바꾼다. 순수 함수 `resolve_date_expression(text, today)`로 두어 측정 도구도 쓴다. 질의 본문은 읽지 않는다. 몰래 범위가 생기면 결과가 줄어든 이유를 알 수 없다.

### D14. CLI에 Haiku 상대 날짜 해석을 이번에는 더하지 않는다
- by: 사람 (spec gate 2026-11-16: "더하지 않는다")
- status: decided
- area: 인터페이스
- basis: X14, X15, X16, X17, X18, I2
- depends: D13

temporal 127문항 중 날짜 범위 표현은 27(21%), 규칙으로 못 푸는 것은 0이라 Haiku 이득이 0이다. 지연은 아직 재지 않았다. 실제 사용에서 규칙 실패가 쌓이면 지연을 재고 다시 정한다. 더해도 규칙이 실패한 CLI `--when`에서만 부르고 MCP와 검색 서비스에는 넣지 않는다(I2).

### D30. 범위 판정은 교환 시각과 그 교환 사실의 사건 날짜를 함께 쓴다
- by: 사람 (C 개정 승인 2026-11-16 "제안방향으로 합니다")
- status: decided
- area: 검색
- basis: X24, X25, D8, D21
- depends: D8, D28

교환은 그 시각이 범위와 겹치거나, 그 교환을 가리키는 사실 조각(D21) 중 하나의 날짜가 범위 안이면 범위 안이다. 사실 날짜는 추출 프롬프트 규칙대로 일이 일어난 날이고, 없으면 교환 날짜다. 사실 추출을 끈 Vault에서는 교환 시각만 쓴다.

### D31. 범위 안 결과를 먼저 채우고 남은 칸은 범위 밖 결과로 채운다
- by: 사람 (C 개정 승인 2026-11-16 "제안방향으로 합니다")
- status: decided
- area: 검색
- basis: X24, D9, D30, I5
- depends: D9, D30

범위를 주면 범위 안 결과(D9)를 순서대로 넣고, 칸이 남으면 범위 없는 같은 검색의 결과 중 아직 없는 것을 순서대로 넣는다. 두 사건을 비교하는 질문에서 범위 밖 정답 세션을 지우지 않기 위해서다. 비교 측정을 위해 범위 밖을 넣지 않는 엄격 모드를 검색 요청과 `vg search --date-strict`에 둔다. 범위가 없으면 지금과 같다(I5).

### D15. LongMemEval의 C 측정은 같은 규칙 해석기를 질문 날짜 기준으로 쓴다
- by: 가정 (X15에서 27문항 모두 규칙으로 풀림)
- status: proposed
- area: 측정
- basis: X8, X15
- depends: D13

`longmemeval_run --date-rules`가 질문을 `resolve_date_expression(질문, 질문 날짜)`에 넣어 범위가 나오면 `--since`·`--until`을 넘긴다. CLI 경로를 재고 MCP 경로는 재지 않는다.

### D16. 수집 뒤 분리된 사실 작업자 하나가 Graph Home 대기열을 처리한다
- by: 사람 (brief B "분리된 프로세스 … catch-up을 본뜬다"); 가정 (대기열)
- status: proposed
- area: 수집
- basis: X9, I8

훅은 수집이 `written`일 때만 작업 파일(수집 Vault, part 경로)을 쓰고, `logs/facts-worker.lock`이 비어 있으면 작업자를 분리해 띄운다. 작업자는 대기열이 빌 때까지 처리한다. 교환은 정규화 사본이 아니라 part 파일에서 읽는다. `attach-facts`가 교환 id와 `source_sha256`을 그 파일로 검사하고, 그 본문은 이미 Vault 가림을 거쳤기 때문이다(구현 중 2026-11-16 변경). 죽어도 다음 수집 때 이어 한다.

### D17. Claude CLI 추출기는 로그인된 Claude Code로 돌고 자식 세션은 훅을 건너뛴다
- by: 사람 (brief B, "API 키는 쓰지 않는다")
- status: decided
- area: 수집
- basis: X9, X12, I2, I9

명령은 `claude -p --model claude-sonnet-5-5 --json-schema <사실 스키마> --no-session-persistence --tools "" --strict-mcp-config`이고 `--bare`와 `ANTHROPIC_API_KEY`는 쓰지 않는다. 자식 세션은 믿을 수 없는 세션 원문을 읽으므로 내장 도구와 MCP 서버를 하나도 주지 않는다(구현 중 2026-11-16 추가). 자식 환경에 `VAULT_GRAPH_FACTS_CHILD=1`을 주면 두 훅이 아무 일 없이 0으로 끝난다. 출력은 사실마다 문장, 날짜, 교환 id이고 세션의 언어를 따른다.

### D18. 추출기는 설정으로 고르고, 차이가 작을 때만 기본값을 로컬로 바꾼다
- by: 사람 (brief B "추출기는 고를 수 있게 … 차이가 작을 때만"); 가정 (설정 파일, 차이 기준)
- status: proposed
- area: 수집, 설정
- basis: X13

Graph Home `configs/facts.json`은 `version`, `enabled`, `extractor`(`claude`, `llama-server`), `endpoint`, `model`을 갖는다. 로컬은 `llama-server`와 `$HOME/llm/models/Qwen3.5-27B-Q4_K_M.gguf`다. 같은 문항에서 로컬 `recall_all_at_5`가 0.02 이하로 낮을 때만 기본값을 바꾼다. 어댑터는 `interface/composition/adapters/`에 둔다.

### D19. 사실 추출은 기본으로 켜져 있고 `vg facts off`로 끈다
- by: 사람 (spec gate 2026-11-16: "기본 켠다")
- status: decided
- area: 설정, 측정
- basis: X13
- depends: D18

`configs/facts.json`이 없으면 `claude` 추출기로 켜진 것으로 본다. `vg facts off`는 `enabled: false`를 쓰고, `vg facts on [--extractor …]`과 `vg facts status`(대기열, 실패)는 그대로 둔다. 기존 설치는 올린 뒤 수집되는 세션부터 추출하고 지난 세션은 거슬러 처리하지 않는다. 테스트는 가짜 추출기만 쓴다. `longmemeval_run`은 B를 재는 실행이 아니면 작업 공간 Graph Home마다 `enabled: false`를 쓴다.

### D20. 추출 결과는 교환 내용 해시로 Graph Home에 캐시한다
- by: 가정 (brief "내용 해시로 캐시 [가정]")
- status: proposed
- area: 수집, 측정
- basis: X11, X13

키는 (추출기, 모델, 스키마 판, 교환 내용 해시)다. 새 part에 다시 나온 교환은 다시 부르지 않는다. LongMemEval은 캐시 폴더를 실행기 인자로 넘겨 문항 사이에 같이 쓴다.

### D21. 사실은 줄마다 원 교환으로 접히는 키 하나로, 원문과 같은 무게로 색인한다
- by: 사람 (brief B "추가 키로만 색인"; 2026-11-18 옵션3 승인 "옵션3 으로 승인합니다")
- status: decided
- area: 색인, 검색
- basis: X1, X10, I1, I3, I6, X26, X27, X28, X29, X30, D23
- depends: D2, D28

사실 줄 하나가 `parent_key` `<session_id>:<exchange_id>`인 사실 조각 하나다. 가중치는 원문과 같은 1.0이다(X29, 업계 기본). 처음 정한 0.5는 측정에서 효과가 거의 없었고(X26), 교환마다 사실을 묶은 확장 키 하나는 오히려 나빴다(X30). 이 값과 방식은 40문항에서 고른 것이 아니라 기본값이며, 효과 판단은 충분한 표본의 별도 측정으로 미룬다(D23). 사실만 맞은 단위는 원 교환의 첫 창으로 바꿔 발췌와 근거를 원문에서 가져온다(그때만 좁게 한 번 읽는다). `include_fact_keys=false`면 사실 조각을 후보에서 뺀다.

### D22. 원칙 문장을 사실 첨부 하나만 허용하도록 좁게 고친다
- by: 사람 (brief "바꿔야 하는 원칙 문장"; spec gate 2026-11-16: "세션 사실 첨부만 예외")
- status: decided
- area: global
- basis: X10, I2, I7

1. 원칙1: "검색, 색인, 회상에서는 LLM을 부르지 않는다. 수집 뒤에만 로그인된 Claude Code나 로컬 모델로 세션 사실을 뽑는다(기본 켜짐, `vg facts off`로 끈다). API 키는 쓰지 않는다."
2. 원칙4와 AGENTS.md 쓰기 길: 다섯째 "사실 첨부(Vault 명령이 세션 옆에 쓴다)"를 더한다.
3. AGENTS.md "machine-made content": "세션 사실 첨부만 예외이고 원 세션을 찾는 열쇠로만 색인한다"를 붙인다.
4. B-2 (5): 세션 사실 첨부만 예외로 둔다.

### D23. B는 시범 20문항으로 먼저 재고, 그 뒤 multi-session·temporal-reasoning 문항으로 넓힌다
- by: 사람 (spec gate 2026-11-16: "시범 20문항 뒤 두 유형")
- status: decided
- area: 측정
- basis: X5, X13, X26, X30, X31
- depends: D20

150문항 전부는 호출 약 6,600번, 18~37시간이다(X13). 두 유형 20문항(호출 약 960번)을 두 추출기로 먼저 재고, 효과가 보이면 150문항 안의 두 유형 전체로 넓힌다. 문항 수는 `research/baseline.md`로 정한다. 시간은 기계가 한가할 때 잰다. 결과(2026-11-18): 시범 20문항은 A만으로 0.90이라 B 효과가 보이지 않았고, A가 틀린 20문항을 더 쟀다. 이 40문항은 대표 표본이 아니고 논문 조건(LongMemEval_M, 질문마다 대화 약 500개)과 달라, 사실 키와 날짜 범위의 효과는 이번 변경에서 판단하지 않는다(X26, X30, X31). 충분한 표본의 측정은 backlog `LME-01`로 남긴다(사람 승인 2026-11-18 "옵션3 으로 승인합니다").

### D24. 부분마다 세 관문을 넘어야 들인다
- by: 사람 (brief 완료 조건); 가정 (비교 기준은 재정렬 꺼짐)
- status: proposed
- area: 측정
- basis: X5, 2026-11-13-cross-encoder-rerank:D17
- depends: D1

LongMemEval 150문항 유형별 값을 기준선과 나란히 적는다. layer-1 세션 recall@5는 dev·test 모두 기준선 이상, layer 2 recall@5는 0.95 이상이다. 기준선은 재정렬 기본값인 꺼짐이고 켜짐도 적는다. 보고서는 `docs/design/reports/2026-11-longmemeval-session-memory.md`다.

### D25. vault-builder: Vault 명령 `sessions attach-facts`를 더한다
- by: 사람 (추가 지시 2, vault-builder 저장소 소속; spec gate 2026-11-16: "이대로 한다")
- status: decided
- area: vault-builder
- basis: X11, I7

vault-builder 저장소 task다. `tools/wiki/cli.py sessions attach-facts --session <part 경로> --facts <JSON> --json`. JSON은 `schema`, `session_id`, `extractor`, `model`, `source_sha256`, 사실 목록(문장, 날짜, 교환 id)이다. 결과는 마지막 줄 JSON `status`(`written`, `exists`, `rejected`)와 경로다.

### D26. vault-builder: 첨부는 세션 part 파일 옆 `<part 이름>.facts.md`다
- by: 사람 (brief B "세션 원문 옆 첨부 파일"; spec gate 2026-11-16: "이대로 한다")
- status: decided
- area: vault-builder
- basis: X4, X11

vault-builder 저장소 task다. part 파일 하나에 첨부 하나이고 한 번 쓰면 바뀌지 않는다. frontmatter는 `schema: vault-session-facts/v1`, `agent`, `session_id`, `part`, `source`, `source_sha256`, `extractor`, `model`, `generated_at`이다. 본문은 줄마다 `- <YYYY-MM-DD> <사실> (exchange <id>)`다.

### D27. vault-builder: 첨부 명령은 원 part 파일과 맞을 때만 쓴다
- by: 사람 (spec gate 2026-11-16: "이대로 한다")
- status: decided
- area: vault-builder
- basis: X11
- depends: D25, D26

vault-builder 저장소 task다. part 없음, sha256 불일치, 다른 `session_id`, 없는 교환 id, 빈 문장이나 400자 초과, 날짜 오류, 비밀값 가림 위반이면 `rejected`다. 첨부가 있으면 `exists`이고 덮어쓰지 않는다. `git-check`와 `capture`는 `.facts.md`를 세션 파일로 세지 않는다. Vault `AGENTS.md` 규칙1 예외에 첨부를 더한다.

### D28. vault-builder 계약: vault-graph는 `vault-session-facts/v1` 첨부를 이렇게 읽는다
- by: 사람 (추가 지시 2 "vault-graph가 읽는 방법"); 가정 (계약 내용)
- status: proposed
- area: vault-builder, 색인
- basis: X4, X6, I1, D21
- depends: D26

계약 문서는 `docs/contracts/vault-session-facts-v1.md`다. vault-graph는 `schema`로 첨부를 알아보고 세션 묶음 규칙에는 넣지 않으며, 줄마다 사실 조각 하나를 만든다(D21. `parent_key`는 원 교환, 시각은 줄 날짜). 모르는 판은 경고 하나와 함께 색인하지 않는다.

### D29. vault-builder task는 별도 세션이 하고, 이 세션은 결과를 기다려 B를 통합한다
- by: 사람 (추가 지시 2, 2026-11-16)
- status: decided
- area: vault-builder, global
- basis: X11
- depends: D25, D26, D27, D28

D25~D28이 승인되면 상위 세션이 그 brief로 vault-builder 저장소에서 별도 세션을 연다. 이 세션은 A, C와 B의 vault-graph 쪽을 먼저 하고, 결과가 들어오면 실제 명령에 붙여 잰다.

## 6. Failure and boundary behavior

### F1. 한 세션이 여러 Vault에 있다
- basis: D3

Vault마다 따로 묶는다. 같은 내용이면 기존 Vault 간 중복 접기가 처리한다.

### F2. 세션 파일에 `agent`나 `session_id`가 없다
- basis: D3

접지 않고 교환마다 결과다.

### F3. 한 세션에서 맞은 교환이 상한보다 많다
- basis: D5

높은 3개만 붙이고 경고에 전체 수와 생략 수를 적는다.

### F4. 교환의 시각을 하나도 읽을 수 없다
- basis: D8, D11

시각 열이 비고 색인 경고가 남는다. 범위 검색에서는 날짜 없는 결과로 빠진다.

### F5. 날짜 인자가 틀렸다
- basis: D10, D13

형식 오류, `since` > `until`, 못 푸는 `--when`, `--when`과 `--since`·`--until` 동시 사용은 MCP 입력 오류, CLI 종료 코드 2와 이유 한 줄이다. 범위 없이 검색하지 않는다.

### F6. 범위 안 결과가 `limit`보다 적거나 없다
- basis: D9, D11

있는 만큼만 준다. 없으면 빈 목록과 정보 경고 `date_range_empty`다.

### F7. 추출기를 쓸 수 없다
- basis: D16, D17, D18

`claude` 없음, 로그인 안 됨, 사용량 한도, 시간 초과, `llama-server` 무응답이면 작업을 대기열에 두고 `logs/facts-failures.json`에 적는다. 30분 뒤 다시 시도한다. 훅과 검색에는 영향이 없다.

### F8. 추출 출력이 스키마와 다르거나 없는 교환을 가리킨다
- basis: D17, D21

스키마 오류는 그 작업의 실패로 기록한다. 없는 교환 id나 빈 문장의 사실만 버린다. 남은 사실이 없으면 첨부를 쓰지 않고 캐시에 "사실 없음"을 남긴다.

### F9. Vault에 사실 첨부 명령이 없거나 거부한다
- basis: D20, D25, D27

명령이 없으면 `facts_writer_missing`을 기록하고, Vault가 갱신된 뒤 캐시로 다시 부르지 않고 쓴다. `rejected`는 이유를 남기고 닫고, `exists`는 성공이다.

### F10. 여러 세션이 동시에 끝나거나 작업자가 죽는다
- basis: D16

훅은 작업 파일만 더하고 잠금이 잡혀 있으면 띄우지 않는다. 죽은 작업자의 남은 작업은 다음 작업자가 처리한다.

### F11. 추출용 Claude 세션이 훅을 부른다
- basis: D17

`VAULT_GRAPH_FACTS_CHILD=1`이면 두 훅이 빈 출력과 0으로 끝나, 훅 실행기는 직접 수집이나 `recall.sh`로 넘어가지 않는다.

### F12. 사실 조각만 맞고 원 교환의 창이 색인에 없다
- basis: D21, D28

사실 조각은 버리고 경고 `fact_source_missing`을 붙인다. 사실 텍스트로 답하지 않는다.

### F13. 기존 설치가 올린 뒤부터 Claude 호출을 시작한다
- basis: D19

설정 파일이 없는 기존 설치도 켜짐이 된다. 올린 뒤 처음 사실 작업을 띄우는 훅이 stderr에 "사실 추출이 켜졌고 `vg facts off`로 끈다"는 안내를 한 번 쓰고, Graph Home에 안내한 기록을 남긴다. 지난 세션은 처리하지 않는다. 깨진 설정 파일은 꺼짐으로 본다.

## 7. What could be wrong

### R1. layer-1 세션 정답이 교환 단위면 접기가 recall을 떨어뜨릴 수 있다
- basis: X5, D2, D5

`evaluate_search`가 붙은 근거까지 세는지 확인하지 않았다. 첫 근거만 세면 붙은 정답이 놓친 것으로 나온다. 채점을 먼저 읽고 필요하면 두 방식 값을 적는다.

### R2. `build_context_pack`이 붙은 근거마다 본문을 읽으면 토큰이 늘 수 있다
- basis: D5

context pack이 근거를 몇 개까지 펼치는지 확인하지 않았다. 다 펼치면 첫 근거만 펼치게 막는다.

### R3. 벡터 저장소가 조각 id 집합으로 싸게 거르지 못할 수 있다
- basis: D9

못 하면 후보를 더 받아 뒤에서 거르고, 좁은 범위에서 후보가 모자랄 수 있다. 검색 p95 1초를 넘는지 잰다.

### R4. LongMemEval 시각은 시간대가 없어 자정 근처 날짜가 하루 밀릴 수 있다
- basis: X8, D10

시간대 없는 값이 UTC로 적힌다. 측정은 `TZ=UTC`로 돌린다.

### R5. C의 LongMemEval 효과는 작을 수 있다
- basis: X14, D15

범위로 좁힐 수 있는 temporal 문항은 127 중 27이고 150문항 표본에는 15문항이다. 개정 C는 B 시범 문항 안에서만 잴 수 있어 표본이 더 작다. MCP 경로 효과는 재지 못한다.

### R6. 자식 `claude -p` 세션의 훅 동작을 확인하지 않았다
- basis: X12, D17

`--no-session-persistence` 세션에서 훅이 불리는지, vault-builder 실행기가 다른 길로 직접 수집하는지 모른다. 실제 실행으로 본다.

### R7. B 측정 시간과 사용량 한도가 추정보다 클 수 있다
- basis: X13, D23

호출당 시간과 로컬 Qwen 처리 시간은 추정이다. 한도에 걸리면 며칠이 걸린다. 시범에서 먼저 본다.

### R8. 기준선 실패 분류가 A의 효과를 작게 보일 수 있다
- basis: X3, D1, D4, D6

"같은 세션 교환이 칸 차지" 실패가 적으면 A의 이득도 작다. 기준선이 나오면 D6과 D4를 다시 본다.

### R9. 한국어 세션에서 사실 품질과 날짜 규칙을 재지 못한다
- basis: X17, D13, D17

LongMemEval은 영어뿐이라 한국어는 단위 테스트로만 확인한다.

## 8. Acceptance criteria

### A1. 한 세션은 결과 하나이고 나머지 교환은 근거로 붙는다
- covers: D2, D3, D4, I4, F1, F2
- check: tests/test_session_result_fold.py
- evidence:

한 세션 교환 셋과 다른 세션 교환 하나면 결과는 둘이고, 첫 결과는 가장 높은 교환의 자리와 점수, 근거 순서는 자신, 사본, 같은 세션 교환이다. 두 part 파일의 같은 세션도 접힌다. 다른 Vault와 키 없는 파일은 접히지 않는다.

### A2. 붙는 교환은 참조만이고 3개까지다
- covers: D5, F3
- check: tests/test_session_result_fold.py
- evidence:

맞은 교환이 다섯이면 붙는 근거는 셋이고 경고에 5와 생략 1이 있다. `summary`는 가장 높은 창 발췌 하나다.

### A3. 원문 창, 조각 id, 임베딩 입력이 바뀌지 않는다
- covers: I1, D8
- check: tests/test_session_exchange_v2_chunker.py, tests/test_session_facts_index.py
- evidence:

변경 전 고정값과 창 `text`, 조각 id, `source_locators`, 임베딩 입력이 바이트 단위로 같고, 첨부가 옆에 있어도 같다. 시각 열은 메타 줄 값이다.

### A4. 세션 단위 결과는 인자 없이 기본으로 동작한다
- covers: D6
- check: tests/test_cli_search.py, tests/test_mcp_tools.py
- evidence:

`vg search --mode evidence`와 `search_vault`가 인자 없이 접힌 결과를 준다.

### A5. LongMemEval 실행기가 서로 다른 세션 수를 적고 기존 채점은 같다
- covers: D7
- check: tests/test_longmemeval_run_session_count.py
- evidence:

같은 입력의 `recall_all_at_5`, `recall_any_at_5`가 변경 전과 같고 세션 수가 문항별·유형별로 적힌다.

### A6. 범위 안 결과가 먼저 오고, 엄격 모드는 범위 밖을 넣지 않으며, 범위가 없으면 지금과 같다
- covers: D9, D11, D30, D31, I5, F6
- check: tests/test_retrieval_service_search.py
- evidence:

교환 시각이 범위 밖이어도 그 교환의 사실 날짜가 범위 안이면 범위 안 결과다. 범위 안 결과가 먼저 오고 남은 칸은 범위 밖·날짜 없는 결과다. 엄격 모드에서는 범위 안 결과만 남고 날짜 없는 결과는 `date_unknown_excluded`에 개수가 있으며, 결과가 없으면 `date_range_empty`다. 범위가 없으면 후보, 순서, 경고, `stage_trace`가 변경 전과 같다.

### A7. 교환 시각은 정한 순서로 읽고, 못 읽으면 비운다
- covers: D8, F4
- check: tests/test_session_exchange_v2_chunker.py
- evidence:

메타 줄, `first_turn_at`, 파일 이름 순으로 쓰이고, 셋 다 없으면 열이 비고 경고 하나다.

### A8. 날짜 인자와 `--when` 규칙이 정한 형식대로 동작한다
- covers: D10, D13, F5
- check: tests/test_date_expression.py, tests/test_cli_search.py, tests/test_mcp_tools.py
- evidence:

LongMemEval 영어 표현 다섯 종류와 한국어 "지난주", "5월에", "N일 전", "지난달"이 고정한 오늘에서 정한 범위로 풀리고 이 컴퓨터 시간대로 비교된다. 잘못된 입력은 MCP 입력 오류와 CLI 종료 코드 2다. 질의 본문의 날짜 낱말은 범위가 되지 않는다.

### A9. MCP 검색 도구 셋이 날짜 인자와 설명을 갖는다
- covers: D12
- check: tests/test_mcp_tools.py
- evidence:

세 도구가 `since`, `until`을 검색 요청에 넘기고 설명에 날짜 계산 안내가 있다. 날짜 해석기는 부르지 않는다.

### A10. CLI 날짜 해석은 모델을 부르지 않는다
- covers: D14
- check: tests/test_date_expression.py
- evidence:

`--when` 해석 중 하위 프로세스와 네트워크 호출이 없다.

### A11. LongMemEval 실행기가 질문 날짜로 범위를 넘길 수 있다
- covers: D15
- check: tests/test_longmemeval_convert_tool.py, tests/test_longmemeval_run_session_count.py
- evidence:

변환기가 `question_date`를 읽는다. `--date-rules`면 풀리는 질문에만 `--since`·`--until`이 붙고, 없으면 명령이 변경 전과 같다.

### A12. 수집 훅은 작업 파일만 두고 기다리지 않으며 작업자는 하나다
- covers: D16, I8, F10
- check: tests/test_hook_facts.py
- evidence:

켜져 있고 `written`이면 작업 파일 하나와 분리 프로세스가 생긴다. 종료 코드와 출력은 꺼짐과 같고, 느린 가짜 추출기에서도 훅은 1초 안에 끝난다. 잠금이 잡혀 있으면 띄우지 않고, `written`이 아니면 작업 파일이 없다.

### A13. Claude 추출기는 정한 명령으로만 돌고 자식 세션은 훅을 건너뛴다
- covers: D17, I9, F11
- check: tests/test_fact_extractors.py, tests/test_hook_facts.py
- evidence:

명령이 D17과 같고 `--bare`가 없으며, 자식 환경에 `ANTHROPIC_API_KEY`가 없고 `VAULT_GRAPH_FACTS_CHILD=1`이 있다. 그 값이면 두 훅이 실행기와 회상을 부르지 않고 0으로 끝난다.

### A14. 실제 Claude Code에서 추출용 세션이 Vault에 남지 않는다
- covers: I9, F11
- check: 수동: 사실 추출을 켜고 실제 Claude Code 세션 하나를 끝낸 뒤 Vault `raw/sessions/`와 Graph Home `logs/`를 본다
- evidence:

원 세션 part와 그 `.facts.md`만 새로 생기고 추출용 세션 파일은 없다.

### A15. 검색, 색인, 회상은 모델을 부르지 않는다
- covers: I2
- check: tests/test_fact_worker.py
- evidence:

하위 프로세스와 HTTP를 막아도 사실 추출이 켜진 Graph Home의 `vg search`, `vg index`, MCP 검색 도구, `vg hook session-start`가 통과한다.

### A16. 작업자는 실패를 기록하고 캐시로 다시 부르지 않는다
- covers: D20, F7, F8, F9
- check: tests/test_fact_worker.py
- evidence:

가짜 추출기에서 추출기 실패는 대기열 유지, 실패 기록, 30분 안 재시도 없음이다. 스키마 오류는 실패, 없는 교환 id 사실만 빠진다. 명령이 없으면 `facts_writer_missing`이고 생긴 뒤에는 추출기 없이 쓴다. 뽑은 교환이 새 part에 나와도 추출기를 부르지 않는다.

### A17. 추출기 설정과 켜고 끄기가 정한 대로 동작한다
- covers: D18, D19, F13
- check: tests/test_facts_config.py, tests/test_hook_facts.py
- evidence:

설정이 없으면 `claude`로 켜져 있고 `written` 수집에 작업 파일이 생긴다. 첫 작업에서만 안내 한 줄이 stderr에 나온다. `off`는 `enabled: false`를 쓰고 그 뒤 작업 파일이 없다. `on --extractor llama-server`는 로컬을 고른다. 깨진 설정은 꺼짐이고 `status`에 이유가 나온다. 지난 세션은 대기열에 들지 않는다.

### A25. 테스트와 LongMemEval 실행기는 실제 추출기를 부르지 않는다
- covers: D19
- check: tests/test_longmemeval_run_session_count.py, tests/test_fact_worker.py
- evidence:

`longmemeval_run`은 B 측정 인자가 없으면 작업 공간 Graph Home마다 `enabled: false`를 쓰고, 그 실행에서 `claude`나 `llama-server` 호출이 없다. 테스트 공용 설정은 가짜 추출기를 넣고 실제 추출기 어댑터를 부르면 실패한다.

### A18. 사실 키는 원 교환을 돌려주고 빼는 모드에서는 지금과 같다
- covers: D21, D28, I3, I6, F12
- check: tests/test_session_facts_index.py
- evidence:

첨부 줄마다 원 교환 `parent_key`와 줄 날짜의 `derived` 조각이 생기고 모르는 판은 경고와 함께 빠진다. 사실만 맞아도 발췌와 근거는 원 교환이고 사실 텍스트는 응답에 없다. 원 part가 없으면 `fact_source_missing`이다. `include_fact_keys=false`와 첨부 없는 Vault는 B 전과 같다.

### A19. 사실 첨부는 Vault 명령으로만 쓰고 수집한 Vault에 간다
- covers: I7
- check: tests/test_fact_worker.py
- evidence:

작업자 전후 Vault 변화는 가짜 `sessions attach-facts`가 만든 것뿐이고, 명령은 작업 파일의 Vault와 part 경로로 불린다. part 파일 내용은 같다.

### A20. 원칙 문장이 승인된 문장으로 바뀐다
- covers: D22
- check: 수동: `docs/SPEC.md` §1 원칙1·4와 §9.2 B-2, `AGENTS.md` Project Boundary를 승인된 D22 문장과 비교한다
- evidence:

네 곳이 D22와 같고 요약·목록·점수 금지 문장은 남아 있다. `docs/DECISIONS.md`와 PATCH_LOG에 항목이 있다.

### A21. A, C, B 각각이 세 관문을 넘는다
- covers: D1, D24
- check: 수동: 부분마다 `longmemeval_run --limit 150`(C는 `--date-rules`, `TZ=UTC`), 층1 `evaluate_search --split dev`·`--split test`, 층2 `evaluate_search --vault-id eval2`를 돌려 `research/baseline.md`와 비교한다
- evidence:

보고서에 부분마다 유형별 `recall_all_at_5`·`recall_any_at_5`, 세션 수, 층1 세션 recall@5(dev·test), 층2 recall@5가 기준선과 나란히 있다. 층1은 dev·test 모두 기준선 이상, 층2는 0.95 이상이다. 못 넘은 부분은 사유가 있다.

### A22. B 측정은 정한 범위에서 두 추출기를 같은 문항으로 비교한다
- covers: D23, D18
- check: 수동: 정한 문항으로 `longmemeval_run`을 사실 추출 꺼짐, Claude, `llama-server`로 돌리고 공유 캐시의 호출 수와 시간을 본다
- evidence:

보고서에 문항 범위, 추출기별 호출 수·시간, 유형별 `recall_all_at_5`, 기본 추출기 판단 근거가 있다.

### A23. vault-builder: 첨부 명령이 정한 형식과 검증을 따른다
- covers: D25, D26, D27
- check: 수동: vault-builder 저장소 세션의 테스트 결과와 `sessions attach-facts` 실행 기록을 읽는다
- evidence:

vault-builder 저장소에서 구현한다. 정상 입력은 part 옆에 첨부를 만들고 `written`, 재실행은 `exists`, D27의 거부 조건은 `rejected`이고 파일이 없다. `git-check`와 `capture`는 첨부를 세지 않는다.

### A24. B 통합은 vault-builder 결과를 받은 뒤 실제 명령으로 돈다
- covers: D29
- check: 수동: vault-builder 결과가 들어온 뒤 LongMemEval 작업 공간 하나를 `--keep`으로 돌려 `.facts.md`와 `derived` 조각 수를 본다
- evidence:

첨부가 실제 `sessions attach-facts`로 만들어졌고 vault-builder 결과가 같은 계약 판을 따른다. 그 전의 B 값은 보고서에 쓰지 않는다.

## 9. Open decisions

spec gate의 질문 일곱 개는 2026-11-16 모두 답을 받았고, 답은 해당 결정 블록의 `by`에 있다. 남은 열린 결정은 없다.
