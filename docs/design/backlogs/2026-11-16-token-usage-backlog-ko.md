---
type: design-backlog
id: TOKEN
status: proposed
priority: 중요
created: 2026-11-16
---

# 토큰 사용 안내 backlog

## 1. 목표

vault-graph를 쓸 때 사용자의 Claude 사용량(토큰)을 쓰게 되는 경우를 한곳에 정리해 README에 알린다. 2026-11-16 spec
`2026-11-16-longmemeval-session-memory`에서 세션 사실 추출을 기본으로 켜기로 하면서(D19) 생긴 과제다.

범위는 README와 사용자 안내 문서다. 토큰 사용을 줄이는 기능 변경은 범위 밖이다.

## 2. 한눈에 보기

| ID | 제목 | 우선순위 | 상태 | 선행 |
| --- | --- | --- | --- | --- |
| TOKEN-01 | README가 vault-graph 사용 중 토큰을 쓰는 경우를 알리지 않는다 | 중요 | proposed | spec 2026-11-16 B 구현 |

## 3. 중요

### TOKEN-01 README가 vault-graph 사용 중 토큰을 쓰는 경우를 알리지 않는다
- [ ] proposed · 안내 · docs
- 문제: [결정] 세션 사실 추출이 기본으로 켜져, 세션이 끝날 때마다 로그인된 Claude Code로 `claude -p`를 부른다(spec
  2026-11-16 D19, 사용자 답 2026-11-16). [가정] 세션 시작 회상이 넣는 문맥, MCP 도구 응답 크기 같은 다른 사용 요인도
  README에 정리되어 있지 않다.
- 영향: 사용자가 사용량이 왜 늘었는지 모르고, 끄는 방법(`vg facts off`)도 찾기 어렵다.
- 방향: 토큰을 쓰는 경우(사실 추출, 세션 시작 회상 문맥, MCP 도구 응답 등)를 코드에서 확인해 목록으로 만들고, 경우마다
  언제 일어나는지, 대략 얼마인지, 끄거나 줄이는 방법을 README에 적는다.
- 완료: README에 토큰 사용 절이 있고, 각 경우가 코드 위치와 대조되어 있으며, 사실 추출 끄는 방법이 적혀 있다.
- 선행: spec 2026-11-16-longmemeval-session-memory B 구현
- 출처: spec 2026-11-16-longmemeval-session-memory gate 답(2026-11-16)
