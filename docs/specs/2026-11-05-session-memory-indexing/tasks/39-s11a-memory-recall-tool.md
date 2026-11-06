## id
39

## title
S11a 기억 평가 도구 `measure_memory_recall.py`

## goal
평가 세트로 지표1~6을 LLM 없이 잴 수 있다. (Intent 7, 8)

## spec
§4.4.10

## acceptance
A-28(도구 부분)

## files
- tests/benchmarks/measure_memory_recall.py (신규)
- tests/test_measure_memory_recall_tool.py (신규)

## blockers
1, 36

## checks
pytest tests/test_measure_memory_recall_tool.py -q

## wave
12

## done-when
- [ ] 질문마다 회상 텍스트와 `build_context_pack`에 정답 페이지가 있는지 결정적으로 본다
- [ ] 지표1~6을 출력한다(지표3~6은 기록만 한다)
- [ ] vault-graph pytest 전체 통과, 독립 커밋

## notes
평가 세트는 개인 내용이라 저장소 밖에 둔다. 채점에 LLM을 쓰지 않는다.
