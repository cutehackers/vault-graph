# 14. fact-extractors

## id
14

## title
Claude CLI와 `llama-server` 사실 추출기 어댑터를 만든다

## goal
로그인된 Claude Code나 로컬 모델로 세션 사실을 뽑는다. API 키는 쓰지 않는다. 13번 task의 포트 `FactExtractor`를 구현한다. Intent 3을 맡는다.

## units
D17, I2, I9, F11, A13

## files
- src/vault_graph/interface/composition/adapters/claude_fact_extractor.py
- src/vault_graph/interface/composition/adapters/llama_fact_extractor.py
- tests/test_fact_extractors.py

## blockers
13, 20

## checks
- tests/test_fact_extractors.py

## done-when
- [ ] Claude 명령이 `claude -p --model claude-sonnet-5-5 --json-schema <스키마> --no-session-persistence`이고 `--bare`가 없다
- [ ] 자식 환경에 `ANTHROPIC_API_KEY`가 없고 `VAULT_GRAPH_FACTS_CHILD=1`이 있다
- [ ] 출력은 사실마다 문장, 날짜, 교환 id이고 세션의 언어를 따른다
- [ ] `llama-server` 어댑터가 `endpoint`와 `model` 설정을 쓴다
- [ ] 시험은 하위 프로세스와 HTTP를 가짜로 막는다
- [ ] 검색·색인·회상 경로가 이 어댑터를 가져오지 않는다
