---
title: "Expo SDK 51 upgrade notes"
summary: "What changed for Tidepool when moving from Expo SDK 50 to 51."
tags: [tidepool, mobile, source]
---

# Expo SDK 51 upgrade notes

## Source

Expo SDK 51 release note와 upgrade guide를 읽고 Tidepool에 해당하는 것만 정리했다.

## Notes

- `expo-sqlite`가 새 API(`openDatabaseAsync`)로 바뀌었다. 옛 `expo-sqlite/legacy` import를 모두 바꿨다.
- `expo-router` v3: typed routes가 기본. `href` 오타가 typecheck에서 잡힌다.
- iOS 최소 버전이 13.4로 올라갔다.
- `eas.json`의 `node` 버전을 20으로 맞춰야 build가 된다.
