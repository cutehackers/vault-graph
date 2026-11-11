---
title: "Use Redux Toolkit for Tidepool state"
summary: "Superseded. Early Tidepool used Redux Toolkit for all app state."
tags: [tidepool, mobile, state, superseded]
---

# Use Redux Toolkit for Tidepool state

> Status: superseded by [[use-zustand-for-tidepool-state|Use Zustand for Tidepool state]] (2026-06).

## Decision (old)

Tidepool 초기 버전(v0.3)은 모든 상태를 Redux Toolkit store에 두기로 했다.

## Why (at the time)

- 처음에는 서버 sync를 Redux middleware로 처리할 계획이었다. RTK Query로 API cache를 함께 쓰려 했다.
- Redux DevTools의 time-travel debugging이 onboarding flow 디버깅에 유용했다.

## Why it was reversed

서버 sync가 v1 범위에서 빠지면서 RTK Query를 쓸 일이 없어졌다. 남은 장점이 구조 비용보다 작았다.
