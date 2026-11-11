---
title: "Use EAS Build for Tidepool releases"
summary: "Tidepool release builds run on Expo EAS Build, not on a local Xcode or Gradle machine."
tags: [tidepool, mobile, release]
---

# Use EAS Build for Tidepool releases

## Decision

Tidepool의 iOS·Android release build는 Expo EAS Build 클라우드에서 만든다. 로컬 Mac에서 `xcodebuild`로 archive하던 방식은 그만둔다.

## Why

- 로컬 archive는 내 MacBook의 Xcode 버전과 keychain 상태에 따라 결과가 달라졌다. 2026-08에 signing certificate가 만료돼 release가 이틀 늦어졌다.
- EAS는 credentials를 Expo 서버에 보관하고 build마다 같은 image를 쓴다. 누가 빌드해도 결과가 같다.
- Android keystore를 개인 노트북에 두는 위험이 없어진다.
- 무료 tier는 월 30 build로 충분하다. 현재 release 주기는 2주에 한 번이다.

## Consequences

- `eas.json`에 `production`, `preview`, `development` profile을 둔다.
- build 대기 시간이 10~20분 생긴다. 급한 hotfix는 OTA update(`eas update`)로 먼저 내보낸다.
