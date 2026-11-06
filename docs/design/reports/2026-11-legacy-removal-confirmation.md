# 확인 A-30: vault-builder 대체 경로 제거 여부 (2026-11-07)

spec 2026-11-05-session-memory-indexing, 작업 #46. spec §4.4.9는 대체 경로(vault-builder의 `memory-cleanup` 스킬, `maps build` 프로젝트 요약, `recall.sh`, `/project-memory`)를 사람이 한 번 더 확인한 뒤 지우도록 정했다.

## 근거

- 진행 조건: 기억 품질 지표1(대체·폐기 기억 주입)과 지표2(다른 프로젝트 기억 섞임)가 이 Mac의 다섯 프로젝트에서 모두 0이다(보고서 2026-11-memory-quality).
- 아직 없는 것: 실제 세션에서 "기억 정리해"로 vg 정리 흐름을 돌린 기록(작업 #38)이 없다.

## 사람의 결정

- 날짜: 2026-11-07
- 결정: **보류.** 실제 세션에서 "기억 정리해"를 한 번 돌려 본 뒤(작업 #38) 제거한다.
- 그동안: vault-builder 요청S11(제거)은 내지 않는다. vg 회상과 `recall.sh` 회상 두 경로가 함께 동작한다(A-29). 작업 #47(제거 뒤 확인)은 S11이 반영된 뒤에 한다.
- vault-builder 쪽 제거 목록은 vault-builder 브랜치 `feat/jh/session-memory-requests`의 `docs/superpowers/specs/2026-11-06-fallback-removal-s11-ko.md`에 있다.
