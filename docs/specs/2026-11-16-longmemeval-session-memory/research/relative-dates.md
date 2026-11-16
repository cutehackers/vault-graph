# LongMemEval temporal-reasoning 질문의 날짜 표현

측정일: 2026-11-16. 데이터: `longmemeval_s_cleaned.json`(sha256 `d6f21ea9…a442`), abstention 질문을 뺀 temporal-reasoning 전체 127문항. 질문 원문은 옮기지 않고 표현의 종류만 적는다.

### X14. 날짜 범위 표현은 127문항 중 27문항이다
- source: longmemeval_s_cleaned.json temporal-reasoning 127문항 (2026-11-16 상위 세션이 셈)
- basis:

27문항(21%)만 검색 범위를 좁힐 날짜 표현을 담는다. 나머지 100문항은 "며칠 전에 X를 했나", "X와 Y 사이 며칠", "어느 것이 먼저" 꼴이라 날짜 범위가 아니라 찾은 세션들의 날짜를 비교해야 답이 나온다.

### X15. 27문항의 표현은 모두 고정 규칙으로 풀린다
- source: longmemeval_s_cleaned.json temporal-reasoning 127문항 (2026-11-16 상위 세션이 셈)
- basis: X14

표현 종류(영어): "N days/weeks/months ago"(15), "last <요일>"·"last week/month"(6), "in the past N months"·"during the past month"(3), "in <월>"·"in <월> and <월>"(4, 겹침 있음), 월·일 명시 1. 모두 질문 날짜를 기준으로 한 고정 규칙으로 범위를 정할 수 있다. "a couple of days ago"와 "the Wednesday two months ago"는 규칙이 넓은 범위(예: 2~4일 전, 두 달 전 그 주)를 주면 된다.

### X16. 규칙으로 풀 수 없는 상대 날짜 표현은 0개다
- source: longmemeval_s_cleaned.json temporal-reasoning 127문항 (2026-11-16 상위 세션이 셈)
- basis: X15

이 데이터에서 규칙으로 풀 수 없는 상대 날짜 표현을 찾지 못했다(0/127). 따라서 LongMemEval에서 CLI용 Haiku 해석이 더해 줄 수 있는 질문 수는 0이다.

### X17. 한국어 날짜 표현은 이 데이터에 없다
- source: longmemeval_s_cleaned.json temporal-reasoning 127문항 (2026-11-16 상위 세션이 셈); 사용자 기억 "Vault 내용 언어"
- basis:

"지난주", "5월에", "보름 전", "지지난 주말" 같은 한국어 표현은 이 데이터에 없다. Vault 내용과 질의가 한국어일 수 있으므로 CLI 규칙은 한국어 기본 표현도 다뤄야 한다 `[가정]`.

### X18. Haiku 호출 지연은 아직 재지 않았다
- source: 상위 세션 기록 (2026-11-16, pending)
- basis:

`claude -p --model claude-haiku-5-5 --json-schema … --no-session-persistence` 호출 지연은 기준선 측정이 끝나 기계가 한가할 때 잰다. 아직 측정하지 않았다.
