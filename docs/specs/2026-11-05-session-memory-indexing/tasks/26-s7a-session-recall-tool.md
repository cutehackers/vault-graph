## id
26

## title
S7a 세션 평가 도구 `measure_session_recall.py`

## goal
교환 단위 recall@5·10, MRR을 (a)(b)(c) 단계로 잴 수 있다. (Intent 3)

## spec
§4.2.10

## acceptance
A-8(도구 부분)

## files
- tests/benchmarks/measure_session_recall.py (신규)
- tests/test_measure_session_recall_tool.py (신규)

## blockers
1, 24

## checks
pytest tests/test_measure_session_recall_tool.py -q

## wave
9

## done-when
- [ ] 질의 세트 줄 형식 `{id, question, expected_exchanges, kind}`을 읽고, 같은 교환의 여러 창을 한 번만 센다
- [ ] 하위 프로세스로 실행하고 결과 파일은 저장소 밖에 쓰며, 합계만 보고서에 낸다
- [ ] vault-graph pytest 전체 통과, 독립 커밋

## notes
spec의 S7 선행에는 S6(#14, #25)도 있다. 도구 작성은 S6 없이 가능하고, 측정(#31)이 S6 뒤다. 질의 세트는 개인 세션 내용이라 저장소에 넣지 않는다.
