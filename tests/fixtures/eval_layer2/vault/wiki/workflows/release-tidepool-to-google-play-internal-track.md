---
title: "Release Tidepool to Google Play internal track"
summary: "Build the Android app bundle on EAS and submit it to the Play Console internal track."
tags: [tidepool, mobile, release, android]
---

# Release Tidepool to Google Play internal track

## Steps

1. `app.config.ts`의 `version`을 iOS와 같은 값으로 맞춘다. Android `versionCode`는 EAS `autoIncrement`가 올린다.
2. `eas build --platform android --profile production`으로 `.aab`를 만든다.
3. `eas submit --platform android --latest --track internal`로 Play Console internal track에 올린다.
4. 처음 한 번은 Play Console에서 수동 업로드가 필요하다(API로는 첫 업로드 불가). 이미 됐으므로 지금은 생략.
5. internal tester 목록(`tidepool-qa@` Google Group)에 opt-in 링크를 보낸다.
6. 이상이 없으면 Play Console에서 internal → production으로 promote하고 rollout을 20%로 시작한다.

## Notes

- service account JSON은 EAS credentials에 있다. 로컬에 받지 않는다.
