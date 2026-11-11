---
title: "Reset Tidepool local database on simulator"
summary: "Wipe the expo-sqlite file on the iOS simulator or Android emulator during development."
tags: [tidepool, mobile, storage, dev]
---

# Reset Tidepool local database on simulator

## Steps

1. 앱의 개발자 메뉴(설정 화면 버전 텍스트를 7번 탭)에서 "Reset local DB"를 누른다. `tidepool.db`를 닫고 지운 뒤 앱을 다시 시작한다.
2. 메뉴가 안 열리면 iOS simulator는 `xcrun simctl get_app_container booted dev.tidepool.app data`로 경로를 찾아 `Library/LocalDatabase/tidepool.db`를 지운다.
3. Android emulator는 `adb shell run-as dev.tidepool.app rm databases/tidepool.db`를 실행한다.
4. 앱을 다시 열면 migration이 `user_version` 0부터 다시 돈다.

## Notes

- production build에는 개발자 메뉴가 없다. `__DEV__` flag로 막는다.
- seed 데이터가 필요하면 `pnpm seed:sim`이 30일치 intake log를 넣는다.
