---
title: "Tidepool app architecture"
summary: "Layers of the Tidepool React Native app: screens, Zustand stores, domain functions and SQLite."
tags: [tidepool, mobile, architecture]
---

# Tidepool app architecture

## Stack

React Native 0.74, Expo SDK 51 managed workflow, expo-router, TypeScript strict.

## Layers

1. `app/`: expo-router 화면. 상태를 직접 SQLite에서 읽지 않는다.
2. `src/state/`: Zustand store 세 개. 화면과 repository 사이에 있다.
3. `src/domain/`: streak, 목표량 계산 같은 순수 함수. React import 금지.
4. `src/data/`: SQLite repository와 migration(`src/data/migrations/NNN_*.ts`).
5. `src/notifications/`: 알림 예약([[tidepool-notification-scheduler|Tidepool notification scheduler]]).

## External

PostHog(analytics), Sentry(crash), EAS(build, OTA update). 서버는 없다.
