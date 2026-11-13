---
title: "Keep Tidepool notifications local-only"
summary: "Tidepool v1 schedules reminders on the device and has no server push."
tags: [tidepool, mobile, notifications]
---

# Keep Tidepool notifications local-only

## Decision

Tidepool v1의 물 마시기 알림은 `expo-notifications`의 local scheduled notification만 쓴다. APNs/FCM server push는 v1에 넣지 않는다.

## Why

- 알림 내용이 사용자 기기 안의 설정(간격, 수면 시간)만으로 정해진다. 서버가 알아야 할 정보가 없다.
- server push를 하려면 device token 저장, 계정 시스템, 서버가 필요하다. v1에는 계정이 없다.
- iOS는 앱당 pending local notification을 64개까지만 허용한다. 하루 최대 16회 × 4일치를 미리 예약하고, 앱을 열 때마다 다시 채운다.

## Revisit when

- 가족 공유 기능처럼 다른 기기에서 일어난 일을 알려야 할 때.
