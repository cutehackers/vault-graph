---
title: "Use Zustand for Tidepool state"
summary: "Tidepool app state moved from Redux Toolkit to Zustand stores."
tags: [tidepool, mobile, state]
---

# Use Zustand for Tidepool state

## Decision

Tidepool의 화면 상태는 Zustand store로 관리한다. 이전 결정인 [[use-redux-toolkit-for-tidepool-state|Use Redux Toolkit for Tidepool state]]를 대체한다.

## Why

- 상태 대부분이 SQLite에 있고, 메모리 상태는 오늘 목표량, 현재 streak, 설정 화면 draft 정도다. Redux의 action/reducer/slice 구조가 이 크기에 비해 과했다.
- Redux Toolkit 도입 후 slice 파일이 14개로 늘었는데 실제 공유 상태는 3개뿐이었다.
- Zustand는 Provider 없이 hook 하나로 쓰여서 widget extension용 작은 entry에서도 그대로 재사용된다.
- bundle size가 약 38KB 줄었다.

## Migration

`src/state/` 아래 `useIntakeStore`, `useSettingsStore`, `useSessionStore` 세 개로 정리했다. devtools는 `zustand/middleware`의 `devtools`로 대체한다.
