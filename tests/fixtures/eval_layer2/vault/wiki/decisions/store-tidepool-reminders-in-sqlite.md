---
title: "Store Tidepool reminders in SQLite"
summary: "Reminders and intake logs live in expo-sqlite instead of AsyncStorage."
tags: [tidepool, mobile, storage]
---

# Store Tidepool reminders in SQLite

## Decision

Tidepool의 reminder 설정과 물 섭취 기록(intake log)은 `expo-sqlite`에 저장한다. AsyncStorage에는 테마, 온보딩 완료 여부 같은 작은 flag만 둔다.

## Why

- intake log가 하루 10~20건씩 쌓인다. AsyncStorage에 JSON 배열로 두면 앱 시작 때 전체를 parse해야 해서 1년 사용자 기준 cold start가 1.8초까지 늘었다.
- 주간 통계 화면은 날짜 범위 query가 필요하다. SQLite index로 바로 처리된다.
- migration을 `PRAGMA user_version`으로 관리할 수 있다.

## Alternatives considered

- WatermelonDB: sync 기능은 좋지만 native module 설정이 무겁고 Expo managed workflow와 충돌했다.
- MMKV: 빠르지만 key-value라서 범위 query 문제가 그대로 남는다.
