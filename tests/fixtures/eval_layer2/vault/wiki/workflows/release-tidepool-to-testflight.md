---
title: "Release Tidepool to TestFlight"
summary: "Build the iOS app on EAS and submit it to TestFlight."
tags: [tidepool, mobile, release, ios]
---

# Release Tidepool to TestFlight

## Steps

1. `main`에서 `app.config.ts`의 `version`을 올린다. iOS `buildNumber`는 EAS가 `autoIncrement`로 올리므로 손대지 않는다.
2. `pnpm release:check`로 typecheck, lint, jest를 돌린다.
3. `eas build --platform ios --profile production`을 실행한다. 10~20분 걸린다.
4. build가 끝나면 `eas submit --platform ios --latest`로 App Store Connect에 올린다.
5. App Store Connect에서 "Export Compliance" 질문에 "No"를 답한다(암호화는 HTTPS만 쓴다).
6. TestFlight 내부 그룹 `tidepool-internal`에 build를 배정한다.
7. Sentry release `tidepool@<version>+<buildNumber>`가 생겼는지 확인한다.

## Notes

- submit이 "Missing Compliance"로 멈추면 5번을 빼먹은 것이다.
- 외부 테스터 그룹은 Apple 심사(보통 하루)가 필요하다.
