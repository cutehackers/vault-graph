# 24. fact-expansion-key

## id
24

## title
사실을 교환마다 확장 키 하나로 색인하고 가중치를 1.0으로 둔다

## goal
사실 줄마다 따로 만들던 조각을, 교환마다 "사용자 질문 제목 + 그 교환 사실들" 확장 키 하나로 바꾼다(논문의 키 합치기, X27). 가중치는 원문과 같은 1.0으로 둔다(X29). 원문 창은 그대로다(I1).

## units
D21, D28, A18

## files
- src/vault_graph/indexing/ingestion/session_facts_chunker.py
- src/vault_graph/retrieval/search/candidate_ranking.py
- tests/test_session_facts_index.py

## blockers
23

## checks
- tests/test_session_facts_index.py

## done-when
- [ ] 첨부 하나에서 교환 수만큼 확장 키 조각이 생기고, 조각 텍스트는 그 교환의 사용자 질문 제목과 사실 문장들이다
- [ ] 제목은 frontmatter `source`의 part 파일에서 읽고, 읽을 수 없으면 사실만 쓴다
- [ ] 조각 시각은 그 교환 사실 날짜의 처음과 끝이다
- [ ] `FACT_KEY_WEIGHT`가 1.0이다
- [ ] 원문 창 `text`, 조각 id, `source_locators`, 임베딩 입력은 바이트 단위로 같다
