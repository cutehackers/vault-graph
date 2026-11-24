# 1. dream-settings-run-at

## id
1

## title
`DreamSettings`에 `run_at`을 더하고 형식을 검사한다

## goal
설정 파일이 실행 시각을 읽고 쓰게 된다. 기본은 01:00(D1)이고, `run_at`이 없는 기존 파일도 꺼지지 않는다(I5).

## units
D1, I5, F7, F8, A1

## files
- src/vault_graph/operation/scope/dream_settings.py
- tests/test_dream_settings.py

## blockers
none

## checks
- tests/test_dream_settings.py

## done-when
- [ ] `run_at: str = "01:00"`이 `DreamSettings`에 있고, 없는 파일은 01:00이다
- [ ] `run_at`이 없는 버전 1 파일은 `source="file"`, 01:00으로 읽히고 `enabled`와 한도는 파일 값이다
- [ ] "00:00"과 "23:59"는 받고, "1:00", "24:00", "01:60", 숫자 1, 빈 문자열은 `broken`이다
- [ ] 저장한 파일에는 언제나 `run_at`이 있고 형식 버전은 1이다
